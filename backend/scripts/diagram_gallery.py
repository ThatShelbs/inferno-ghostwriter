"""Render every code-drawn diagram template with sample content into a contact sheet for a visual review.

    uv run python scripts/diagram_gallery.py                        # every template in two schemes, free
    uv run python scripts/diagram_gallery.py --compare              # plus the reference images in examples/Others
    uv run python scripts/diagram_gallery.py --schemes inferno:white magma:near_black

Writes one PNG per template and scheme and ``contact.png`` to data/diagram-gallery/ (git-ignored).
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from inferno_ghostwriter.images.diagrams import TEMPLATES, render_diagram_png
from inferno_ghostwriter.images.diagrams.samples import SAMPLES
from inferno_ghostwriter.images.memes.text import load_font
from inferno_ghostwriter.images.palettes import from_id

ROOT = Path(__file__).resolve().parents[2]
THUMB = 700
PAD = 28
LABEL = 44


def _open(data: bytes | Path) -> Image.Image:
    with Image.open(io.BytesIO(data) if isinstance(data, bytes) else data) as img:
        return img.convert("RGB")


def _thumb(img: Image.Image) -> Image.Image:
    return img.resize((THUMB, round(img.height * THUMB / img.width)), Image.Resampling.LANCZOS)


def contact_sheet(rows: list[tuple[str, list[Image.Image]]], columns: int) -> Image.Image:
    heights = [LABEL + max(i.height for i in imgs) + PAD for _, imgs in rows]
    sheet = Image.new("RGB", (PAD + columns * (THUMB + PAD), PAD + sum(heights)), "#ffffff")
    draw = ImageDraw.Draw(sheet)
    font = load_font("bold", 24)
    y = PAD
    for (title, imgs), h in zip(rows, heights, strict=True):
        draw.text((PAD, y + 6), title, font=font, fill="#14101f")
        for i, img in enumerate(imgs):
            sheet.paste(img, (PAD + i * (THUMB + PAD), y + LABEL))
        y += h
    return sheet


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--schemes", nargs="+", default=["inferno:light_gray", "viridis:white"], help="ramp:surface ids")
    parser.add_argument("--compare", action="store_true", help="add the reference images from examples/Others")
    parser.add_argument("--refs", type=Path, default=ROOT / "examples" / "Others", help="the reference image folder")
    parser.add_argument("--credit", default="@ghostwriter", help="credit handle drawn bottom-right")
    parser.add_argument("--only", nargs="*", default=[], help="template ids to render (default: all)")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "diagram-gallery")
    args = parser.parse_args(argv)

    schemes = [s for s in (from_id(i) for i in args.schemes) if s is not None]
    if not schemes:
        print("No valid scheme ids; use ramp:surface, e.g. inferno:light_gray.", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    rows: list[tuple[str, list[Image.Image]]] = []
    if args.compare:
        refs = (
            sorted(p for p in args.refs.glob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")) if args.refs.is_dir() else []
        )
        if refs:
            thumbs = [_thumb(_open(p)) for p in refs]
            for start in range(0, len(thumbs), len(schemes)):
                rows.append(
                    ("References: " + ", ".join(p.stem for p in refs[start : start + len(schemes)]), thumbs[start : start + len(schemes)])
                )
        else:
            print(f"No reference images in {args.refs}; skipping --compare.")
    for template in TEMPLATES.values():
        if args.only and template.id not in args.only:
            continue
        imgs = []
        for sch in schemes:
            png, _, _ = render_diagram_png(SAMPLES[template.id], sch, args.credit)
            (args.out / f"{template.id}__{sch.id.replace(':', '_')}.png").write_bytes(png)
            imgs.append(_thumb(_open(png)))
        rows.append((f"{template.name} ({template.id}, {template.width}x{template.height}): {template.use_when}", imgs))
    sheet = contact_sheet(rows, max(len(schemes), max((len(i) for _, i in rows), default=1)))
    path = args.out / "contact.png"
    sheet.save(path, optimize=True)
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
