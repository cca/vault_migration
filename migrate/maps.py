######################################################
# Maps                                               #
# simple dict maps from MODS metadata to InvenioRDM  #
######################################################

# EQUELLA Collection UUID -> Invenio Community shortname
# & /mods/relatedItem[@type='host']/titleInfo/title -> shortname
# See Record.communities method for details.
communities_map: dict[str, str] = {
    # Animation Program
    "66558697-71c5-43a0-b7b3-f778b42c7cd9": "animation",
    # Art Collection
    "b8852fc5-4423-4bc7-958f-7ea643a0b438": "art-collection",
    # Faculty Research
    "e96ccf65-0098-44bb-bec0-6e1cd5466046": "faculty-research",
    # Libraries, non-artists book eResources map here, too
    "6b755832-4070-73d2-77b3-3febcc1f5fad": "libraries",
    "db4e60c6-e001-9ef3-5ce5-479f384026a3": "libraries",
    # Open Access Journal Articles i.e. DBR
    "c34be1f4-c3ea-47d9-b336-e39ad6e926f4": "design-book-review",
    # Libraries Subcollections from relatedItem@host/title
    "Capp Street Project Archive": "capp-street",
    "Hamaguchi Study Print Collection": "hamaguchi",
    "Robert Sommer Mudflats Collection": "mudflats",
}

# CCA/C Archives uses CC-BY-NC4.0 in mods/accessCondition
# There are a few other CC licenses used
license_href_map: dict[str, str] = {
    "http://rightsstatements.org/vocab/InC/1.0/": "copyright",
    "https://creativecommons.org/licenses/by-nc/4.0/": "cc-by-nc-4.0",
}

license_text_map: dict[str, str] = {
    "CC BY 4.0": "cc-by-4.0",
    "CC BY-NC-ND 4.0": "cc-by-nc-nd-4.0",
    "CC BY-NC-SA 4.0": "cc-by-nc-sa-4.0",
    "https://creativecommons.org/licenses/by-nc/4.0/": "cc-by-nc-4.0",
}

# ! CAST TERMS TO lowercase BEFORE USING THESE MAPS. VAULT metadata is inconsistent.
# mods typeOfResourceWrapper/typeOfResource, genre, & genreWrapper/genre -> Invenio resource type
# Our subset of the full list of Invenio resource types: publication, publication-article, publication-book, publication-syllabus, thesis, bachelors-thesis, masters-thesis, image, image-map, image-painting-drawing, image-photo, image-plans, video, event, other
resource_type_map: dict[str, str] = {
    "article": "publication-article",
    "book chapter": "publication-book",
    "cartographic": "image-map",
    "event documentation": "event",
    "event promotion": "event",
    "group field trip": "event",
    "hold harmless": "publication",
    "journal article": "publication-article",
    "media release": "publication",
    "mixed material": "other",
    "moving image": "video",
    "sound recording-nonmusical": "video",
    "sound recording": "video",
    "still image": "image",
    "text": "publication",
}
# mods/physicalDescription/formBroad -> resource type, used in Art Collection & CSP
form_broad_map: dict[str, str] = {
    "animation": "video",
    "architectural document": "image-plans",
    "architectural drawing": "image-plans",
    "article": "publication-article",
    "artists' books (book)": "publication-book",
    "audio": "video",  # video is described as Video/Audio
    "book": "publication-book",
    "books": "publication-book",
    "conference": "event",
    "drawing": "image-painting-drawing",
    "drawings": "image-painting-drawing",
    "exhibition": "event",
    "graphic-novel": "publication-book",
    "legal documents": "publication",
    "maps": "image-map",
    "masters theses": "masters-thesis",
    "mixed media": "other",
    "motion pictures": "video",
    "multimedia": "other",
    "multiple": "other",
    "observational and imaginary drawing": "image-painting-drawing",
    "observational drawing": "image-painting-drawing",
    "oral history": "video",
    "painting": "image-painting-drawing",
    "photo": "image-photo",
    "photograph": "image-photo",
    "print or drawing": "image-painting-drawing",
    "realia": "other",
    "sculpture": "other",
    "sculpture/3D": "image-photo",  # most of these are photos of sculptures
    "serialized comic": "publication-book",
    "video": "video",
    "workshop (seminar)": "event",
}
# local/courseWorkWrapper/courseWorkType -> resource type, used in academic collections
course_work_type_map: dict[str, str] = {
    "animation show submission": "video",
    "other": "other",
    # Arguably we could map "senior packet" and "senior project" to bachelors-thesis, too
    "senior thesis": "bachelors-thesis",
    "senior thesis project": "bachelors-thesis",
    "thesis": "masters-thesis",
    "workshop / events": "event",
}

# creator/contributor roles
# MODS (uses MARC list): https://www.loc.gov/marc/relators/relaterm.html | https://id.loc.gov/vocabulary/relators.html
# Invenio roles: https://github.com/inveniosoftware/invenio-rdm-records/blob/master/invenio_rdm_records/fixtures/data/vocabularies/roles.yaml
# Another option: https://art-and-rare-materials-bf-ext.github.io/arm/v1.0/vocabularies/relator.html
# Maps from our existing values of mods/name/role/roleTerm to terms either in the MARC relator list of the Invenio roles vocab.
role_map: dict[str, str] = {
    # 2 FASHN items, person is creator/artist
    "academicpartner": "artist",
    "collaborator": "contributor",
    "curatorassistant": "curator",
    "installationartist": "artist",
    "instructorassistant": "teacher",
    # 2 class shows in CCA/C Archives; in context of item, prof is a curator
    "instructor/curator": "curator",
    # MARC says to user "organizer"
    "organizerofmeeting": "organizer",
    "painter": "artist",
    "performanceartist": "artist",
    "poet": "author",
    "professor": "teacher",
    # 1 item where person already has two other roles
    "singersongwriter": "artist",
    "writer": "author",
}
