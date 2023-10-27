import pytest

from migrate import *


@pytest.mark.parametrize(
    "input, expect",
    [
        ("string", ["string"]),
        ([1, 2], [1, 2]),
        ({"a": 1, "b": 2}, [{"a": 1, "b": 2}]),
    ],
)
def test_mklist(input, expect):
    assert mklist(input) == expect


def x(s):
    """helper, turn <mods> or <locaL> XML string into minimal item dict"""
    return {"metadata": f"<xml>{s}</xml>"}


def m(r):
    """helper, alias for Record.get()["metadata"]"""
    return r.get()["metadata"]


# test one abstract, multiple abstracts, no abstracts
@pytest.mark.parametrize(
    "input, expect",
    [
        (x("<mods><abstract>foo</abstract></mods>"), "foo"),
        (x("<mods><abstract>foo</abstract><abstract>bar</abstract></mods>"), "foo"),
        (x("<mods></mods>"), ""),
    ],
)
def test_desc(input, expect):
    r = Record(input)
    assert m(r)["description"] == expect
