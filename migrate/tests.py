import pytest

from names import parse_name
from record import Record
from utils import mklist


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


# Name
@pytest.mark.parametrize(
    "input, expect",
    [
        ("Phetteplace, Eric", {"family_name": "Phetteplace", "given_name": "Eric"}),
        ("Stephen Beal", {"family_name": "Beal", "given_name": "Stephen"}),
        (
            "Phetteplace, Eric, 1984-",
            {"family_name": "Phetteplace", "given_name": "Eric"},
        ),
        ("Joyce, James, 1882-1941", {"family_name": "Joyce", "given_name": "James"}),
        (
            "CCA Alumni Association",
            {"name": "CCA Alumni Association"},
        ),
        (
            "CCA Student Council",
            {"name": "CCA Student Council"},
        ),
        (
            "Teri Dowling, John Smith, Annemarie Haar",
            [
                {"family_name": "Dowling", "given_name": "Teri"},
                {"family_name": "Smith", "given_name": "John"},
                {"family_name": "Haar", "given_name": "Annemarie"},
            ],
        ),
        (
            "Maria Rodriguez; Natalie Portman; Audre Lorde",
            [
                {"family_name": "Rodriguez", "given_name": "Maria"},
                {"family_name": "Portman", "given_name": "Natalie"},
                {"family_name": "Lorde", "given_name": "Audre"},
            ],
        ),
        (
            "Carland, Tammy Rae + Hanna, Kathleen",
            [
                {"family_name": "Carland", "given_name": "Tammy Rae"},
                {"family_name": "Hanna", "given_name": "Kathleen"},
            ],
        ),
        (
            "California College of Arts and Crafts (Oakland, Calif.)",
            {"name": "California College of Arts and Crafts (Oakland, Calif.)"},
        ),
        (
            "CCAC Libraries; CCA Sputnik",
            [{"name": "CCAC Libraries"}, {"name": "CCA Sputnik"}],
        ),
    ],
)
def test_parse_name(input, expect):
    assert parse_name(input) == expect


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
@pytest.mark.parametrize(
    "input, expect",
    [
        (x("<mods><abstract>foo</abstract></mods>"), []),
        (  # second abstract
            x("<mods><abstract>foo</abstract><abstract>bar</abstract></mods>"),
            [{"type": "abstract", "description": "bar"}],
        ),
        (  # note
            x("<mods><noteWrapper><note>foo</note></noteWrapper></mods>"),
            [{"type": "other", "description": "foo"}],
        ),
    ],
)
def test_addl_desc(input, expect):
    r = Record(input)
    assert m(r)["additional_descriptions"] == expect


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


# Resource Type
@pytest.mark.parametrize(
    "input, expect",
    [
        (  # regular mapping
            x(
                "<mods><typeOfResourceWrapper><typeOfResource>Event documentation</typeOfResource></typeOfResourceWrapper></mods>"
            ),
            {"id": "event"},
        ),
        (  # multiple <typeOfResource> elements
            x(
                "<mods><typeOfResourceWrapper><typeOfResource>moving image</typeOfResource><typeOfResource>mixed material</typeOfResource></typeOfResourceWrapper></mods>"
            ),
            {"id": "image"},
        ),
        (  # default to publication
            x("<mods></mods>"),
            {"id": "publication"},
        ),
    ],
)
def test_type(input, expect):
    r = Record(input)
    assert m(r)["resource_type"] == expect
