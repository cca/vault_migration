import pytest
import xmltodict
from edtf import text_to_edtf
from names import parse_name
from record import Record
from subjects import TYPES, Subject, find_subjects, subjects_from_xmldict
from utils import (
    get_url,
    mklist,
    syllabus_collection_uuid,
    to_edtf,
    visual_mime_type_sort,
)


@pytest.mark.parametrize(
    "input, expect",
    [
        ("not a url", None),
        ("https://example.com", "https://example.com"),
        (
            "//www.youtube.com/v/video_id_here",
            "https://www.youtube.com/v/video_id_here",
        ),
    ],
)
def test_get_url(input, expect):
    assert get_url(input) == expect


@pytest.mark.parametrize(
    "input, expect",
    [
        ("string", ["string"]),
        ([1, 2], [1, 2]),
        ({"a": 1, "b": 2}, [{"a": 1, "b": 2}]),
        (None, []),
    ],
)
def test_mklist(input, expect):
    assert mklist(input) == expect


@pytest.mark.parametrize(  # ensure edtf library works with our date formats
    "input, expect",
    [
        # different types of ISO 8601 dates
        ("1996", "1996"),
        ("1984-11", "1984-11"),
        ("2020-03-14", "2020-03-14"),
        # format of item.dateCreated string
        ("2019-04-25T16:22:52.704-07:00", "2019-04-25"),
        # date range
        ("1996-1997", "1996/1997"),
    ],
)
def test_edtf(input, expect):
    assert text_to_edtf(input) == expect


# test our to_edtf utility
@pytest.mark.parametrize(
    "input, expect",
    [
        ("1996", "1996"),
        ("1984-01", "1984-01"),
        ("1984-01-01", "1984-01-01"),
        ("Unparseable", None),
        # map EDTF season to approx month
        ("Summer 2020", "2020-05"),
        ("2024 Fall", "2024-08"),
    ],
)
def test_to_edtf(input, expect):
    assert to_edtf(input) == expect


@pytest.mark.parametrize(
    "input, expect",
    [
        ([], []),
        ([{"filename": "file.py"}], [{"filename": "file.py"}]),
        (
            [{"folder": "binary.zip"}, {"filename": "img.gif"}],
            [{"filename": "img.gif"}, {"folder": "binary.zip"}],
        ),
        (
            [{"filename": "print.pdf"}, {"filename": "word.docx"}],
            [{"filename": "print.pdf"}, {"filename": "word.docx"}],
        ),
        (
            [
                {"filename": "image.jpg"},
                {"filename": "highres.tiff"},
                {"filename": "archive.tgz"},
            ],
            [
                {"filename": "highres.tiff"},
                {"filename": "image.jpg"},
                {"filename": "archive.tgz"},
            ],
        ),
        (
            [
                {"filename": "unknown"},
                {"filename": "plain.txt"},
                {"filename": "img.tiff"},
                {"filename": "img.webp"},
                {"filename": "doc.pdf"},
                {"filename": "movie.mp4"},
                {"filename": "song.mp3"},
                {"filename": "app.exe"},
                {"folder": "zip.zip"},
            ],
            [
                {"filename": "img.tiff"},
                {"filename": "doc.pdf"},
                {"filename": "movie.mp4"},
                {"filename": "song.mp3"},
                {"folder": "zip.zip"},
                {"filename": "unknown"},
                {"filename": "plain.txt"},
                {"filename": "img.webp"},
                {"filename": "app.exe"},
            ],
        ),
    ],
)
def test_visual_mime_type_sort(input, expect):
    assert sorted(input, key=visual_mime_type_sort) == expect


def x(s):
    """helper, turn <mods> or <locaL> XML string into minimal item dict"""
    return {"metadata": f"<xml>{s}</xml>"}


def m(r):
    """helper, alias for Record.get()["metadata"]"""
    return r.get()["metadata"]


