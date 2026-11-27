"""The backstop that makes the hands-on charts dial true: retag orphans, add pictures for plotting examples."""

from __future__ import annotations

from inferno_ghostwriter.images.codeblocks import code_before, code_blocks
from inferno_ghostwriter.writer.handson_slots import MAX_EXTRA, MAX_IMAGES, draws_chart, guide, settle_slots
from inferno_ghostwriter.writer.pipeline import ensure_placeholders
from inferno_ghostwriter.writer.schemas import ImageSlot

PLOT = "```python\nimport seaborn as sns\nsns.histplot([1, 2, 3])\n```"
PLAIN = "```python\nprint('no chart')\n```"


def slot(slot_id: str, kind: str = "hands_on_viz", section: int = 0) -> ImageSlot:
    return ImageSlot(slot_id=slot_id, kind=kind, section_index=section, purpose="p", brief="b")  # type: ignore[arg-type]


HERO, MEME = slot("hero", "hero", -1), slot("meme", "meme", 0)


def test_a_hands_on_slot_without_code_above_it_becomes_an_ordinary_chart() -> None:
    post = f"# T\n\n## A\n\nText only.\n\n{{{{image:img2}}}}\n\n## B\n\n{PLOT}\n\n{{{{image:img3}}}}\n"
    _, slots = settle_slots(post, [HERO, slot("img2"), slot("img3"), MEME], "lots")
    kinds = {s.slot_id: s.kind for s in slots}
    assert kinds["img2"] == "chart" and kinds["img3"] == "hands_on_viz"


def test_the_none_level_turns_every_hands_on_slot_into_a_chart() -> None:
    post = f"## A\n\n{PLOT}\n\n{{{{image:img2}}}}\n"
    _, slots = settle_slots(post, [HERO, slot("img2"), MEME], "none")
    assert [s.kind for s in slots if s.slot_id == "img2"] == ["chart"]


def test_a_downgraded_slot_no_longer_names_a_plotting_library() -> None:
    post = f"## A\n\n{PLOT}\n\n{{{{image:img2}}}}\n"
    drawn = ImageSlot(slot_id="img2", kind="hands_on_viz", section_index=0, purpose="Matplotlib histogram", brief="Draw it with matplotlib")
    _, slots = settle_slots(post, [HERO, drawn, MEME], "none")
    out = next(s for s in slots if s.slot_id == "img2")
    assert "matplotlib" not in (out.brief + out.purpose).lower()


def test_lots_gives_each_plotting_example_a_picture_after_it() -> None:
    post = f"# T\n\n## A\n\n{PLOT}\n\nMore.\n\n## B\n\n{PLAIN}\n\n{PLOT}\n"
    text, slots = settle_slots(post, [HERO, MEME], "lots")
    added = [s for s in slots if s.kind == "hands_on_viz"]
    assert len(added) == 2  # the plain print example gets none
    for s in added:
        assert code_before(text, s.slot_id) is not None
    assert slots[0].slot_id == "hero" and slots[-1].slot_id == "meme"


def test_few_and_none_add_nothing() -> None:
    post = f"## A\n\n{PLOT}\n"
    for level in ("few", "none"):
        text, slots = settle_slots(post, [HERO, MEME], level)
        assert text == post and len(slots) == 2


def test_an_example_that_already_has_its_picture_is_left_alone() -> None:
    post = f"## A\n\n{PLOT}\n\n{{{{image:img2}}}}\n"
    text, slots = settle_slots(post, [HERO, slot("img2"), MEME], "lots")
    assert text == post and len(slots) == 3


def test_the_number_of_added_slots_is_capped() -> None:
    post = "## A\n\n" + "\n\n".join([PLOT] * 12) + "\n"
    _, slots = settle_slots(post, [HERO, MEME], "lots")
    assert len([s for s in slots if s.kind == "hands_on_viz"]) == MAX_EXTRA
    full = [slot(f"img{i}", "chart") for i in range(2, MAX_IMAGES)]  # hero + middle images + meme = MAX_IMAGES slots
    _, slots = settle_slots(post, [HERO, *full, MEME], "lots")
    assert len(slots) == MAX_IMAGES


def test_draws_chart_needs_python_and_a_plotting_import() -> None:
    assert [draws_chart(b) for b in code_blocks(f"{PLOT}\n\n{PLAIN}\n\n```js\nplot()\n```")] == [True, False, False]
    pandas_plot = "```python\nimport pandas as pd\ndf.plot(kind='bar')\n```"
    assert draws_chart(code_blocks(pandas_plot)[0])


def test_a_forgotten_hands_on_placeholder_goes_right_after_the_plotting_example() -> None:
    post = f"# T\n\n## A\n\nIntro.\n\n{PLOT}\n\nAfter the code.\n\n## B\n\nOther.\n"
    out = ensure_placeholders(post, [slot("img2")])
    assert code_before(out, "img2") is not None


def test_the_guide_depends_on_the_level() -> None:
    assert "main images" in guide("lots") and "at most 2" in guide("few")
    assert guide("none") == guide("unknown") == "Do not use the `hands_on_viz` kind."
