# Invenio Vocabularies

This file contains the YAML data of Invenio vocabularies. Some of these files are static and some are generated from scripts in this project.

The `sync` script copies these vocabularies to the appropriate places under an Invenio instance's `app_data` directory using an `INVENIO_REPO` environment variable equal to the path of an Invenio git repository.

## Vocabulary List

- **subject_TYPE.yaml**: (multiple) local subject vocabularies created by migrate/mk_subjects.py from a spreadsheet of terms that existed in VAULT
- **names.yaml**: created by taxos/users.py from Workday JSON data, these auto-complete in Invenio's Creator and Contributor fields
- **programs.yaml**: migrate/mk_subjects.py appends these CCA program names to cca_local
- **roles.yaml**: created by taxos.roles.py from VAULT data, contributor role terms (e.g. "editor", "author")
- **test_users.yaml**: static `library-test-*` user accounts added to users.yaml
- **users.yaml**: created by taxos/users.py from Workday JSON data, these are user accounts
- **vault_names.yaml**: migrate/mk_subjects.py appends these person names lacking LC URIs to cca_local