# Archives Series
@pytest.mark.parametrize(
    "input, expect",
    [
        # no series
        (x("<mods></mods>"), {}),
        # wrapper but no series
        (x("<local><archivesWrapper></archivesWrapper>></local>"), {}),
        (
            x(
                "<local><archivesWrapper><series>I. Administrative Materials</series><subseries>5. Faculty and Staff Files</subseries></archivesWrapper>></local>"
            ),
            {
                "cca:archives_series": {
                    "series": "I. Administrative Materials",
                    "subseries": "5. Faculty and Staff Files",
                }
            },
        ),
        (
            x(
                "<local><archivesWrapper><series>VIII. Periodicals and Other Publications</series><subseries>4. Yearbooks</subseries></archivesWrapper></local>"
            ),
            {
                "cca:archives_series": {
                    "series": "VIII. Periodicals and Other Publications",
                    "subseries": "4. Yearbooks",
                }
            },
        ),
    ],
)
def test_archives_series(input, expect):
    r = Record(input)
    # can't use m(r) helper because custom_fields live outside metadata
    assert r.get()["custom_fields"] == expect


@pytest.mark.parametrize(
    "input, expect",
    [
        (
            {
                "collection": {
                    "name": "Libraries",
                    "uuid": "6b755832-4070-73d2-77b3-3febcc1f5fad",
                },
                "metadata": "<xml/>",
            },
            # pass set() constructor a list b/c it breaks string iterables into set of characters
            set(["libraries"]),
        ),
        (
            {
                "collection": {
                    "name": "Animation Program",
                    "uuid": "66558697-71c5-43a0-b7b3-f778b42c7cd9",
                },
                "metadata": "<xml/>",
            },
            set(["animation"]),
        ),
        (
            {
                "collection": {"name": "Unmapped Collection", "uuid": "Don Quixote"},
                "metadata": "<xml/>",
            },
            set(),
        ),
        (
            {"metadata": "<xml/>", "title": "no collection info"},
            set(),
        ),
        # Libraries subcollections, Mudflats
        (
            x(
                '<mods><relatedItem type="host"><title>Robert Sommer Mudflats Collection</title></relatedItem></mods>'
            ),
            set(["libraries-mudflats"]),
        ),
        (
            x(
                '<mods><relatedItem type="host"><title>Capp Street Project Archive</title></relatedItem><relatedItem type="other">This is ignored.</relatedItem></mods>'
            ),
            set(["libraries-capp-street"]),
        ),
        (
            x('<mods><relatedItem type="part">This is ignored.</relatedItem></mods>'),
            set(),
        ),
    ],
)
def test_communities(input, expect):
    r = Record(input)
    assert r.communities == expect


# TODO test course
@pytest.mark.parametrize(
    "input, expect",
    [
        # No course info
        (x("<mods></mods>"), None),
        # Course info with department and term
        (
            x(
                "<local><courseInfo><department>DESGN</department><semester>Fall 2023</semester></courseInfo></local>"
            ),
            {
                "department": "",
                "department_code": "DESGN",
                "instructors_string": "",
                "section": "",
                "section_calc_id": "",
                "term": "Fall 2023",
                "title": "",
            },
        ),
        # Course info with only department
        (
            x("<local><courseInfo><department>FINAR</department></courseInfo></local>"),
            {
                "department": "",
                "department_code": "FINAR",
                "instructors_string": "",
                "section": "",
                "section_calc_id": "",
                "term": "",
                "title": "",
            },
        ),
        # Complete course info
        (
            x(
                """<local><courseInfo>
                <department>FINAR</department>
                <faculty>Frida Kahlo</faculty>
                <section>FINAR-1000-1</section>
                <semester>Fall 2024</semester>
                <course>The Finest Arts</course>
                </courseInfo>
                <department>Fine Arts</department></local>"""
            ),
            {
                "department": "Fine Arts",
                "department_code": "FINAR",
                "instructors_string": "Frida Kahlo",
                "section": "FINAR-1000-1",
                "section_calc_id": "FINAR-1000-1_AP_Fall_2024",
                "term": "Fall 2024",
                "title": "The Finest Arts",
            },
        ),
        # Course info with only term = no calc id
        (
            x(
                "<local><courseInfo><semester>Spring 2024</semester></courseInfo></local>"
            ),
            {
                "department": "",
                "department_code": "",
                "instructors_string": "",
                "section": "",
                "section_calc_id": "",
                "term": "Spring 2024",
                "title": "",
            },
        ),
        # Course info with section & term -> calc id
        (
            x(
                "<local><courseInfo><semester>Spring 2024</semester><section>FINAR-1000-1</section></courseInfo></local>"
            ),
            {
                "department": "",
                "department_code": "",
                "instructors_string": "",
                "section": "FINAR-1000-1",
                "section_calc_id": "FINAR-1000-1_AP_Spring_2024",
                "term": "Spring 2024",
                "title": "",
            },
        ),
        # Empty courseInfo node
        (x("<local><courseInfo></courseInfo></local>"), None),
    ],
)
def test_course(input, expect):
    r = Record(input)
    assert r.get()["custom_fields"].get("cca:course") == expect


