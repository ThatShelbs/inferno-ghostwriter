"""Render every meme format into a contact sheet for a visual review.

    uv run python scripts/meme_gallery.py                      # canned demo builds, free
    uv run python scripts/meme_gallery.py --compare            # each format next to its original from the reference library, free
    uv run python scripts/meme_gallery.py --compare --refs ../examples   # another reference folder
    uv run python scripts/meme_gallery.py --real --yes         # real Claude memes for your latest projects (costs money)
    uv run python scripts/meme_gallery.py --real --yes --format venn --projects 2

Writes PNGs and an index.html to data/meme-gallery/ (git-ignored). The reference library (``examples/`` by default, see
``images/references.py``) holds third-party originals and is never committed.
"""

from __future__ import annotations

import argparse
import asyncio
import html
import shutil
import sys
from pathlib import Path

from inferno_ghostwriter.config import Settings
from inferno_ghostwriter.demo import meme_build_payload
from inferno_ghostwriter.images.memes.compose import compose
from inferno_ghostwriter.images.memes.formats import FAMILIES, FORMATS, get_format
from inferno_ghostwriter.images.memes.settings import configure as configure_settings
from inferno_ghostwriter.images.memes.specs import MemeBuild
from inferno_ghostwriter.images.references import ReferenceLibrary

ROOT = Path(__file__).resolve().parents[2]

Card = tuple[str, str, str, str]  # our image, its title, alt text, the original ("" when none)


def demo_cards(out: Path, refs: ReferenceLibrary | None) -> list[Card]:
    cards = []
    for fmt in FORMATS:
        build = MemeBuild.model_validate(meme_build_payload(fmt.id))
        png, _, _ = compose(fmt, {t.slot: t for t in build.texts}, {a.region: a.svg for a in build.art}, build.cast_defs, build.data)
        (out / f"{fmt.id}.png").write_bytes(png)
        original = ""
        if refs is not None and (found := refs.for_meme(fmt.id)) is not None:
            original = f"original-{fmt.id}{found.suffix}"
            shutil.copyfile(found, out / original)
        if refs is None or original:
            cards.append((f"{fmt.id}.png", f"{fmt.name} ({FAMILIES[fmt.family]})", build.alt, original))
    return cards


async def real_cards(out: Path, projects: int, only: str | None) -> list[Card]:
    from sqlmodel import Session, col, select

    from inferno_ghostwriter.db import Persona, Project, ProjectImage
    from inferno_ghostwriter.services import build_services
    from inferno_ghostwriter.voice import current_voice_profile

    services = build_services(Settings())
    cards: list[Card] = []
    with Session(services.engine) as session:
        rows = list(session.exec(select(Project).where(Project.status == "ready").order_by(col(Project.updated_at).desc()).limit(projects)))
        jobs = []
        for project in rows:
            meme = session.exec(select(ProjectImage).where(ProjectImage.project_id == project.id, ProjectImage.kind == "meme")).first()
            persona = session.get(Persona, project.persona_id)
            profile = current_voice_profile(session, project.persona_id)
            if meme and meme.id is not None and persona:
                jobs.append((project, meme.id, Persona.model_validate(persona.model_dump()), profile.markdown if profile else ""))
    for project, image_id, persona, voice in jobs:
        image = await services.images.create(
            image_id, persona=persona, title=project.title, markdown=project.markdown, voice_profile=voice, rethink=True, format=only
        )
        for n, finalist in enumerate(image.finalists or [{"file_name": image.file_name, "label": image.caption}]):
            name = finalist.get("file_name")
            if not name:
                continue
            target = out / f"project{project.id}-{n}-{name}"
            target.write_bytes((services.storage.image_dir(project.id or 0) / name).read_bytes())
            cards.append((target.name, f"{project.title}: {finalist.get('label') or image.caption}", image.alt, ""))
        if image.error:
            print(f"Project {project.id}: {image.error}", file=sys.stderr)
    return cards


def write_index(out: Path, cards: list[Card]) -> Path:
    def figure(src: str, title: str, alt: str, original: str) -> str:
        ours = f'<img src="{html.escape(src)}" alt="{html.escape(alt)}">'
        theirs = f'<img src="{html.escape(original)}" alt="original">' if original else ""
        pair = f'<div class="pair">{theirs}{ours}</div>' if original else ours
        return f"<figure>{pair}<figcaption>{html.escape(title)}{' (original left, ours right)' if original else ''}</figcaption></figure>"

    figures = "\n".join(figure(*card) for card in cards)
    page = (
        "<!doctype html><meta charset='utf-8'><title>Meme gallery</title><style>"
        "body{font-family:system-ui;background:#1b0c41;color:#fcffa4;margin:24px}"
        "main{display:grid;grid-template-columns:repeat(auto-fill,minmax(520px,1fr));gap:24px}"
        "figure{margin:0;background:#2a1650;padding:12px;border-radius:12px}img{width:100%;border-radius:8px;background:#fff}"
        ".pair{display:grid;grid-template-columns:1fr 1fr;gap:8px;align-items:start}"
        f"figcaption{{margin-top:8px}}</style><h1>Meme gallery</h1><main>{figures}</main>"
    )
    index = out / "index.html"
    index.write_text(page, encoding="utf-8")
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "meme-gallery")
    parser.add_argument("--compare", action="store_true", help="Only formats with an original in the reference library, side by side.")
    parser.add_argument("--refs", type=Path, default=None, help="The reference library folder (default: Settings.image_reference_dir).")
    parser.add_argument("--real", action="store_true", help="Ask Claude for new memes for your latest ready projects (costs money).")
    parser.add_argument("--yes", action="store_true", help="Confirm a --real run.")
    parser.add_argument("--projects", type=int, default=3)
    parser.add_argument("--format", dest="only", help="Constrain --real memes to one format id.")
    args = parser.parse_args()
    if args.only and not get_format(args.only):
        parser.error(f"Unknown format {args.only!r}. Choose from: {', '.join(f.id for f in FORMATS)}")
    if args.real and not args.yes:
        parser.error("--real calls Claude and costs money; add --yes to confirm.")
    args.out.mkdir(parents=True, exist_ok=True)
    # The painted meme settings come from the Cartoon Character Kit in the same library.
    configure_settings(args.refs or Settings().image_reference_dir)
    refs = None
    if args.compare:
        refs = ReferenceLibrary(args.refs or Settings().image_reference_dir)
        if not refs.available:
            parser.error(f"No reference library at {refs.root}; pass --refs.")
    cards = asyncio.run(real_cards(args.out, args.projects, args.only)) if args.real else demo_cards(args.out, refs)
    print(f"Wrote {len(cards)} memes: {write_index(args.out, cards)}")


if __name__ == "__main__":
    main()
