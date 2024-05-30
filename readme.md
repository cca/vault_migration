# Repository Migrations

Tools, ideas, and data.

## Setup & Tests

```sh
poetry install # get dependencies
poetry shell # enter venv
python -m spacy download en_core_web_lg # download spacy model for Named Entity Recognition
pytest -v migrate/tests.py # run tests
```

The migrate/record.py file is a class for Invenio records. On the command line, you can pass it JSON EQUELLA item(s) and it will return a JSON Invenio record(s). The migrate/api.py file will create Invenio records from EQUELLA items and attempt to POST them to a local Invenio instance. It requires an `INVENIO_TOKEN` or `TOKEN` environment variable. To create a token: sign in as an admin and go to Applications > Personal access tokens.

## Vocabularies

Invenio uses vocabularies to represent a number of fixtures beyond just subject headings, like names and user accounts. They're stored in the app_data directory and loaded only when an instance is initialized. Lists in contribution wizards and EQUELLA taxonomies might be mapped to vocabularies.

Two ways to export vocabularies:

- `eq tax --name $NAME --terms` e.g. `eq tax --name 'LIBRARIES - cca/c subject' --terms > taxonomies/libraries-ccac-subject.json`
- Admin Console > Taxonomies > Select taxo and **Export**. Yields a zip archive which has each term as an XML file in a nested directory structure. It's less easy to work with but exports hierarchical taxonomies in one go.

```sh
eq tax --path '?length=500' > all.json # download list of all taxos
# download all LIBRARIES taxos (top-level terms only)
for t in (jq -r .results[].name all.json | grep LIBRARIES);
    eq tax --name $t --terms > $t.json
end
```

One way to download a (two-tier) hierarchical taxonomy (archives series). This doesn't quite work because some archives series parent terms (VI. Photographs, VIII. Periodicals and Other Publications, IX. Graduate and Undergraduate Theses) have no children so they end up as empty arrays.

```sh
eq tax 347c7b42-594a-4a7d-8d73-3054ab05a079 --terms > "Archives Series.json"
set idx 1
for term in (jq -r .[].term "Archives Series.json")
    eq tax 347c7b42-594a-4a7d-8d73-3054ab05a079 --term $term > $idx.tmp.json
    set idx (math $idx + 1)
end
mlr --json cat *.tmp.json > taxo.json
rm *.tmp.json
```

Personal names are nested two layers deep in the LIBRARIES - subject name taxonomy: authority > personal or conference > name, e.g. "oclc\personal\Ferrea, Elizabeth, 1880-1925".

```sh
eq tax 657fdbec-c17c-4497-aa31-5b4bc7d9e9e5 --terms > "subject name.json"
set idx 1
for term in (jq -r .[].term "subject name.json")
    eq tax 657fdbec-c17c-4497-aa31-5b4bc7d9e9e5 --term $term\\personal > $idx.tmp.json
    set idx (math $idx + 1)
end
mlr --json cat *.tmp.json > taxo.json
rm *.tmp.json
```

`mlr` is [miller](https://miller.readthedocs.io/) (`brew install miller`). It'd be possible to concatenate the JSON files with `jq` or editing them together, but not as easy.

## Subjects

Download our [subjects sheet](https://docs.google.com/spreadsheets/d/1la_wsFPOkHLjpv4-f3tWwMsCd0_xzuqZ5xp_p1zAAoA/edit#gid=1465207925) and run `python migrate/convert_subjects.py subjects.csv` to create the YAML vocabularies in the vocab dir (lc.yaml and cca_local.yaml) as well as the migrate/subjects_map.json file which is used to convert the text of VAULT subject terms into Invenio IDs or ID-less keyword subjects.

## Items

We could write scripts to directly take an item from EQUELLA using its API, perform a metadata crosswalk, and post it to Invenio. Alternatively, we could work with local copies of items, perhaps created by the equella_scripts collection export tool.

We need to load the necessary fixtures, including user accounts, before adding to Invenio. For instance, the item owner needs to already be in Invenio before we can add them as owner of a record. I'm not sure what the effect of loading a record with a subject that doesn't exist in a vocabulary yet.

## Metadata Crosswalk

We can use the `item.metadata` XML of existing VAULT items for testing. Generally, `poetry run python migrate.py items/item.json | jq` to see the JSON Invenio record. See [our crosswalk diagrams](https://cca.github.io/vault_migration/crosswalk.html).

Schemas:

- https://cca.github.io/vault_schema/
- https://inveniordm.docs.cern.ch/reference/metadata/

It's likely our schema is outdated/inaccurate in places.

How to map a field:

- Add a brief description to the mermaid diagram in [docs/crosswalk.html](docs/crosswalk.html)
- Write a test in tests.py with your input XML and expected record output
- Write a `Record` method in migrate.py & use it in the `Record::get()` dict
- Run tests, optionally run a record migration as described above

## LICENSE

[ECL Version 2.0](https://opensource.org/licenses/ECL-2.0)
