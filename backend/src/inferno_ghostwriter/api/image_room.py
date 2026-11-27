"""How an image is shown to the author: one ideas board (``ImageRoomOut``) and finalists, whatever its kind."""

from __future__ import annotations

from typing import Any

from inferno_ghostwriter.api.schemas import (
    FinalistOut,
    HandsOnOut,
    ImageFormatOut,
    ImageHistoryOut,
    ImageOut,
    ImageRoomOut,
    PitchOut,
    RemixOut,
    RemixTweakOut,
    SourceOut,
    WordSlotOut,
)
from inferno_ghostwriter.db import ProjectImage
from inferno_ghostwriter.images import handson, kinds
from inferno_ghostwriter.images.body import KIND_OPTIONS
from inferno_ghostwriter.images.memes import FAMILIES, FORMATS, get_format, load_state
from inferno_ghostwriter.images.memes.generate import panel_scores
from inferno_ghostwriter.images.opening.room import load_state as load_opening_state
from inferno_ghostwriter.images.opening.room import ruled_out as opening_ruled_out
from inferno_ghostwriter.images.opening.room import sources_of
from inferno_ghostwriter.images.opening.specs import OpeningBuild
from inferno_ghostwriter.images.opening.styles import STYLES, get_style
from inferno_ghostwriter.images.opening.templates import get_template, slot_texts
from inferno_ghostwriter.images.service import is_meme, meme_spec, remix_dimensions

# Views of the kind table (``images/kinds.py``) for in-body images.
_LISTED = (*kinds.BODY_KINDS, "hands_on_viz")
KIND_LABELS = {k: kinds.label(k) for k in _LISTED}
KIND_USE = {k: kinds.KINDS[k].use for k in _LISTED}
# How many formats the board suggests.
SUGGESTED = 4


def image_url(image: ProjectImage) -> str | None:
    if not image.file_name:
        return None
    return f"/api/images/{image.id}/file?v={image.file_name}"


def image_out(image: ProjectImage, markdown: str | None = None) -> ImageOut:
    """``markdown`` (the post's text) lets a hands-on image say whether its code changed since the picture was made."""
    history = [
        ImageHistoryOut(
            index=i,
            url=f"/api/images/{image.id}/history/{i}/file",
            provider=str(entry.get("provider", "")),
            caption=str(entry.get("caption", "")),
            created_at=str(entry.get("created_at", "")),
        )
        for i, entry in enumerate(image.history)
    ]
    return ImageOut(
        **image.model_dump(
            exclude={"history", "spec", "file_name", "project_id", "anchor", "remix", "ideas", "finalists", "rating", "reference"}
        ),
        url=image_url(image),
        history=history,
        room=room_info(image),
        finalists=finalists_out(image),
        reference_url=f"/api/images/{image.id}/reference/file?v={image.reference}" if image.reference else None,
        remix=remix_info(image),
        remix_dimensions=list(remix_dimensions(image)),
        hands_on=hands_on_info(image, markdown),
        kind_label=kinds.label(image.kind),
    )


def hands_on_info(image: ProjectImage, markdown: str | None) -> HandsOnOut | None:
    """What a code-made image knows about itself: the library, the size of its code and whether the code has changed since."""
    if image.kind != "hands_on_viz" or image.provider != handson.PROVIDER:
        return None
    spec = handson.load_spec(image.spec)
    return HandsOnOut(
        library=str(spec.get("library") or ""),
        lines=int(spec.get("lines") or 0),
        chars=int(spec.get("chars") or 0),
        stale=handson.is_stale(image.spec, markdown, image.slot_id) if markdown is not None else False,
    )


def finalists_out(image: ProjectImage) -> list[FinalistOut]:
    return [
        FinalistOut(
            index=i,
            # The file name is in the URL because a redraw replaces a finalist in place and the file is cached for good.
            url=f"/api/images/{image.id}/finalists/{i}/file?v={f.get('file_name') or ''}",
            label=str(f.get("label") or ""),
            score=f.get("score"),
            reads_as=str(f.get("reads_as") or ""),
            current=bool(f.get("file_name")) and f.get("file_name") == image.file_name,
        )
        for i, f in enumerate(image.finalists or [])
    ]


