"""Blocks the brief shows must reach the post exactly, and are put back when they go missing."""

from __future__ import annotations

from inferno_ghostwriter.writer import verbatim

BRIEF = """Write about my chart experiments.

Here is the prompt I used:

```text
Goal: build a chart.
Source: the vega movies dataset.
```

Then it returned this:

```python
import altair as alt

alt.Chart().show()
```

> first quoted line of the output
> second quoted line of the output
> third quoted line of the output
"""


def test_the_briefs_fenced_and_quoted_blocks_are_found_with_their_lead_ins() -> None:
    blocks = verbatim.brief_blocks(BRIEF)
    assert [b.language for b in blocks] == ["text", "python", ""]
    assert blocks[0].lead_in == "Here is the prompt I used:" and blocks[1].lead_in == "Then it returned this:"
    assert blocks[2].quoted and blocks[2].text.startswith("first quoted line")


def test_short_snippets_are_not_forced() -> None:
    assert verbatim.brief_blocks("Use `x` and\n\n```\nls\n```\n") == []


def test_exact_blocks_are_present_and_a_paraphrase_is_missing() -> None:
    post = "# T\n\nHere is the prompt I used:\n\n```text\nGoal: build a chart.\nSource: the vega movies dataset.\n```\n"
    missing = verbatim.missing_blocks(post, verbatim.brief_blocks(BRIEF))
    assert [b.language for b in missing] == ["python", ""]
    assert verbatim.missing_blocks(post.replace("vega movies", "vega film"), verbatim.brief_blocks(BRIEF))[0].language == "text"


def test_the_editor_is_told_which_blocks_are_missing() -> None:
    note = verbatim.format_missing("# T\n\nNothing.\n", BRIEF)
    assert "character for character" in note and "alt.Chart().show()" in note
    assert verbatim.format_missing(verbatim.restore("# T\n\nNothing.\n", BRIEF), BRIEF) == ""


def test_restore_puts_a_block_back_after_its_lead_in_exactly() -> None:
    post = "# T\n\n## The run\n\nThen it returned this:\n\nA loose summary of the code.\n\n## Wrap up\n\nBye.\n"
    out = verbatim.restore(post, BRIEF)
    assert verbatim.missing_blocks(out, verbatim.brief_blocks(BRIEF)) == []
    assert out.index("Then it returned this:") < out.index("import altair as alt") < out.index("A loose summary")
    # The prompt had no lead-in in the post, so it lands before the closing section.
    assert out.index("Goal: build a chart.") < out.index("## Wrap up")
    assert verbatim.restore(out, BRIEF) == out
