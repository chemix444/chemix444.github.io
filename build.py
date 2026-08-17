#!/usr/bin/env python3
"""Refresh index.html from the live GitHub API.

Only the marked regions are rewritten — the hand-written prose in the featured
entries is never touched. Run it locally with no arguments, or let the
workflow in .github/workflows/refresh.yml run it every two hours.

    python3 build.py            # rewrite index.html in place
    python3 build.py --check    # report what would change, write nothing

GH_TOKEN is used when present (higher rate limit, and it is what Actions
provides); the script works unauthenticated too.
"""

import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGE = HERE / "index.html"
CURATION = HERE / "curation.json"

API = "https://api.github.com"
KIND_ORDER = ["DECK", "APP", "GAME", "SCRIPT", "SITE", "MISC"]

# Descriptions come from GitHub, where anything can end up in them. The page is
# deliberately emoji-free, so strip pictographs rather than let one through.
EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF\U00002B00-\U00002BFF️⃣]+"
)


def fetch(path):
    req = urllib.request.Request(API + path, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "chemix444-portfolio-build",
    })
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def clean(text):
    return EMOJI.sub("", (text or "")).strip().replace("  ", " ")


def region(source, open_tag, close_tag, body, label):
    """Replace whatever sits between two markers, keeping the markers."""
    pattern = re.compile(
        re.escape(open_tag) + r".*?" + re.escape(close_tag), re.DOTALL)
    if not pattern.search(source):
        sys.exit(f"marker missing in index.html: {label}")
    return pattern.sub(lambda _: open_tag + body + close_tag, source, count=1)


def main():
    check_only = "--check" in sys.argv
    cur = json.loads(CURATION.read_text())
    user = cur["user"]
    exclude = set(cur.get("exclude", []))
    kinds = cur.get("kinds", {})
    blurbs = cur.get("blurbs", {})

    profile = fetch(f"/users/{user}")
    repos = []
    page = 1
    while True:
        batch = fetch(f"/users/{user}/repos?per_page=100&page={page}&sort=pushed")
        repos += batch
        if len(batch) < 100:
            break
        page += 1

    keep = [r for r in repos
            if not r["fork"] and not r["private"] and r["name"] not in exclude]

    rows = []
    for r in keep:
        name = r["name"]
        kind = kinds.get(name, cur.get("default_kind", "MISC"))
        if kind not in KIND_ORDER:
            kind = "MISC"
        rows.append({
            "name": name,
            "kind": kind,
            "lang": r["language"] or "—",
            "year": int(r["created_at"][:4]),
            "live": 1 if r["has_pages"] else 0,
            "text": clean(blurbs.get(name) or r["description"] or "—"),
            "pushed": r["pushed_at"],
        })

    # Grouped by kind, most recently pushed first inside each group. Two passes
    # rather than one composite key, because the sort is stable and the two
    # halves want opposite directions.
    rows.sort(key=lambda x: x["pushed"], reverse=True)
    rows.sort(key=lambda x: KIND_ORDER.index(x["kind"]))

    missing = [f for f in cur.get("featured", [])
               if f not in {x["name"] for x in rows}]
    if missing:
        print(f"warning: featured entry no longer in the repo list: {missing}",
              file=sys.stderr)

    # ---- computed figures -------------------------------------------------
    total = len(rows)
    live = sum(r["live"] for r in rows)
    games = sum(1 for r in rows if r["kind"] == "GAME")
    langs = len({r["lang"] for r in rows if r["lang"] != "—"})
    featured = len(cur.get("featured", []))
    activity = max((r["pushed"] for r in rows), default="")
    activity_out = (datetime.strptime(activity, "%Y-%m-%dT%H:%M:%SZ")
                    .replace(tzinfo=timezone.utc).strftime("%-d %b %Y")
                    if activity else "—")

    stats = [(total, "Repositories"), (live, "Run in a browser"),
             (games, "Games"), (langs, "Languages")]
    stats_html = "\n" + "\n".join(
        f'      <div class="stat"><b>{n}</b><span>{html.escape(label)}</span></div>'
        for n, label in stats) + "\n    "

    # ---- table rows, so the index exists without JavaScript ---------------
    trs = []
    for r in rows:
        go = (f'<a class="tag-run" href="https://{user}.github.io/{r["name"]}/">RUN</a>'
              if r["live"] else '<span class="tag-none">SOURCE</span>')
        trs.append(
            "\n            <tr>"
            f'<td class="name">{html.escape(r["name"])}</td>'
            f'<td class="what">{html.escape(r["text"])}</td>'
            f'<td class="kind">{r["kind"]}</td>'
            f'<td class="lang">{html.escape(r["lang"])}</td>'
            f'<td class="year">{r["year"]}</td>'
            f'<td class="go">{go}</td></tr>')
    rows_html = "".join(trs) + "\n          "

    # ---- the array the client filters over --------------------------------
    lines = []
    for r in rows:
        lines.append("    " + json.dumps(
            [r["name"], r["kind"], r["lang"], r["year"], r["live"], r["text"]],
            ensure_ascii=False))
    repos_js = "\n" + ",\n".join(lines) + "\n  "
    # A literal </script> inside a string would close the block early.
    repos_js = repos_js.replace("</", "<\\/")

    page_src = PAGE.read_text()
    out = page_src
    out = region(out, "<!--auto:tagline-->", "<!--/auto:tagline-->",
                 html.escape(clean(profile.get("bio")) or ""), "tagline")
    out = region(out, "<!--auto:stats-->", "<!--/auto:stats-->", stats_html, "stats")
    out = region(out, "<!--auto:featured-count-->", "<!--/auto:featured-count-->",
                 f"{featured:02d} of {total}", "featured-count")
    out = region(out, "<!--auto:rows-->", "<!--/auto:rows-->", rows_html, "rows")
    out = region(out, "/*auto:repos*/", "/*end:repos*/", repos_js, "repos")
    out = region(out, "<!--auto:activity-->", "<!--/auto:activity-->",
                 activity_out, "activity")

    changed = out != page_src
    print(f"{total} repositories · {live} live · {games} games · {langs} languages"
          f" · last activity {activity_out}")
    if check_only:
        print("changed" if changed else "unchanged")
        return 0
    if changed:
        PAGE.write_text(out)
        print("index.html updated")
    else:
        print("index.html already current")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.HTTPError as e:
        sys.exit(f"GitHub API error {e.code}: {e.reason}")
