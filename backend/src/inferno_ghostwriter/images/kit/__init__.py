"""The scene kit for staged memes: backdrops, set pieces and props drawn by code in a look's treatment.

Characters are not drawn here: the cast comes from the figure library (``images/figures``) through
``images/memes/cast.py``. See ``docs/image-kit.md``.
"""

from inferno_ghostwriter.images.kit.style import STYLES, KitStyle, kit_style

__all__ = ["STYLES", "KitStyle", "kit_style"]
