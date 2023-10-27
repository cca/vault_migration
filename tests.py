import pytest

from migrate import *


@pytest.mark.parametrize(
    "input, expected",
    [
        ("string", ["string"]),
        ([1, 2], [1, 2]),
        ({"a": 1, "b": 2}, [{"a": 1, "b": 2}]),
    ],
)
def test_mklist(input, expected):
    assert mklist(input) == expected
