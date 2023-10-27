# EQUELLA -> InvenioRDM Crosswalk<

For upcoming VAULT migration. This page uses a <a href="https://mermaid.js.org/">Mermaid</a> <a href="https://mermaid.js.org/syntax/flowchart.html">flowchart</a>.

## MODS Mappings

These start at /xml/mods.

```mermaid
flowchart LR
    ABSTRACTS[abstract] ---> |1st instance| DESCRIPTION["Description (0-1)"]
    ABSTRACTS --> |2+ instances| ADTYPE["Attributes imply desc type, default other"]
    NOTES[noteWrapper/note] --> ADTYPE
    ADTYPE --> ADDLDESC["Additional Descriptions (0-n)"]
```

## Local Mappings

These start at /xml/local.

```mermaid
flowchart LR
    viewlevel[viewLevel] --> |Many, many translations| ACCESS["Access restricted/public"]
```

<script type="module">
import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
mermaid.initialize({ startOnLoad: true });
</script>
