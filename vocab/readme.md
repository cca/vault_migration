# Invenio Vocabularies

This file contains the YAML data of Invenio vocabularies. Some of these files are static and some are generated from scripts in this project.

The `sync` script copies these vocabularies to the appropriate places under an Invenio instance's `app_data` directory using an `INVENIO_REPO` environment variable equal to the path of an Invenio git repository.

## Vocabulary List

- **admin_users.yaml**: taxos/users.py appends users listed here to users.yaml below
- **cca_local.yaml**: local subjects vocabulary created by migrate/mk_subjects.py from a spreadsheet of terms that existed in VAULT
- **lc.yaml**: same as cca_local but these have identifiers in Library of Congress controlled vocabularies (LCNAF, LCSH, etc.)
- **names.yaml**: created by taxos/users.py from Workday JSON data, these auto-complete in Invenio's Creator and Contributor fields
- **programs.yaml**: migrate/mk_subjects.py appends these CCA program names to cca_local
- **roles.yaml**: created by taxos.roles.py from VAULT data, contributor role terms (e.g. "editor", "author")
- **subject_names.yaml**: migrate/mk_subjects.py appends these person names lacking LC URIs to cca_local
- **users.yaml**: created by taxos/users.py from Workday JSON data, these are user accounts
