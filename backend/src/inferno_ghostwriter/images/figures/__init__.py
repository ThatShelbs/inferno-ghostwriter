"""A small library of polished, simple figures that Claude-authored SVG places with ``<use href="#fig-...">``.

Three styles, the same eleven poses each:

* ``bean``: flat rounded figures with dot eyes, for editorial scenes and explainers.
* ``line``: clean line-art people with expressive faces, for meme re-creations (outfits and hair vary).
* ``ghost``: the house mascot, a friendly spectral ghost.

A figure id reads ``fig-<style>-<pose>[-<expression>][-<outfit>][-<hair>][-left][-<tag>]``; :func:`figure` builds the
symbol for one, :func:`defs_for` the ``<defs>`` for a set of ids (what Claude's SVG references), :data:`CATALOG`
describes every base id and :func:`catalog_text` is the block a drawing prompt reads.

Every symbol's viewBox has its bottom edge on the ground under the feet and x = 0 on the figure's centre line, so a
figure placed with ``<use x y width height>`` (keeping the viewBox's aspect) stands on ``y + height``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from inferno_ghostwriter.images.figures import bean, ghost, line, robot
from inferno_ghostwriter.images.figures.base import SKIN_TONES, FigureColors, Point, SvgSymbol, fmt
from inferno_ghostwriter.images.figures.faces import EXPRESSIONS
from inferno_ghostwriter.images.figures.poses import POSES

__all__ = [
    "CATALOG",
    "EXPRESSIONS",
    "HAIRS",
    "OUTFITS",
    "POSES",
    "SKIN_TONES",
    "STYLES",
    "FigureColors",
    "FigureRef",
    "SvgSymbol",
    "catalog_text",
    "defs_for",
    "figure",
    "figure_id",
    "ids_in",
    "inject",
    "parse_id",
]

STYLES: dict[str, str] = {
    "bean": "flat rounded figure, round head, two white dot eyes, no outline; body in `shirt`",
    "line": "line-art person with an expressive face, ink outlines, flat fills; for memes",
    "ghost": "the house mascot: a friendly spectral ghost with rosy cheeks, floating over its shadow",
    "robot": "a friendly house robot: glossy white shell, dark visor with a glowing cyan face, a glowing chest core",
}
OUTFITS = line.OUTFITS
HAIRS = line.HAIRS
_VIEW_BOX = {"bean": bean.VIEW_BOX, "line": line.VIEW_BOX, "ghost": ghost.VIEW_BOX, "robot": robot.VIEW_BOX}
_TAG = re.compile(r"^[a-z0-9]{1,16}$")
_RESERVED = {"left", "right", *EXPRESSIONS, *OUTFITS, *HAIRS, *STYLES, *POSES}
_ID = re.compile(r"#(fig-[a-z0-9_-]+)")


@dataclass(frozen=True)
class FigureRef:
    """A parsed figure id."""

    style: str
    pose: str
    expression: str | None = None
    outfit: str | None = None
    hair: str | None = None
    facing: str = "right"
    tag: str | None = None

    @property
    def id(self) -> str:
        return figure_id(
            self.style, self.pose, expression=self.expression, outfit=self.outfit, hair=self.hair, facing=self.facing, tag=self.tag
        )


def figure_id(
    style: str,
    pose: str,
    *,
    expression: str | None = None,
    outfit: str | None = None,
    hair: str | None = None,
    facing: str = "right",
    tag: str | None = None,
) -> str:
    parts = ["fig", style, pose]
    if expression and expression != POSES[pose].expression:
        parts.append(expression)
    if outfit and outfit != "tee":
        parts.append(outfit)
    if hair and hair != "short":
        parts.append(hair)
    if facing == "left":
        parts.append("left")
    if tag:
        if not _TAG.match(tag) or tag in _RESERVED:
            raise ValueError(f"A figure tag is 1-16 lowercase letters or digits and not a reserved word: {tag!r}")
        parts.append(tag)
    return "-".join(parts)


def parse_id(fid: str) -> FigureRef:
    """Read a figure id; raises ``ValueError`` for anything that is not one."""
    tokens = fid.split("-")
    if len(tokens) < 3 or tokens[0] != "fig" or tokens[1] not in STYLES or tokens[2] not in POSES:
        raise ValueError(f"Not a figure id: {fid!r}")
    style, pose = tokens[1], tokens[2]
    ref: dict[str, str] = {}
    for tok in tokens[3:]:
        if tok == "left" and "facing" not in ref:
            ref["facing"] = "left"
        elif tok in EXPRESSIONS and "expression" not in ref:
            ref["expression"] = tok
        elif style == "line" and tok in OUTFITS and "outfit" not in ref:
            ref["outfit"] = tok
        elif style == "line" and tok in HAIRS and "hair" not in ref:
            ref["hair"] = tok
        elif _TAG.match(tok) and tok not in _RESERVED and "tag" not in ref:
            ref["tag"] = tok
        else:
            raise ValueError(f"Not a figure id: {fid!r} (unexpected {tok!r})")
    return FigureRef(
        style,
        pose,
        expression=ref.get("expression"),
        outfit=ref.get("outfit"),
        hair=ref.get("hair"),
        facing=ref.get("facing", "right"),
        tag=ref.get("tag"),
    )


def figure(
    style: str,
    pose: str,
    *,
    colors: FigureColors | None = None,
    expression: str | None = None,
    facing: str = "right",
    outfit: str | None = None,
    hair: str | None = None,
    tag: str | None = None,
) -> SvgSymbol:
    """The symbol for one figure. ``outfit`` (tee, plaid, dress, hoodie, jacket) and ``hair`` (short, long, messy,
    bun, bald) apply to the ``line`` style; ``tag`` only makes the id unique (two differently colored figures in
    the same pose)."""
    if style not in STYLES:
        raise ValueError(f"Unknown figure style {style!r}")
    if pose not in POSES:
        raise ValueError(f"Unknown pose {pose!r}")
    if expression is not None and expression not in EXPRESSIONS:
        raise ValueError(f"Unknown expression {expression!r}")
    if outfit is not None and outfit not in OUTFITS:
        raise ValueError(f"Unknown outfit {outfit!r}")
    if hair is not None and hair not in HAIRS:
        raise ValueError(f"Unknown hair {hair!r}")
    c = colors or FigureColors()
    info = POSES[pose]
    defaults = {"ghost": ghost.DEFAULTS, "bean": bean.DEFAULTS, "robot": robot.DEFAULTS}.get(style, {})
    expr = expression or defaults.get(pose, info.expression)
    f_head = -1 if info.looks_back else 1
    sid = figure_id(style, pose, expression=expression, outfit=outfit, hair=hair, facing=facing, tag=tag)
    if style == "line":
        body, anchors = line.draw(pose, c, expr, sid, outfit=outfit or "tee", hair=hair or "short", f_head=f_head)
    elif style == "ghost":
        body, anchors = ghost.draw(pose, c, expr, sid, f_head=f_head)
    elif style == "robot":
        body, anchors = robot.draw(pose, c, expr, sid, f_head=f_head)
    else:
        body, anchors = bean.draw(pose, c, expr, sid, f_head=f_head)
    vb = _VIEW_BOX[style]
    if facing == "left":
        body = f'<g transform="scale(-1 1)">{body}</g>'
        anchors = {k: (-x, y) for k, (x, y) in anchors.items()}
    rounded: dict[str, Point] = {k: (round(x, 1), round(y, 1)) for k, (x, y) in anchors.items()}
    return SvgSymbol(sid, vb, body, rounded)


def defs_for(ids: Iterable[str], colors: FigureColors | Mapping[str, FigureColors] | None = None) -> str:
    """``<defs>`` holding a symbol for every figure id in ``ids`` (duplicates once). ``colors`` is one set for all,
    or a mapping from id to colors (ids it lacks get the defaults). Raises ``ValueError`` on an unknown id."""
    symbols: list[str] = []
    seen: set[str] = set()
    for fid in ids:
        if fid in seen:
            continue
        seen.add(fid)
        ref = parse_id(fid)
        c = colors.get(fid) if isinstance(colors, Mapping) else colors
        sym = figure(
            ref.style,
            ref.pose,
            colors=c,
            expression=ref.expression,
            facing=ref.facing,
            outfit=ref.outfit,
            hair=ref.hair,
            tag=ref.tag,
        )
        # The symbol keeps the id as written, so a reference that spells a default expression still resolves.
        symbols.append(sym.svg.replace(sym.id, fid))
    return f"<defs>{''.join(symbols)}</defs>"


def ids_in(svg: str) -> list[str]:
    """Figure ids an SVG references, in order of first use, keeping only valid ones."""
    out: list[str] = []
    for fid in _ID.findall(svg):
        if fid in out:
            continue
        try:
            parse_id(fid)
        except ValueError:
            continue
        out.append(fid)
    return out


def inject(svg: str, colors: FigureColors | Mapping[str, FigureColors] | None = None) -> str:
    """Claude's SVG with the ``<defs>`` for every figure it references inserted after the root tag."""
    ids = ids_in(svg)
    if not ids:
        return svg
    m = re.search(r"<svg\b[^>]*>", svg)
    if not m:
        return svg
    return svg[: m.end()] + defs_for(ids, colors) + svg[m.end() :]


