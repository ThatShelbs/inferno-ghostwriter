import pytest
from pydantic import ValidationError

from inferno_ghostwriter.writer.dials import Dials


def test_image_count_allows_a_top_20_list_with_opener_and_meme() -> None:
    assert Dials(image_count=22).image_count == 22
    with pytest.raises(ValidationError):
        Dials(image_count=23)
