# Repository Migrations

Tools, ideas, and data.

Semantics: EQUELLA objects are _items_ with _attachments_. Invenio objects are _records_ with _files_. EQUELLA has _taxonomies_; Invenio has _vocabularies_. We use these terms consistently so it's clear what format an object is in (e.g. `python migrate/record.py item.json > record.json` converts an _item_ into a _record_).

## Setup & Tests

```sh
uv install # get dependencies, takes awhile due to spacy's en_core_web_lg model
uv run pytest -v migrate/tests.py # run tests
```

Migrate scripts that create records require an `INVENIO_TOKEN` or `TOKEN` variable in our environment or .env file. To create a token: sign in as an admin and go to Applications > Personal access tokens.

## Vocabularies

Invenio uses [vocabularies](https://inveniordm.docs.cern.ch/customize/vocabularies/) to represent a number of fixtures beyond just subject headings, like names, description types, and creator roles. They're stored under the app_data directory and loaded when an instance is initialized. Many of our controlled lists in contribution wizards and EQUELLA taxonomies will be mapped to vocabularies.

The **taxos** dir contains exported EQUELLA taxonomies and tools for working with them. The **vocab** dir contains YAML files for Invenio vocabularies.

Notable scripts that create Invenio vocabularies:

- [taxos/users.py](./taxos/users.py) creates the [names.yaml](https://inveniordm.docs.cern.ch/operate/customize/vocabularies/names/) and [users.yaml](https://inveniordm.docs.cern.ch/operate/customize/users/#add-users-via-fixtures) fixtures
- [taxos/roles.py](./taxos/roles.py) creates the Invenio relator `creatorsroles` and `contributorsroles` in a file named roles.yaml

### Subjects

We create two subject vocabularies: one for Library of Congress subjects with URIs from one of their authorities and one for CCA local subjects not present in any LC authority.

Download our [subjects sheet](https://docs.google.com/spreadsheets/d/1la_wsFPOkHLjpv4-f3tWwMsCd0_xzuqZ5xp_p1zAAoA/edit#gid=1465207925) and run `python migrate/mk_subjects.py data/subjects.csv` to create the YAML vocabularies in the vocab dir (lc.yaml and cca_local.yaml) as well as migrate/subjects_map.json which is used to convert the text of VAULT subject terms into Invenio identifiers or ID-less keyword subjects.

Copy the YAML vocabularies into the app_data/vocabularies directory of our Invenio instance. The site needs to be rebuilt to load the changes (`invenio-cli services destroy` and then `invenio-cli services setup` again). Eventually (Invenio v12) there will be a CLI command to alter vocabularies without rebuilding the site.

## Creating Records in Invenio

- **migrate/record.py**: Converts EQUELLA item JSON into Invenio record JSON
- **migrate/api.py**: Converts an item and `POST`s it to Invenio to create a record
- **migrate/import.py**: Imports an item _directory_ (created by [the export tool](https://github.com/cca/equella_scripts/tree/main/collection-export)) with its attachments to Invenio

To use these scripts, we must create a personal access token for an administrator account in Invenio:

1. Sign in as an admin
2. Go to **Applications** > **Personal access tokens**
3. Create one—its name and the `user:email` scope (as of v12) do not matter
4. Copy it to clipboard and **Save**
5. Paste in .env and/or set it as an env var, e.g. `set -x INVENIO_TOKEN=xyz` in fish

Below, we migrate a VAULT item to an Invenio record and post it to Invenio.

```sh
set -x INVENIO_TOKEN your_token_here && set -x HOST 127.0.0.1:5000
python migrate/api.py items/item.json # example output below
HTTP 201
https://127.0.0.1:5000/api/records/k7qk8-fqq15/draft
HTTP 202
{"id": "k7qk8-fqq15", "created": "2024-05-31T15:26:17.972009+00:00", ...
https://127.0.0.1:5000/records/k7qk8-fqq15
```

You can sometimes trip over yourself if the `.env` file in the project root is loaded and contains an outdated personal access token. If API calls fail with 403 errors, check that the `TOKEN` or `INVENIO_TOKEN` variable is set correctly.

Rerunning a "migrate" script with the same input creates a new record, it doesn't update the existing one.

## Items

We could write scripts to directly take an item from EQUELLA using its API, perform a metadata crosswalk, and post it to Invenio. Alternatively, we could work with local copies of items, perhaps created by the equella_scripts collection export tool.

We need to load the necessary fixtures, including user accounts, before adding to Invenio. For instance, the item owner needs to already be in Invenio before we can add them as owner of a record. If we attempt to load a record with a subject `id` that doesn't exist yet, we get a 500 error.

We download metadata for all items using equella-cli and a script like this:

```sh
#!/usr/bin/env fish
set total (eq search -l 1 | jq '.available')
set length 50 # can only download up to 50 at a time
set pages (math floor $total / $length)
for i in (seq 0 $pages)
  set start (math $i x $length)
  echo "Downloading items $start to" (math $start + $length)
  # NOTE: no attachment info, use "--info all" for both attachments & metadata
  eq search -l $length --info metadata --start $start > json/$i.json
end
```

## Metadata Crosswalk

We can use the `item.metadata` XML of existing VAULT items for testing. Generally, `python migrate/record.py items/item.json | jq` to see the JSON Invenio record. See [our crosswalk diagrams](https://cca.github.io/vault_migration/crosswalk.html).

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