# Name
@pytest.mark.parametrize(
    "input, expect",
    [
        (
            "Phetteplace, Eric",
            {"family_name": "Phetteplace", "given_name": "Eric", "type": "personal"},
        ),
        (
            "Stephen Beal",
            {"family_name": "Beal", "given_name": "Stephen", "type": "personal"},
        ),
        (
            "Phetteplace, Eric, 1984-",
            {"family_name": "Phetteplace", "given_name": "Eric", "type": "personal"},
        ),
        (
            "Joyce, James, 1882-1941",
            {"family_name": "Joyce", "given_name": "James", "type": "personal"},
        ),
        (
            "CCA Alumni Association",
            {"name": "CCA Alumni Association", "type": "organizational"},
        ),
        (
            "CCA Student Council",
            {"name": "CCA Student Council", "type": "organizational"},
        ),
        (
            "Teri Dowling, John Smith, Annemarie Haar",
            [
                {"family_name": "Dowling", "given_name": "Teri", "type": "personal"},
                {"family_name": "Smith", "given_name": "John", "type": "personal"},
                {"family_name": "Haar", "given_name": "Annemarie", "type": "personal"},
            ],
        ),
        (
            "Maria Rodriguez; Natalie Portman; Audre Lorde",
            [
                {"family_name": "Rodriguez", "given_name": "Maria", "type": "personal"},
                {"family_name": "Portman", "given_name": "Natalie", "type": "personal"},
                {"family_name": "Lorde", "given_name": "Audre", "type": "personal"},
            ],
        ),
        (
            "Carland, Tammy Rae + Hanna, Kathleen",
            [
                {
                    "family_name": "Carland",
                    "given_name": "Tammy Rae",
                    "type": "personal",
                },
                {"family_name": "Hanna", "given_name": "Kathleen", "type": "personal"},
            ],
        ),
        (
            "California College of Arts and Crafts (Oakland, Calif.)",
            {
                "name": "California College of Arts and Crafts (Oakland, Calif.)",
                "type": "organizational",
            },
        ),
        (
            "CCAC Libraries; CCA Sputnik",
            [
                {"name": "CCAC Libraries", "type": "organizational"},
                {"name": "CCA Sputnik", "type": "organizational"},
            ],
        ),
        # Don't let Spacy split CSAC into two ORG entities
        (
            "California School of Arts and Crafts",
            {
                "name": "California School of Arts and Crafts",
                "type": "organizational",
            },
        ),
    ],
)
def test_parse_name(input, expect):
    assert parse_name(input) == expect


# Creators (names in context of a Record)
@pytest.mark.parametrize(
    "input, expect",
    [
        (
            x("<mods><name><namePart>Joe Jonas</namePart></name></mods>"),
            [{"type": "personal", "given_name": "Joe", "family_name": "Jonas"}],
        ),
        (
            x(
                "<mods><name><namePart>Taylor Swift</namePart><namePart>Joe Pesci</namePart></name></mods>"
            ),
            [
                {"type": "personal", "given_name": "Taylor", "family_name": "Swift"},
                {"type": "personal", "given_name": "Joe", "family_name": "Pesci"},
            ],
        ),
        # Syllabus: no mods/name but local/courseInfo/faculty
        (
            x(
                "<local><courseInfo><faculty>Barbara Kruger</faculty></courseInfo></local>"
            ),
            [{"type": "personal", "given_name": "Barbara", "family_name": "Kruger"}],
        ),
    ],
)
def test_creators(input, expect):
    r = Record(input)
    assert [c["person_or_org"] for c in m(r)["creators"]] == expect


