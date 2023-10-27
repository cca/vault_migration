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


# Description
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


# Additional Descriptions


# Title
@pytest.mark.parametrize(
    "input, expect",
    [
        ({"name": "foo", **x("")}, "foo"),
        (
            x(""),
            "Untitled",
        ),
    ],
)
def test_title(input, expect):
    r = Record(input)
    assert m(r)["title"] == expect


# Additional Titles
@pytest.mark.parametrize(
    "input, expect",
    [
        (  # subtitle
            x("<mods><titleInfo><subTitle>foo</subTitle></titleInfo></mods>"),
            [{"title": "foo", "type": {"id": "subtitle"}}],
        ),
        (  # two titles
            x(
                "<mods><titleInfo><title>foo</title></titleInfo><titleInfo><title>bar</title></titleInfo></mods>"
            ),
            [{"title": "bar", "type": {"id": "other"}}],
        ),
        (  # alt title & a subtitle
            x(
                '<mods><titleInfo><title>foo</title><subTitle>bar</subTitle></titleInfo><titleInfo type="alternative"><title>baz</title></titleInfo></mods>'
            ),
            [
                {"title": "bar", "type": {"id": "subtitle"}},
                {"title": "baz", "type": {"id": "alternative-title"}},
            ],
        ),
        (  # other title types: translated, other
            x(
                '<mods><titleInfo><title>a</title></titleInfo><titleInfo type="translated"><title>foo</title></titleInfo><titleInfo type="descriptive"><title>bar</title></titleInfo></mods>'
            ),
            [
                {"title": "foo", "type": {"id": "translated-title"}},
                {"title": "bar", "type": {"id": "other"}},
            ],
        ),
    ],
)
def test_addl_titles(input, expect):
    r = Record(input)
    assert m(r)["additional_titles"] == expect
