# creator/contributor roles
# ! NOTE cast terms to LOWERCASE before using this map. Our metadata is inconsistent between title case and lowercase.
# MODS (uses MARC list): https://www.loc.gov/marc/relators/relaterm.html
# Invenio roles: https://github.com/inveniosoftware/invenio-rdm-records/blob/master/invenio_rdm_records/fixtures/data/vocabularies/roles.yaml
# Maps from our existing values of mods/name/role/roleTerm to terms either in the MARC relator list of the Invenio roles vocab.
# ? Can we add our roles to the Invenio vocab? They're missing a lot.
role_map = {
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