# Creator with roles
@pytest.mark.parametrize(
    "input, expect",
    [
        (
            x(
                "<mods><name><namePart>A B</namePart><subNameWrapper><ccaAffiliated>Yes</ccaAffiliated></subNameWrapper></name></mods>"
            ),
            [[{"id": "01mmcf932"}]],
        ),
        (  # common inconsistency, non-CCA still has CCA listed in affiliations
            x(
                "<mods><name><namePart>A B</namePart><subNameWrapper><ccaAffiliated>No</ccaAffiliated><affiliation>CCA</affiliation></subNameWrapper></name></mods>"
            ),
            [[]],
        ),
        (
            x(
                "<mods><name><namePart>A B</namePart><subNameWrapper><affiliation>Other Place</affiliation></subNameWrapper></name></mods>"
            ),
            [[{"name": "Other Place"}]],
        ),
        (
            x(
                "<mods><name><namePart>A B</namePart><subNameWrapper><ccaAffiliated>Yes</ccaAffiliated></subNameWrapper><subNameWrapper><affiliation>Other Place</affiliation></subNameWrapper></name></mods>"
            ),
            [
                [
                    {"id": "01mmcf932"},
                    {"name": "Other Place"},
                ]
            ],
        ),
        # multiple creators
        (
            x(
                "<mods><name><namePart>A B</namePart><subNameWrapper><ccaAffiliated>Yes</ccaAffiliated></subNameWrapper></name><name><namePart>A B</namePart><subNameWrapper><affiliation>Other Place</affiliation></subNameWrapper></name></mods>"
            ),
            [
                [{"id": "01mmcf932"}],
                [{"name": "Other Place"}],
            ],
        ),
    ],
)
def test_creator_affiliations(input, expect):
    r = Record(input)
    # flatten to a list of all creators' affiliations and sort
    # order of affiliations can vary depending how tests are run (lol?)
    assert [
        sorted(c["affiliations"], key=lambda d: d.get("name", "0"))
        for c in m(r)["creators"]
    ] == expect


# Creator roles
@pytest.mark.parametrize(
    "input, expect",
    [
        (
            x(
                '<mods><name><namePart>A B</namePart><role><roleTerm type="text">editor</roleTerm><roleTerm type="text">illustrator</roleTerm></role></name></mods>'
            ),
            [{"id": "editor"}],
        ),
        (  # test a mapped role
            x(
                '<mods><name><namePart>A B</namePart><role><roleTerm type="text">curatorassistant</roleTerm></role></name></mods>'
            ),
            [{"id": "curator"}],
        ),
        (
            x(
                '<mods><name><namePart>A B</namePart><role><roleTerm type="text">publisher</roleTerm></role></name><name><namePart>A B</namePart><role><roleTerm type="text">editor</roleTerm></role></name></mods>'
            ),
            [{"id": "publisher"}, {"id": "editor"}],
        ),
        (  # name without a role
            x("<mods><name><namePart>A B</namePart></name></mods>"),
            [{}],
        ),
    ],
)
def test_creator_roles(input, expect):
    r = Record(input)
    # flatten to a list of all creators' roles
    assert [c["role"] for c in m(r)["creators"]] == expect


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
            [
                {
                    "type": {"id": "abstract", "title": {"en": "Abstract"}},
                    "description": "bar",
                }
            ],
        ),
        (  # note
            x("<mods><noteWrapper><note>foo</note></noteWrapper></mods>"),
            [{"type": {"id": "other", "title": {"en": "Other"}}, "description": "foo"}],
        ),
        (  # note with type
            x(
                "<mods><noteWrapper><note type='handwritten'>foo</note></noteWrapper></mods>"
            ),
            [
                {
                    "type": {"id": "other", "title": {"en": "Other"}},
                    "description": "Handwritten: foo",
                }
            ],
        ),
        (  # empty note does not get added
            x("<mods><noteWrapper><note></note></noteWrapper></mods>"),
            [],
        ),
        (  # empty second abstract does not get added
            x("<mods><abstract>foo</abstract><abstract></abstract></mods>"),
            [],
        ),
    ],
)
def test_addl_desc(input, expect):
    r = Record(input)
    assert m(r)["additional_descriptions"] == expect


