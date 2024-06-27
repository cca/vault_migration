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

Personal names are nested two layers deep in the "LIBRARIES - subject name" taxonomy: authority > personal or conference > name, e.g. "oclc\personal\Ferrea, Elizabeth, 1880-1925".

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

`mlr` is [miller](https://miller.readthedocs.io/) (`brew install miller`). It's possible to concatenate the JSON files with `jq` or editing them together, but not as easy.
