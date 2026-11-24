"""Contact sheet of the figure library: every style in every pose, plus expressions, outfits and hair.

    uv run python scripts/figure_sheet.py                    # data/figure-sheet/figures.png (free, no model calls)
    uv run python scripts/figure_sheet.py --ramp viridis --surface white --out some/dir

Every figure is placed through ``<use href="#fig-...">`` exactly as Claude's SVG will place it, on a ground line, so
the sheet also checks the feet anchor. Review it by eye: each figure should look whole and appealing at full size and
at thumbnail size.
"""

from __future__ import annotations

import argparse
import html
from pathlib import Path

from inferno_ghostwriter.images.figures import EXPRESSIONS, HAIRS, OUTFITS, POSES, STYLES, FigureColors, SvgSymbol, figure
from inferno_ghostwriter.images.palettes import RAMPS, SURFACES, Scheme, scheme
from inferno_ghostwriter.images.render import svg_to_png

ROOT = Path(__file__).resolve().parents[2]
CELL_W, CELL_H = 210, 270

SCALE = {"bean": 1.7, "ghost": 1.15}  # shown near the line figures' height

Cell = tuple[SvgSymbol, str]


def _rows(sch: Scheme) -> list[tuple[str, list[Cell]]]:
    def colors(i: int) -> FigureColors:
        return FigureColors.from_scheme(sch, i, skin=i % 5, hair=i % 4)

    rows: list[tuple[str, list[Cell]]] = []
    for style in STYLES:
        rows.append((f"{style}: poses", [(figure(style, p, colors=colors(i), tag=f"s{i}"), p) for i, p in enumerate(POSES)]))
    for style in STYLES:
        rows.append(
            (
                f"{style}: expressions",
                [(figure(style, "standing", colors=colors(i), expression=e, tag=f"e{i}"), e) for i, e in enumerate(EXPRESSIONS)],
            )
        )
    looks: list[Cell] = []
    memes = [
        ("plaid", "messy", FigureColors(shirt="#3f6fb0", plaid="#1b2a4a", pants="#33363f"), "plaid, messy"),
        ("dress", "long", FigureColors(shirt="#e0383e", hair="#5a3624"), "dress, long"),
        ("jacket", "short", FigureColors(shirt="#f26b1d", skin="#8d5a3b"), "jacket"),
        ("hoodie", "short", FigureColors(shirt="#7a4a2a"), "hoodie"),
        ("tee", "bald", FigureColors(shirt="#ffffff"), "tee, bald"),
        ("tee", "bun", FigureColors(shirt="#4a0c6b", hair="#c98b3c"), "tee, bun"),
    ]
    for i, (outfit, hair, c, label) in enumerate(memes):
        looks.append((figure("line", "standing", colors=c, outfit=outfit, hair=hair, tag=f"o{i}"), label))
    looks.append((figure("line", "looking_back", colors=memes[0][2], outfit="plaid", hair="messy", tag="db"), "distracted"))
    looks.append((figure("line", "nope", colors=memes[2][2], outfit="jacket", tag="dn"), "drake nope"))
    looks.append((figure("line", "yep", colors=memes[2][2], outfit="jacket", tag="dy"), "drake yep"))
    looks.append((figure("line", "nervous", colors=FigureColors(shirt="#3b5998"), hair="short", tag="bt"), "two buttons"))
    looks.append(
        (figure("line", "standing", colors=memes[3][2], outfit="hoodie", expression="calm", facing="left", tag="iq"), "hood, left")
    )
    rows.append(("line: outfits, hair, memes", looks))
    assert all(h in HAIRS for _, h, _, _ in memes) and all(o in OUTFITS for o, *_ in memes)
    return rows


def sheet(sch: Scheme) -> bytes:
    rows = _rows(sch)
    cols = max(len(cells) for _, cells in rows)
    head = 34
    width, height = CELL_W * cols, (CELL_H + head) * len(rows)
    defs: list[str] = []
    body: list[str] = []
    ink = sch.ink
    for r, (title, cells) in enumerate(rows):
        top = r * (CELL_H + head)
        body.append(f'<text x="12" y="{top + 24}" font-size="17" font-weight="700" fill="{ink}">{html.escape(title)}</text>')
        for c, (sym, label) in enumerate(cells):
            defs.append(sym.svg)
            cx = c * CELL_W + CELL_W / 2
            ground = top + head + CELL_H - 42
            body.append(f'<line x1="{cx - 80}" y1="{ground}" x2="{cx + 80}" y2="{ground}" stroke="{sch.line}" stroke-width="1.5"/>')
            body.append(sym.use(cx, ground, sym.height * SCALE.get(sym.id.split("-")[1], 1.0)))
            body.append(
                f'<text x="{cx}" y="{ground + 26}" font-size="14" text-anchor="middle" fill="{sch.muted}">{html.escape(label)}</text>'
            )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<rect width="{width}" height="{height}" fill="{sch.bg}"/><defs>{"".join(defs)}</defs>{"".join(body)}</svg>'
    )
    return svg_to_png(svg, width=width, background=sch.bg)[0]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ramp", default="inferno", choices=sorted(RAMPS))
    ap.add_argument("--surface", default="white", choices=sorted(SURFACES))
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "figure-sheet")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"figures-{args.ramp}-{args.surface}.png"
    path.write_bytes(sheet(scheme(args.ramp, args.surface)))
    print(path)


if __name__ == "__main__":
    main()