# File Formats
@pytest.mark.parametrize(
    "input, expect",
    [
        (  # one format
            {
                "metadata": "<xml></xml>",
                "attachments": [{"type": "file", "filename": "syllabus.pdf"}],
            },
            ["application/pdf"],
        ),
        (  # multiple formats
            {
                "metadata": "<xml></xml>",
                "attachments": [
                    {"type": "file", "filename": "image.jpg"},
                    {"type": "file", "filename": "image.tiff"},
                ],
            },
            ["image/jpeg", "image/tiff"],
        ),
        (  # no files => empty list
            x("<mods></mods>"),
            [],
        ),
        (  # non-file attachment => empty list
            {"metadata": "<xml></xml>", "attachments": [{"type": "other"}]},
            [],
        ),
    ],
)
def test_file_formats(input, expect):
    r = Record(input)
    # sort to ensure order is consistent
    assert sorted(m(r)["formats"]) == expect


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
                {"title": "bar", "type": {"id": "descriptive-title"}},
            ],
        ),
    ],
)
def test_addl_titles(input, expect):
    r = Record(input)
    assert m(r)["additional_titles"] == expect


# Publication Date
@pytest.mark.parametrize(
    "input, expect",
    [
        (
            x(
                "<mods><origininfo><dateCreatedWrapper><dateCreated>1996</dateCreated></dateCreatedWrapper></origininfo></mods>"
            ),
            "1996",
        ),
        (
            x(
                '<mods><origininfo><dateType>dateCreated</dateType><dateCreatedWrapper><dateCreated keyDate="yes">1979-04-28</dateCreated><pointStart/><pointEnd/></dateCreatedWrapper></origininfo></mods>'
            ),
            "1979-04-28",
        ),
        (  # item with dateCreated but nothing in MODS XML
            {
                "metadata": "<xml><mods></mods></xml>",
                "createdDate": "2019-04-25T16:22:52.704-07:00",
            },
            "2019-04-25",
        ),
        (  # some dates are not in ISO 8601 format
            x(
                '<mods><origininfo><dateCreatedWrapper><dateCreated encoding="w3cdtf" keyDate="yes">10/1/93</dateCreated></dateCreatedWrapper></origininfo></mods>'
            ),
            "1993-10-01",
        ),
        (  # empty dateCreated element
            {
                "metadata": "<xml><mods><origininfo><dateCreatedWrapper><dateCreated></dateCreated></dateCreatedWrapper></origininfo></mods></xml>",
                "createdDate": "2023-11-15T12:22:52.704-07:00",
            },
            "2023-11-15",
        ),
        (  # date range
            x(
                "<mods><origininfo><dateCreatedWrapper><dateCreated></dateCreated><pointStart>2016-09</pointStart><pointEnd>2017-05</pointEnd></dateCreatedWrapper></origininfo></mods>"
            ),
            "2016-09/2017-05",
        ),
        (  # empty date range should default to item.dateCreated
            {
                "metadata": "<xml><mods><origininfo><dateCreatedWrapper><dateCreated></dateCreated><pointStart></pointStart><pointEnd></pointEnd></dateCreatedWrapper></origininfo></mods></xml>",
                "createdDate": "2016-11-15T14:42:52.804-07:00",
            },
            "2016-11-15",
        ),
        (
            x(
                "<mods><origininfo><dateCreatedWrapper><dateCreated>fall 2017</dateCreated></dateCreatedWrapper></origininfo></mods>"
            ),
            "2017-08",
        ),
        (
            x(
                "<mods><origininfo><dateCreatedWrapper><dateCreated>winter 2020</dateCreated></dateCreatedWrapper></origininfo></mods>"
            ),
            "2020-11",
        ),
        (  # complex date range
            x(
                "<mods><origininfo><dateCreatedWrapper><dateCreated></dateCreated><pointStart>2017-09-23</pointStart><pointEnd>winter 2020</pointEnd></dateCreatedWrapper></origininfo></mods>"
            ),
            "2017-09-23/2020-11",
        ),
        (  # semesterCreated
            x(
                "<mods><origininfo><semesterCreated>Spring 2014</semesterCreated></origininfo></mods>"
            ),
            "2014-02",
        ),
        (  # malformed date range -> default to item.createdDate
            {
                "createdDate": "2019-04-25T16:22:52.704-07:00",
                "metadata": "<xml><mods><origininfo><dateCreatedWrapper><dateCreated>malformed date</dateCreated></dateCreatedWrapper></origininfo></mods></xml>",
            },
            "2019-04-25",
        ),
    ],
)
def test_publication_date(input, expect):
    r = Record(input)
    assert m(r)["publication_date"] == expect


