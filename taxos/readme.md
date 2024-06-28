# Taxonomies

Two ways to export taxonomies:

- `eq tax --name $NAME --terms` e.g. `eq tax --name 'LIBRARIES - cca/c subject' --terms > taxonomies/libraries-ccac-subject.json`
- Admin Console > Taxonomies > Select taxo and **Export**. Yields a zip archive which has each term as an XML file in a nested directory structure. It's less easy to work with but exports hierarchical taxonomies in one go.

```sh
eq tax --path '?length=500' > all.json # download list of all taxos
# download all LIBRARIES taxos (top-level terms only)
for t in (jq -r .results[].name all.json | grep LIBRARIES);
    eq tax --name $t --terms > $t.json
end
```

Here's a way to download a (two-tier) hierarchical taxonomy ("LIBRARIES - Archives Series"). Some series have no children (VI. Photographs, VIII. Periodicals and Other Publications, IX. Graduate and Undergraduate Theses). We're waiting to have these finalized during archives work before adding to Invenio and unsure if they will be part of the `cca_local` subjects, a distinct subject vocab, or a custom field.

```sh
set uuid 347c7b42-594a-4a7d-8d73-3054ab05a079
eq tax $uuid --terms > "Archives Series.json"
cp "Archives Series.json" archives-series-complete.json
for term in (jq -r ".[].term" "Archives Series.json")
    eq tax $uuid --term $term > tmp.json
    set length (jq '. | length' tmp.json 2> /dev/null)
    if test "$length" -gt 0
        mlr --json cat tmp.json archives-series-complete.json > tmp2.json
        mv tmp2.json archives-series-complete.json
    end
end
rm tmp.json
```

Personal names are nested two layers deep in the "LIBRARIES - subject name" taxonomy: authority > conference or corporate or personal > term, e.g. "oclc\personal\Ferrea, Elizabeth, 1880-1925". The code below recreates subject-name-complete.json with all terms.

```sh
set uuid 657fdbec-c17c-4497-aa31-5b4bc7d9e9e5
eq tax $uuid --terms > "subject name.json"
echo "[]" > subject-name-complete.json
for term in (jq -r .[].term "subject name.json")
    for type in conference corporate personal
        eq tax $uuid --term $term\\$type > tmp.json
        set err (jq -r .error tmp.json 2> /dev/null)
        if test -z "$err" # no err => results array
            mlr --json cat tmp.json subject-name-complete.json > tmp2.json
            mv tmp2.json subject-name-complete.json
        end
    end
end
rm tmp.json
```

`mlr` is [miller](https://miller.readthedocs.io/) (`brew install miller`). It's possible to concatenate the JSON files with `jq` or by editing them together, but not as easy.
