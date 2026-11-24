"""How the kit's backdrops and props are rendered in each meme look.

A look changes the treatment (outline weight and color, shading); the colors always come from the image's ``Scheme``
(inferno, magma or viridis), plus a few natural colors that no palette should recolor.
"""

from __future__ import annotations

from dataclasses import dataclass

from inferno_ghostwriter.images.palettes import INK_DARK, Scheme


@dataclass(frozen=True)
class KitStyle:
    """The rendering treatment of one look."""

    id: str
    outline: float = 6.0  # outline width at scale 1 (0 = no outline)
    shading: str = "soft"  # flat | soft | volume | halftone | line | marker
    ink: str = ""  # outline color ("" = the default dark ink)


STYLES: dict[str, KitStyle] = {
    "inferno_flat": KitStyle("inferno_flat", 6.0, "soft", INK_DARK),
    "kawaii": KitStyle("kawaii", 7.0, "soft"),
    "soft_3d": KitStyle("soft_3d", 0.0, "volume"),
    "viridis_lab": KitStyle("viridis_lab", 4.5, "flat", INK_DARK),
    "magma_noir": KitStyle("magma_noir", 5.0, "volume", INK_DARK),
    "corporate_slate": KitStyle("corporate_slate", 3.5, "flat", INK_DARK),
    "retro_comic": KitStyle("retro_comic", 9.0, "halftone", "#111111"),
    "pixel_arcade": KitStyle("pixel_arcade", 6.0, "flat", INK_DARK),
    "whiteboard": KitStyle("whiteboard", 6.0, "marker"),
    "blueprint": KitStyle("blueprint", 4.0, "line"),
    "inferno_robots": KitStyle("inferno_robots", 6.0, "soft", INK_DARK),
}
DEFAULT_STYLE = STYLES["inferno_flat"]


def kit_style(look_id: str | None) -> KitStyle:
    return STYLES.get((look_id or "").strip(), DEFAULT_STYLE)


def blueprint_ground(scheme: Scheme) -> str:
    """The paper a blueprint is drawn on: the scheme's own dark surface, else a deep blueprint blue. Line art is filled
    with it, so shapes stay opaque (a prop behind another never shows through) while reading as linework."""
    return scheme.bg if scheme.dark else "#14396a"