# Dates
@pytest.mark.parametrize(
    "input, expect",
    [
        (  # dateCaptured
            x(
                "<mods><origininfo><dateCaptured>2020-03-03</dateCaptured></origininfo></mods>"
            ),
            [
                {
                    "date": "2020-03-03",
                    "type": {"id": "collected"},
                    "description": "date captured",
                }
            ],
        ),
        (  # dateOther with no type
            x(
                "<mods><origininfo><dateOtherWrapper><dateOther>2009</dateOther></dateOtherWrapper></origininfo></mods>"
            ),
            [{"date": "2009", "description": "", "type": {"id": "other"}}],
        ),
        (  # dateOther with type
            x(
                "<mods><origininfo><dateOtherWrapper><dateOther type='Exhibit'>2017</dateOther></dateOtherWrapper></origininfo></mods>"
            ),
            [{"date": "2017", "description": "Exhibit", "type": {"id": "other"}}],
        ),
        (  # dateOther with attributes but no text
            x(
                "<mods><origininfo><dateOtherWrapper><dateOther encoding='w3cdtf' type='Agreement'></dateOther></dateOtherWrapper></origininfo></mods>"
            ),
            [],
        ),
        (  # multiple <originInfo>s
            x(
                "<mods><origininfo><dateCaptured>2025-10-21</dateCaptured></origininfo><origininfo/></mods>"
            ),
            [
                {
                    "date": "2025-10-21",
                    "type": {"id": "collected"},
                    "description": "date captured",
                }
            ],
        ),
    ],
)
def test_dates(input, expect):
    r = Record(input)
    assert sorted(m(r)["dates"], key=lambda d: d["date"]) == expect


# Resource Type
@pytest.mark.parametrize(
    "input, expect",
    [
        (  # regular mapping
            x(
                "<mods><typeOfResourceWrapper><typeOfResource>Event documentation</typeOfResource></typeOfResourceWrapper></mods>"
            ),
            "event",
        ),
        (  # multiple <typeOfResource> elements
            x(
                "<mods><typeOfResourceWrapper><typeOfResource>moving image</typeOfResource><typeOfResource>mixed material</typeOfResource></typeOfResourceWrapper></mods>"
            ),
            "image",
        ),
        (  # Items in Syllabus Collection = publication-syllabus
            {
                "collection": {"uuid": syllabus_collection_uuid},
                "metadata": "<xml></xml>",
            },
            "publication-syllabus",
        ),
        (  # default to publication
            x("<mods></mods>"),
            "publication",
        ),
    ],
)
def test_type(input, expect):
    r = Record(input)
    assert m(r)["resource_type"].get("id", "") == expect