def _describe(style: str, pose: str) -> str:
    sym = figure(style, pose)
    x, y, w, h = sym.view_box
    anchors = ", ".join(f"{k} ({fmt(ax)},{fmt(ay)})" for k, (ax, ay) in sym.anchors.items() if k not in ("top",))
    info = POSES[pose]
    return f"{STYLES[style].split(';')[0]}, {info.label}: {info.use}. viewBox {fmt(x)} {fmt(y)} {fmt(w)} {fmt(h)}; anchors {anchors}"


CATALOG: dict[str, str] = {f"fig-{style}-{pose}": _describe(style, pose) for style in STYLES for pose in POSES}


def catalog_text(styles: Iterable[str] = tuple(STYLES)) -> str:
    """The figure library as a drawing prompt reads it."""
    chosen = [s for s in styles if s in STYLES]
    lines = [
        'Figures: place ready-made figures with <use href="#ID" x y width height/>; never draw people or characters yourself.',
        "Ids: fig-<style>-<pose>[-<expression>][-<outfit>][-<hair>][-left][-<tag>]. Add -left to face left; a short tag "
        "(letters/digits) makes a second copy you can color differently.",
        "Each viewBox's bottom edge is the ground under the feet and x = 0 is the figure's centre: keep the aspect "
        "(height = width * vbH / vbW) and set y = ground - height. Anchors are points in viewBox units (a beam starts at `lens`).",
        f"Poses: {', '.join(POSES)}.",
        f"Expressions: {'; '.join(f'{k} ({v.label})' for k, v in EXPRESSIONS.items())}.",
    ]
    if "line" in chosen:
        lines.append(f"Line outfits: {', '.join(OUTFITS)} (tee default). Line hair: {', '.join(HAIRS)} (short default).")
    for style in chosen:
        lines.append(f"Style {style}: {STYLES[style]}. viewBox {' '.join(fmt(v) for v in _VIEW_BOX[style])}.")
    return "\n".join(lines)
