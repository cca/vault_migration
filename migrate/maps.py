######################################################
# Maps                                               #
# simple dict maps from MODS metadata to InvenioRDM  #
######################################################

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

# mods typeOfResource => our Invenio resource types
# Our subset of the full list of Invenio resource types: bachelors-thesis, publication, event, image, publication-article, masters-thesis, other, video (Video/Audio)
# Our values for typeOfResource: Event documentation, Event promotion, Group Field Trip, Hold Harmless, Media Release, cartographic, mixed material, moving image, sound recording, sound recording-nonmusical, still image, text
resource_type_map: dict[str, str] = {
    "Event documentation": "event",
    "Event promotion": "event",
    "Group Field Trip": "event",
    "Hold Harmless": "publication",
    "Media Release": "publication",
    "cartographic": "publication",
    "mixed material": "other",
    "moving image": "image",
    "sound recording": "video",
    "sound recording-nonmusical": "video",
    "still image": "video",
    "text": "publication",
}

# creator/contributor roles
# ! NOTE cast terms to LOWERCASE before using this map. Our metadata is inconsistent between title case and lowercase.
# MODS (uses MARC list): https://www.loc.gov/marc/relators/relaterm.html
# Invenio roles: https://github.com/inveniosoftware/invenio-rdm-records/blob/master/invenio_rdm_records/fixtures/data/vocabularies/roles.yaml
# Maps from our existing values of mods/name/role/roleTerm to terms either in the MARC relator list of the Invenio roles vocab.
# ? Can we add our roles to the Invenio vocab? They're missing a lot.
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
    "performanceartist": "arti",
    "poet": "author",
    "professor": "teacher",
    # 1 item where person already has two other roles
    "singersongwriter": "artist",
    "writer": "author",
}
