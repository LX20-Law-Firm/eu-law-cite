# eu-law-cite

Python library and CLI for public EU bibliographic metadata. Convert CELEX, EU-court ECLI and EU ELI work identifiers to BibTeX or CSL-JSON. Check explicit identifiers and links in Markdown. Python 3.11 or later.

```sh
python -m pip install .
eu-law-cite cite CELEX:32016R0679 --format bibtex
eu-law-cite --language it cite ECLI:EU:C:2020:559
eu-law-cite cite https://data.europa.eu/eli/reg/2016/679/oj
eu-law-cite check README.md notes.md
eu-law-cite --offline cite CELEX:32016R0679
```

```python
from eu_law_cite import Client, bibtex
item = Client(cache=".cache/citations").resolve("32016R0679", language="en")
print(bibtex(item))
```

The provider queries the [Publications Office CELLAR SPARQL endpoint](https://publications.europa.eu/webapi/rdf/sparql) for public titles, document dates, languages and identifiers. ECLI records contain EU court metadata distributed through EUR-Lex/CELLAR. The cache stores only resulting citation fields, not legal texts, with a default 24-hour lifetime. `--offline` permits stale cache entries and never requests the network. Delete the cache directory to refresh all records. Cache filenames are hashes, and writes are atomic. No credentials are required.

Supported identifiers: CELEX legislation, case-law, treaty article and treaty text forms; EU court ECLI; EU ELI work URIs ending in `/oj`. National ECLI and national ELI providers, ELI consolidated expressions and document fragments are outside this release. Requested languages must be EU official two-letter codes. No automatic translation or invented metadata is used. A record with no title/date in the requested language is an unavailable result, not a nonexistent identifier. An empty CELLAR result means absent from that catalogue, not proof of nonexistence everywhere.

Markdown parsing uses markdown-it-py: inline links, images, autolinks and reference links are checked; fenced and inline code are ignored. Explicit `CELEX:`/`ECLI:` identifiers, common bare CELEX numbers and EUR-Lex URI/ELI links are resolved. Local file targets are checked. Fragment anchors, raw HTML links and mail addresses are not checked. HTTP 404/410 means broken; authentication, rate limits and network errors mean unavailable. Offline remote links are reported as unchecked. Private network destinations and credential-bearing URLs are blocked, including redirect targets. The checker does not assess legal propositions.

Exit codes: 0 verified with no findings; 1 malformed/missing citations or broken links; 2 unavailable, unsupported or unchecked results (including mixed results). Output is JSON; diagnostics for `cite` go to stderr. BibTeX uses portable `@misc` entries; CSL-JSON uses `legislation` or `legal_case`.

## GitHub Action

After publishing a reviewed release, pin its commit in the calling workflow. Example syntax (the v0.1.0 tag must be created when publishing):

```yaml
- uses: actions/checkout@v4
- uses: LX20-Law-Firm/eu-law-cite@v0.1.0
  with:
    paths: |
      README.md
      docs/article.md
    language: en
```

Inputs are passed as arguments, not executed as shell text. The action performs live metadata/link checks; this repository's CI performs offline tests and lint only.

## Development and provenance

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
ruff check .
```

Tests replay actual CELLAR responses recorded on 2026-11-15. Adjacent `.source.json` files contain exact request URLs. Network sockets are blocked in citation tests. Failure cases are explicitly synthetic fault injections. Metadata comes from the Publications Office; its source rights are retained. Original code: Apache-2.0. Original test data: CC BY 4.0. See LICENSE-DATA and NOTICE.

`.zenodo.json` is prepared for an eventual release deposit. No DOI has been minted. See RELEASE.md for remaining publication gates.
