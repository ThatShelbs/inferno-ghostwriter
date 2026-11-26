"""Finding the code block right above an image placeholder, and swapping its body."""

from __future__ import annotations

from inferno_ghostwriter.images.codeblocks import code_before, code_blocks, replace_code

POST = (
    "# T\n\n## Plot it\n\nHere is the script:\n\n```python\nimport matplotlib.pyplot as plt\n\nplt.plot([1, 2])\nplt.show()\n```\n\n"
    "{{image:img2}}\n\nThat drew a line.\n\n```bash\nuv run plot.py\n```\n\nSome text.\n\n{{image:img3}}\n"
)


def test_the_block_directly_above_the_placeholder_is_found_with_its_exact_body() -> None:
    block = code_before(POST, "img2")
    assert block is not None
    assert block.language == "python"
    assert block.code == "import matplotlib.pyplot as plt\n\nplt.plot([1, 2])\nplt.show()"


def test_text_between_the_code_and_the_image_means_no_block() -> None:
    assert code_before(POST, "img3") is None  # prose sits between the bash block and the image
    assert code_before(POST, "missing") is None


def test_an_image_first_in_the_post_has_nothing_above_it() -> None:
    assert code_before("{{image:hero}}\n\n```python\nx = 1\n```\n", "hero") is None


def test_every_fenced_block_is_listed_in_order_with_its_language() -> None:
    assert [b.language for b in code_blocks(POST)] == ["python", "bash"]
    assert code_blocks("```\nplain\n```")[0].language == ""


def test_replace_code_swaps_only_the_body() -> None:
    block = code_before(POST, "img2")
    assert block is not None
    out = replace_code(POST, block, "print('hi')\n")
    assert "```python\nprint('hi')\n```\n\n{{image:img2}}" in out
    assert "plt.plot" not in out
    # Everything else is untouched, so the swapped block is still the one above its image.
    assert out.endswith(POST[POST.index("That drew a line.") :])
    again = code_before(out, "img2")
    assert again is not None and again.code == "print('hi')"


def test_an_unclosed_fence_is_read_to_the_end() -> None:
    blocks = code_blocks("```python\nx = 1\ny = 2")
    assert blocks[0].code == "x = 1\ny = 2"
