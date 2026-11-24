"""Render every data-art engine to one contact sheet, to review the engines by eye.

    uv run python scripts/art_gallery.py                      # writes data/art_gallery.png
    uv run python scripts/art_gallery.py --compare            # adds the reference images from examples/Data Art
    uv run python scripts/art_gallery.py --engine rings --seeds 1 2 3 --out rings.png

Each row is one engine: two seeds in each of a couple of schemes (dark and light). The dashed lines on each tile mark
the centre 5:2 crop band, where the focal structure must sit. No model calls, no network.
"""

from __future__ import annotations

import argparse
import io
import subprocess
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from inferno_ghostwriter.images import palettes
from inferno_ghostwriter.images.art import ENGINES, DataArtSpec, render_art
from inferno_ghostwriter.images.render import FONT_DIR, svg_to_png

BACKEND = Path(__file__).resolve().parents[1]
TILE_W, TILE_H = 480, 270
LABEL_H = 26
SCHEMES = ("inferno:near_black", "viridis:white", "magma:charcoal")
REF_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
SKIP_REFS = ("machine learning",)  # a literal head; not a model for abstract data art


def _main_checkout() -> Path:
    """The main checkout's root (a worktree's examples live there), else this repo's root."""
    try:
        common = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=BACKEND, capture_output=True, text=True, check=True
        ).stdout.strip()
        return Path(common).parent
    except (OSError, subprocess.CalledProcessError):
        return BACKEND.parent


def _tile(job: tuple[str, int, str, float]) -> bytes:
    engine, seed, scheme_id, density = job
    scheme = palettes.from_id(scheme_id) or palettes.scheme()
    svg = render_art(DataArtSpec(engine=engine, seed=seed, density=density), scheme)  # type: ignore[arg-type]
    png, _, _ = svg_to_png(svg, width=TILE_W)
    return png


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(FONT_DIR / "Inter-Regular.ttf"), size)
    except OSError:
        return ImageFont.load_default()


def _references(folder: Path) -> list[Image.Image]:
    if not folder.is_dir():
        print(f"No reference folder at {folder}; skipping --compare.")
        return []
    out = []
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() not in REF_EXTS or any(s in path.stem.lower() for s in SKIP_REFS):
            continue
        try:
            img = Image.open(path).convert("RGB")
        except OSError:
            continue
        img.thumbnail((TILE_W, TILE_H))
        out.append(img)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--engine", nargs="*", default=list(ENGINES), choices=list(ENGINES))
    parser.add_argument("--seeds", nargs="*", type=int, default=[1, 2])
    parser.add_argument("--schemes", nargs="*", default=list(SCHEMES[:2]), help="ramp:surface ids")
    parser.add_argument("--density", type=float, default=0.6)
    parser.add_argument("--compare", action="store_true", help="add the reference images as the first row")
    parser.add_argument("--refs", type=Path, default=None, help="reference folder (default: examples/Data Art in the main checkout)")
    parser.add_argument("--out", type=Path, default=BACKEND / "data" / "art_gallery.png")
    args = parser.parse_args()

    jobs = [(e, s, sc, args.density) for e in args.engine for sc in args.schemes for s in args.seeds]
    with ProcessPoolExecutor() as pool:
        tiles = list(pool.map(_tile, jobs))

    per_row = len(args.schemes) * len(args.seeds)
    refs = _references(args.refs or _main_checkout() / "examples" / "Data Art") if args.compare else []
    ref_rows = (len(refs) + per_row - 1) // per_row if refs else 0
    rows = len(args.engine) + ref_rows
    sheet = Image.new("RGB", (per_row * TILE_W, rows * (TILE_H + LABEL_H)), "#16161a")
    draw = ImageDraw.Draw(sheet)
    font = _font(15)

    row = 0
    for i, ref in enumerate(refs):
        r, c = divmod(i, per_row)
        y = (row + r) * (TILE_H + LABEL_H)
        draw.text((c * TILE_W + 8, y + 5), "reference", fill="#bbbbbb", font=font)
        sheet.paste(ref, (c * TILE_W + (TILE_W - ref.width) // 2, y + LABEL_H + (TILE_H - ref.height) // 2))
    row += ref_rows

    band_top = (TILE_H - TILE_W * 2 / 5) / 2
    for i, png in enumerate(tiles):
        engine, seed, scheme_id, _ = jobs[i]
        r, c = divmod(i, per_row)
        x, y = c * TILE_W, (row + r) * (TILE_H + LABEL_H)
        draw.text((x + 8, y + 5), f"{engine}  seed {seed}  {scheme_id}", fill="#eeeeee", font=font)
        sheet.paste(Image.open(io.BytesIO(png)).convert("RGB"), (x, y + LABEL_H))
        for by in (band_top, TILE_H - band_top):
            yy = y + LABEL_H + int(by)
            for dx in range(0, TILE_W, 12):
                draw.line([(x + dx, yy), (x + dx + 5, yy)], fill="#7f7f7f", width=1)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.out)
    print(f"Wrote {args.out} ({len(tiles)} tiles)")


if __name__ == "__main__":
    main()