# Publisher
@pytest.mark.parametrize(
    "input, expect",
    [
        (  # publisher in originInfo
            x("<mods><originInfo><publisher>foo</publisher></originInfo></mods>"),
            "foo",
        ),
        (  # multiple originInfo nodes, empty publisher node used to cause an error
            x(
                "<mods><originInfo><publisher/></originInfo><originInfo><publisher>foo</publisher></originInfo></mods>"
            ),
            "foo",
        ),
        (  # no publisher
            x("<mods></mods>"),
            "",
        ),
        # various DBR publishers depending on issue
        (
            x(
                "<mods><relatedItem type='host'><titleInfo><title>Design Book Review</title></titleInfo><part><detail type='number'><number>12</number></detail></part></relatedItem></mods>"
            ),
            "Design Book Review",
        ),
        (
            x(
                "<mods><relatedItem type='host'><titleInfo><title>Design Book Review</title></titleInfo><part><detail type='number'><number>29/30</number></detail></part></relatedItem></mods>"
            ),
            "MIT Press",
        ),
        (
            x(
                "<mods><relatedItem type='host'><titleInfo><title>Design Book Review</title></titleInfo><part><detail type='number'><number>37/38</number></detail></part></relatedItem></mods>"
            ),
            "Design Book Review",
        ),
        (
            x(
                "<mods><relatedItem type='host'><titleInfo><title>Design Book Review</title></titleInfo><part><detail type='number'><number>43</number></detail></part></relatedItem></mods>"
            ),
            "California College of the Arts",
        ),
    ],
)
def test_publisher(input, expect):
    r = Record(input)
    assert m(r)["publisher"] == expect


# Related Identifiers
@pytest.mark.parametrize(
    "input, expect",
    [
        (  # no VAULT item information, no related identifiers
            x("<mods/>"),
            [],
        ),
        (
            {
                "uuid": "ec839536-06f9-4fd2-8a80-42ee8a5cf891",
                "version": 1,
                "metadata": "<xml></xml>",
            },
            [
                {
                    "identifier": "https://vault.cca.edu/items/ec839536-06f9-4fd2-8a80-42ee8a5cf891/1/",
                    "relation_type": {"id": "isnewversionof"},
                    "scheme": "url",
                }
            ],
        ),
    ],
)
def test_related_identifiers(input, expect):
    r = Record(input)
    assert m(r)["related_identifiers"] == expect


# Rights
@pytest.mark.parametrize(
    "input, expect",
    [
        (  # accessCondition program rights
            x(
                "<mods><accessCondition type='use and reproduction'>For rights relating to this resource, please contact the CCA First Year Office.</accessCondition></mods>"
            ),
            "copyright",
        ),
        (  # accessCondition CC text
            x("<mods><accessCondition>CC BY 4.0</accessCondition></mods>"),
            "cc-by-4.0",
        ),
        (  # accessCondition with © href
            x(
                "<mods><accessCondition href='http://rightsstatements.org/vocab/InC/1.0/'>does not matter what we put here</accessCondition></mods>"
            ),
            "copyright",
        ),
        (  # accessCondition with CC href
            x(
                "<mods><accessCondition href='https://creativecommons.org/licenses/by-nc/4.0/'>CCA Libraries blah blah blah</accessCondition></mods>"
            ),
            "cc-by-nc-4.0",
        ),
        (  # accessCondition with CC text but no href
            x(
                "<mods><accessCondition>This content is licensed CC-BY-NC per the terms at https://creativecommons.org/licenses/by-nc/4.0/ . You may not use the material for commercial purposes without permission and must give appropriate credit. Contact the CCA Libraries with questions about licensing or attribution.</accessCondition></mods>"
            ),
            "cc-by-nc-4.0",
        ),
        (  # no accessCondition
            x("<mods></mods>"),
            "copyright",
        ),
    ],
)
def test_rights(input, expect):
    r = Record(input)
    assert m(r)["rights"][0]["id"] == expect  # we only use one rights element


@pytest.mark.parametrize(
    "input, expect",
    [
        (  # physical description but no extent
            x(
                "<mods><physicalDescription><formBroad>document</formBroad></physicalDescription></mods>"
            ),
            [],
        ),
        (  # one extent
            x(
                "<mods><physicalDescription><extent>58 unnumbered leaves, bound ; 12 in.</extent></physicalDescription></mods>"
            ),
            ["58 unnumbered leaves, bound ; 12 in."],
        ),
    ],
)
def test_sizes(input, expect):
    r = Record(input)
    assert sorted(m(r)["sizes"]) == expect


