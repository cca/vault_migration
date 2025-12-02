# Migration Scripts

These scripts are tools for actually migrating data into Invenio. The [main readme](../readme.md#creating-records-in-invenio) has a general summary of the script usage and this is additional documentation.

## Import ID Map

We need to know which Invenio record corresponds to which VAULT item, which will be referenced in the Invenio metadata but we also want a more convenient format which compiles several important pieces of information. The import.py script (but _none of the other scripts_) creates and updates a JSON mapping. It is named "id-map.json" by default but can be changed with the `--map-file` flag.

Here is the structure of the mapping file:

```json
{
  "https://vault.cca.edu/item/<uuid>/<version>": {
    "id": "invenio_id",
    "title": "Title",
    "owner": "username",
    "collaborators": ["username1", "username2"],
    "viewlevel": "Public",
    "events": [
      {
        "name": "import",
        "time": "2025-12-01T12:34:56.789012",
        "data": {
          "id": "invenio_id"
        }
      }
    ]
  },
  "vault_item_url_2": {
    ...
  }
}
```

We can use additional Invenio management scripts to modify records and update this mapping, for instance to:

- Change the owner of a record to `owner`
- Share the record with `collaborators`
- Share the record according to its `viewlevel`

When an operation is performed, we append it to the `events` array. Events must have `name` and ISO `time` strings, but optionally an open-ended `data` object for arbitrary information related to the event. For instance, by recording the Invenio record ID in the `import` event while the import script overwrites the main `id` field, we can track the Invenio record IDs that have been created for a given VAULT item over time. This allows us to deduplicate Invenio records if necessary.

## Archives Series

The [archives_series.json](archives_series.json) file is used to check created Invenio records against our Archives Series structure, coming from the Box List spreadsheet. It must be kept up to date with the Box List as well as the JavaScript object in the ArhivesSeries.js custom field react component. If a record uses a series term not in this file, a warning it printed to stderr but no exception is thrown.
