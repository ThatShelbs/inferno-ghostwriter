"""The poses every style draws, with what each is for (the prompt catalog reads these)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PoseInfo:
    label: str
    use: str
    expression: str  # the default expression
    looks_back: bool = False  # body faces forward, head turned back


POSES: dict[str, PoseInfo] = {
    "standing": PoseInfo("standing", "a relaxed stand, arms down; the default cast member", "neutral"),
    "pointing": PoseInfo("pointing", "arm straight out pointing ahead (at a chart, a label, another figure)", "focused"),
    "looking_back": PoseInfo(
        "looking back over the shoulder",
        "walking one way, head turned back admiring something behind (the distracted boyfriend)",
        "impressed",
        looks_back=True,
    ),
    "nervous": PoseInfo("sweating", "wiping a sweaty brow with a cloth, under pressure (the two-buttons sweat)", "nervous"),
    "flashlight": PoseInfo("holding a flashlight", "shining a flashlight ahead; the beam starts at the `lens` anchor", "focused"),
    "laptop": PoseInfo("at a laptop", "typing at a laptop on a small standing desk in front", "focused"),
    "shrug": PoseInfo("shrugging", "both palms up, who knows", "smug"),
    "arms_crossed": PoseInfo("arms crossed", "arms folded, unimpressed or confident", "smug"),
    "nope": PoseInfo(
        "gesturing away",
        "head turned away, palm raised to block (Drake 'nope', the top panel)",
        "disgusted",
        looks_back=True,
    ),
    "yep": PoseInfo("approving point", "pointing up and forward with a pleased smile (Drake 'yep', the bottom panel)", "smug"),
    "walking": PoseInfo("walking", "mid-stride, arms swinging", "neutral"),
}