@pytest.mark.parametrize(
    "input, expect",
    [
        # empty, no subjects
        ("<subject></subject>", []),
        ("<subject><name/></subject>", []),
        ("<mods></mods>", []),
        # single subject
        (
            "<subject><subjectType>topic</subjectType><topic>Trees</topic></subject>",
            [Subject("Topic", "Trees")],
        ),
        (
            "<subject><subjectType>geographic</subjectType><geographic authority='lcsh'>Berkeley, Calif.</geographic></subject>",
            [Subject("Geographic", "Berkeley, Calif.", "lcsh")],
        ),
        # translate topicCona
        (
            "<subject><topicCona>performance</topicCona></subject>",
            [Subject("Topic", "performance")],
        ),
        # genre
        (
            "<genreWrapper><genre>creative non-fiction</genre></genreWrapper>",
            [Subject("Genre", "creative non-fiction")],
        ),
        # multiple subjects
        (
            "<subject><topic>Art</topic><topic>Design</topic></subject>",
            [Subject("Topic", "Art"), Subject("Topic", "Design")],
        ),
        # multiple genres
        (
            "<genreWrapper><genre>creative non-fiction</genre><genre authority='aat'>poetry</genre></genreWrapper>",
            [
                Subject("Genre", "creative non-fiction"),
                Subject("Genre", "poetry", "aat"),
            ],
        ),
    ],
)
def test_subjects_from_xmldict(input, expect):
    xml = xmltodict.parse(input)
    subjects = []
    for s in mklist(xml.get("subject")):
        for t in TYPES:  # check for every subject type
            for sub in mklist(s.get(t)):
                subjects.extend(subjects_from_xmldict(t, sub))
    for g in mklist(xml.get("genreWrapper", {}).get("genre")):
        subjects.extend(subjects_from_xmldict("genre", g))
    assert sorted(subjects) == expect


@pytest.mark.parametrize(
    "input, expect",
    [
        (
            "<xml><mods><subject><topic>Art</topic><topic>Design</topic></subject><genreWrapper><genre>creative non-fiction</genre><genre>poetry</genre></genreWrapper></mods></xml>",
            [
                Subject("Genre", "creative non-fiction"),
                Subject("Genre", "poetry"),
                Subject("Topic", "Art"),
                Subject("Topic", "Design"),
            ],
        ),
        # real subject alongside empty subject tag
        (
            "<xml><mods><subject><topic>Art</topic></subject><subject/></mods></xml>",
            [Subject("Topic", "Art")],
        ),
        # empty genreWrapper
        (
            "<xml><mods><genreWrapper/></mods></xml>",
            [],
        ),
    ],
)
def test_find_subjects(input, expect):
    xml = xmltodict.parse(input)
    assert sorted(find_subjects(xml)) == expect


# ! These tests depend on having a migrate/subjects_map.json file with term text -> URI mappings
# ! for a few terms (e.g. Emeryville, Graphic Novel)
@pytest.mark.parametrize(
    "input, expect",
    [
        # no subjects
        (x("<mods></mods>"), []),
        # keyword subject
        (
            x(
                "<mods><subject><subjectType>topic</subjectType><topic>Subject not in our mapping</topic></subject></mods>"
            ),
            [{"subject": "Subject not in our mapping"}],
        ),
        # temporal subject
        (
            x(
                "<mods><subject><subjectType>temporal</subjectType><temporal>2010-2019</temporal></subject></mods>"
            ),
            [{"id": "2010-2019"}],
        ),
        # LC subject
        (
            x(
                "<mods><subject><subjectType>geographic</subjectType><geographic authority='lcsh'>Emeryville (Calif.)</geographic></subject></mods>"
            ),
            [{"id": "https://id.loc.gov/authorities/names/n81081214.html"}],
        ),
        # multiple subjects, one genre
        (
            x(
                "<mods><subject><subjectType>topic</subjectType><topic>Subject not in our mapping</topic></subject><genreWrapper><genre>Graphic Novel</genre></genreWrapper></mods>"
            ),
            [
                {
                    "id": "https://id.loc.gov/authorities/genreForms/gf2014026362.html",
                },
                {"subject": "Subject not in our mapping"},
            ],
        ),
    ],
)
def test_subjects(input, expect):
    r = Record(input)
    for subject in m(r)["subjects"]:
        assert subject in expect
    assert len(m(r)["subjects"]) == len(expect)
