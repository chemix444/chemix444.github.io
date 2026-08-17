# chemix444.github.io

My portfolio — an index of everything I've built, with the 15 projects that run
in a browser one click away.

One HTML file. No framework, no build step, no external requests: the typeface
is an embedded Fira Code subset and the data is inline. Open `index.html`.

The index is keyboard-driven — `↑↓` move, `↵` opens the repository, `R` runs it,
`/` searches, `T` switches theme — and everything is clickable too.

## Keeping itself current

`index.html` is regenerated from the GitHub API every two hours by
[`.github/workflows/refresh.yml`](.github/workflows/refresh.yml), which runs
`build.py` and commits only when something actually changed. The bio, the
counts, the repository table and the "last activity" date all follow the
account on their own; a new repository shows up by itself.

Only the marked regions are rewritten — the prose in the featured entries is
hand-written and never touched.

`curation.json` is the one file to edit by hand: which kind each repository is
filed under, short blurbs where GitHub's description runs long, which repos to
exclude, and which six are featured.

```sh
python3 build.py           # rebuild index.html now
python3 build.py --check   # say what would change, write nothing
```