def remix_info(image: ProjectImage) -> RemixOut | None:
    state = image.remix or {}
    if not state.get("tweaks") and not state.get("brainstormed"):
        return None
    return RemixOut(
        weakness=str(state.get("weakness") or ""),
        improvements=[str(i) for i in state.get("improvements") or []],
        fresh_angle=str(state.get("fresh_angle") or ""),
        tweaks=[
            RemixTweakOut(dimension=str(t.get("dimension", "")), id=str(t.get("id", "")), label=str(t.get("label", "")))
            for t in state.get("tweaks") or []
        ],
        brainstormed=bool(state.get("brainstormed")),
    )


def _score(total: Any) -> float | None:
    """A stored score on the 0-10 scale (older openers stored 4-40, older memes 6-30 or 4-40)."""
    try:
        value = float(total)
    except (TypeError, ValueError):
        return None
    if value < 0:
        return 0.0
    return round(value if value <= 10 else value / 4, 1)


def room_info(image: ProjectImage) -> ImageRoomOut | None:
    """The image's ideas board. Every image but a hands-on data viz has one, even with no pitches yet (the board then
    offers to pitch some). On an upload the stored pitches stay pickable, but none is on show and it has no words."""
    if image.kind == "hands_on_viz":
        return None
    if image.kind == "hero" and (state := load_opening_state(image.spec)) is not None:
        room = _opening_room(image, state)
    elif image.kind == "meme" and (state := load_state(image.spec)) is not None:
        room = _meme_room(state)
    elif image.kind in ("hero", "meme"):
        room = ImageRoomOut(room="opening" if image.kind == "hero" else "meme", format="", format_label="")
    else:
        room = _body_room(image)
    _add_pictures(image, room)
    if image.provider == "upload":
        for pitch in room.pitches:
            pitch.current = False
        room.why, room.slots, room.fallback_from = "", [], ""
    return room


def _idea_key(text: str) -> str:
    return " ".join(text.split()).casefold()


def _add_pictures(image: ProjectImage, room: ImageRoomOut) -> None:
    """Show each pitch's picture when a version of the image drew it (restoring that version costs no call), and
    suggest the formats of the best pitches not tried yet."""
    drawn: dict[str, int] = {}
    for i, entry in enumerate(image.history or []):
        key = _idea_key(str(entry.get("idea") or ""))
        if key:
            drawn[key] = i  # the newest version of each idea wins
    for pitch in room.pitches:
        version = drawn.get(_idea_key(pitch.hook or pitch.concept))
        if version is not None:
            pitch.version = version
            pitch.thumb_url = f"/api/images/{image.id}/history/{version}/file"
    ranked = sorted(
        (p for p in room.pitches if not p.ruled_out),
        key=lambda p: (p.tried, -(p.score if p.score is not None else 0), -p.batch, p.index),
    )
    room.suggested = list(dict.fromkeys(p.format for p in ranked if p.format != room.format))[:SUGGESTED]


def _opening_room(image: ProjectImage, state: dict[str, Any]) -> ImageRoomOut:
    chosen, tried = state.get("chosen"), set(state.get("tried") or [])
    pitches = []
    for i, entry in enumerate(state.get("concepts") or []):
        style = get_style(str(entry.get("style", "")))
        if style is None:
            continue
        panel = entry.get("panel") or {}
        pitches.append(
            PitchOut(
                index=i,
                format=style.id,
                format_label=style.label,
                hook=str(entry.get("hook") or ""),
                concept=str(entry.get("concept") or ""),
                anchor=str(entry.get("anchor") or ""),
                anchored=bool(entry.get("anchored", True)),
                reads_as=str(entry.get("reads_as") or ""),
                score=_score(panel.get("total")) if "total" in panel else None,
                note=str(panel.get("note") or ""),
                ruled_out=opening_ruled_out(entry),
                tried=i in tried,
                current=i == chosen,
                batch=int(entry.get("batch") or 0),
                edited=bool(entry.get("edited")),
            )
        )
    style = get_style(str(state.get("style") or ""))
    slots: list[WordSlotOut] = []
    if is_meme(image):
        inner = load_state(meme_spec(image)) or {}
        slots = _meme_slots(inner)
    else:
        template = get_template(str(state.get("template") or ""))
        if template is not None and state.get("build"):
            build = OpeningBuild.model_validate(state["build"])
            slots = [
                WordSlotOut(name=name, hint=hint, text=text, max_chars=limit, optional=name != "headline")
                for name, hint, text, limit in slot_texts(template, build)
            ]
    failed = get_style(str(state.get("fallback_from") or ""))
    return ImageRoomOut(
        room="opening",
        format=style.id if style else "",
        format_label=style.label if style else "",
        why=str((state.get("review") or {}).get("why") or state.get("summary") or ""),
        ideas_left=sum(1 for p in pitches if not p.tried and not p.ruled_out),
        fallback_from=failed.label if failed else "",
        pitches=pitches,
        slots=slots,
        sources=[SourceOut(**s) for s in sources_of(state)],
    )


