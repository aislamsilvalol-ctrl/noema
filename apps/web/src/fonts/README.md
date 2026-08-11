# Vendored fonts

Latin subsets of the variable faces used by the interface, downloaded from Google
Fonts and committed so builds do not depend on network access. That matters for CI,
and more importantly for anyone building NOEMA on an air-gapped machine — which the
project's local mode explicitly promises to support.

| file | family | licence |
|---|---|---|
| `inter.woff2` | Inter | SIL Open Font License 1.1 |
| `newsreader.woff2` | Newsreader | SIL Open Font License 1.1 |
| `jetbrains-mono.woff2` | JetBrains Mono | SIL Open Font License 1.1 |

All three are OFL 1.1, which permits redistribution alongside this project. The
licence text is in `OFL.txt`.

To refresh, request the latin subset from the Google Fonts CSS API and replace the
file in place; the weights are variable ranges, so there is one file per family.