def _meme_slots(state: dict[str, Any]) -> list[WordSlotOut]:
    fmt = get_format(str(state.get("format", "")))
    words = {str(t.get("slot")): str(t.get("text", "")) for t in (state.get("build") or {}).get("texts") or []}
    return [
        WordSlotOut(name=s.name, hint=s.hint, text=words.get(s.name, ""), max_chars=s.max_chars, optional=s.optional)
        for s in (fmt.slots if fmt and state.get("build") else ())
    ]


def _meme_room(state: dict[str, Any]) -> ImageRoomOut:
    concepts = state.get("concepts") or []
    chosen = state.get("chosen")
    fmt = get_format(str(state.get("format", "")))
    tried = set(state.get("tried") or [])
    scores = panel_scores(state, len(concepts))
    panel = state.get("panel") or {}
    notes = panel.get("notes") or []
    vetoed = set(panel.get("vetoed") or [])
    pitches = [
        PitchOut(
            index=i,
            format=pitch_fmt.id,
            format_label=pitch_fmt.name,
            hook=str(c.get("premise", "")),
            concept=str(c.get("callback", "")),
            words=[str(t.get("text", "")).strip() for t in c.get("texts") or [] if str(t.get("text", "")).strip()],
            anchor=str(c.get("anchor") or ""),
            anchored=bool(c.get("anchored", True)),
            reads_as=str(c.get("reads_as") or ""),
            score=_score(scores[i]) if scores else None,
            note=str(notes[i]) if i < len(notes) else "",
            ruled_out=i in vetoed,
            tried=i in tried,
            current=i == chosen,
            batch=int(c.get("batch") or 0),
            edited=bool(c.get("edited")),
        )
        for i, c in enumerate(concepts)
        if (pitch_fmt := get_format(str(c.get("format", ""))))
    ]
    failed = get_format(str(state.get("fallback_from", "")))
    return ImageRoomOut(
        room="meme",
        format=fmt.id if fmt else "",
        format_label=fmt.name if fmt else "",
        why=str((state.get("review") or {}).get("why") or state.get("why") or ""),
        ideas_left=sum(1 for p in pitches if not p.tried and not p.ruled_out),
        fallback_from=failed.name if failed else "",
        pitches=pitches,
        slots=_meme_slots(state),
    )


def _body_room(image: ProjectImage) -> ImageRoomOut:
    ideas = image.ideas or {}
    chosen, tried = ideas.get("chosen"), set(ideas.get("tried") or [])
    pitches = [
        PitchOut(
            index=i,
            format=str(c.get("kind") or image.kind),
            format_label=KIND_LABELS.get(str(c.get("kind") or image.kind), str(c.get("kind") or image.kind)),
            hook=str(c.get("hook") or ""),
            concept=str(c.get("concept") or ""),
            anchor=str(c.get("anchor") or ""),
            anchored=bool(c.get("anchored", True)),
            reads_as=str(c.get("reads_as") or ""),
            tried=i in tried,
            current=i == chosen,
            batch=int(c.get("batch") or 0),
            edited=bool(c.get("edited")),
        )
        for i, c in enumerate(ideas.get("concepts") or [])
    ]
    kind = "chart" if image.provider == "vega-lite" else image.kind
    return ImageRoomOut(
        room="body",
        format=kind,
        format_label=KIND_LABELS.get(kind, kind),
        ideas_left=sum(1 for p in pitches if not p.tried),
        pitches=pitches,
    )


def image_formats(room: str, kind: str = "") -> list[ImageFormatOut]:
    """What an image's room can switch to: meme formats, opening styles (plus the meme bank) or ways to draw it."""
    memes = [ImageFormatOut(id=f.id, label=f.name, group=FAMILIES[f.family], when_to_use=f.when_to_use) for f in FORMATS]
    if room == "meme":
        return memes
    if room == "opening":
        styles = [
            ImageFormatOut(id=s.id, label=s.label, group="Opening styles", when_to_use=s.when_to_use) for s in STYLES if s.id != "meme"
        ]
        return styles + memes
    kinds = KIND_OPTIONS.get(kind, tuple(KIND_LABELS))
    return [ImageFormatOut(id=k, label=KIND_LABELS.get(k, k), group="Ways to draw it", when_to_use=KIND_USE.get(k, "")) for k in kinds]
