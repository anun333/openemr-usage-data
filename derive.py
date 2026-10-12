"""Computes every figure from the raw files fetch.py downloaded, and checks each against a
floor a broken download would miss.

    python3 derive.py

Writes data/*.csv and data/figures.json, and FIGURES.md (each figure, its source file and
checksum, and the value published in community.open-emr.org t/27117 where there is one).
Needs pdftotext (poppler-utils) for the Real World Testing reports, and git with an
openemr/openemr clone (OPENEMR_REPO, default ~/dev/openemr) for the translation figures.

Meaningful Use: only aggregates are written. The raw file names individual clinicians;
anyone can check the aggregates against it by its sha256 in raw/MANIFEST.json.
"""

from __future__ import annotations

import collections
import csv
import json
import os
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
DATA = HERE / "data"
MANIFEST = json.loads((RAW / "MANIFEST.json").read_text())
OPENEMR_REPO = Path(os.environ.get("OPENEMR_REPO", Path.home() / "dev" / "openemr"))
COMMIT = MANIFEST["openemr_source"]["commit"]
figures: dict[str, dict] = {}
problems: list[str] = []


def floor(ok: bool, what: str) -> None:
    if not ok:
        problems.append(what)


def source(name: str) -> dict:
    s = next(s for s in MANIFEST["sources"] if s["file"] == name)
    return {"file": name, "url": s["url"], "retrieved_utc": s["retrieved_utc"], "sha256": s["sha256"]}


def figure(key: str, value, what: str, src: dict, published=None) -> None:
    figures[key] = {"value": value, "what": what, "source": src, "published_in_t27117": published}


def write_csv(name: str, header: list[str], rows) -> None:
    with (DATA / name).open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def shares(pairs: list) -> list:
    total = sum(n for _, n in pairs) or 1
    return [(name, n, round(100 * n / total, 1)) for name, n in pairs]


# ------------------------------------------------------------------ SourceForge
for name, period in (("sourceforge-all-time.json", "all_time"), ("sourceforge-2025-10-to-2026-09.json", "2025-10_to_2026-09")):
    d = json.loads((RAW / name).read_text())
    figure(f"sourceforge.downloads.{period}", d["total"], f"downloads from SourceForge, {period.replace('_', ' ')}", source(name),
           {"all_time": "830,878 (usage doc)", "2025-10_to_2026-09": "about 45,000"}[period])
    write_csv(f"sourceforge-countries-{period}.csv", ["country", "downloads", "percent_of_located"], shares(d["countries"]))
    write_csv(f"sourceforge-os-{period}.csv", ["operating_system", "downloads", "percent"], shares(d["oses"]))
    write_csv(f"sourceforge-monthly-{period}.csv", ["month", "downloads"], [(m[0][:7], m[1]) for m in d["downloads"]])
    top = shares(d["countries"])[:10]
    figure(f"sourceforge.top_countries.{period}", [f"{c} {p}%" for c, _, p in top],
           "share of downloads whose country is known", source(name),
           "US 42%, India 8%, then Pakistan, the Philippines, Mexico, Nigeria, Kenya, Argentina, Egypt and Brazil" if period != "all_time" else None)
    floor(d["total"] > (800_000 if period == "all_time" else 30_000), f"SourceForge {period} total {d['total']} below its floor")

# ------------------------------------------------------------------ GitHub and Docker Hub
releases = json.loads((RAW / "github-releases.json").read_text())
rows = []
for r in releases:
    archives = sum(a["download_count"] for a in r["assets"] if re.search(r"\.(zip|tar\.gz)$", a["name"]))
    rows.append((r["tag_name"], (r["published_at"] or "")[:10], archives, sum(a["download_count"] for a in r["assets"])))
write_csv("github-release-downloads.csv", ["tag", "published", "archive_downloads", "all_asset_downloads"], rows)
recent = {t: (a, al) for t, _, a, al in rows if t in ("v8_2_0", "v8_3_0", "v8_4_0", "v8_4_1")}
figure("github.release_downloads.8_2_to_8_4_1", {t: al for t, (a, al) in recent.items()},
       "downloads of each release's assets from GitHub (all assets)", source("github-releases.json"), "1,100 to 7,600 per release (8.2.0 through 8.4.1)")
floor(len(recent) == 4, f"GitHub releases 8.2.0-8.4.1 not all found: {sorted(recent)}")
repo = json.loads((RAW / "github-repo.json").read_text())
figure("github.repo", {"stars": repo["stargazers_count"], "forks": repo["forks_count"]}, "openemr/openemr on GitHub", source("github-repo.json"))
hub = json.loads((RAW / "dockerhub-openemr.json").read_text())
figure("dockerhub.pulls", hub["pull_count"], "pulls of openemr/openemr (includes CI and automated pulls)", source("dockerhub-openemr.json"), "9.2 million")
floor(hub["pull_count"] > 1_000_000, "Docker Hub pull count below its floor")

# ------------------------------------------------------------------ Meaningful Use attestations
# Columns as in the file's header: 0 NPI, 1 CCN, 2 provider type, 3 state, 5 specialty,
# 8 program year, 17 vendor, 18 product, 19 product version. OpenEMR rows: vendor OEMR, or a
# product named OpenEMR / Open EMR / LibreHealth (a fork). A provider is NPI, or CCN for hospitals.
def is_openemr(row: list[str]) -> bool:
    p = row[18].lower()
    return row[17] == "OEMR" or "openemr" in p or "open emr" in p or "librehealth" in p


all_by_year: dict[str, set] = collections.defaultdict(set)
oe_by_year: dict[str, set] = collections.defaultdict(set)
oe_rows = []
with (RAW / "MU_REPORT.csv").open(encoding="latin-1", newline="") as fh:
    reader = csv.reader(fh)
    header = next(reader)
    for row in reader:
        if len(row) < 23:
            continue
        key = row[0] or row[1]
        all_by_year[row[8]].add(key)
        if is_openemr(row):
            oe_by_year[row[8]].add(key)
            oe_rows.append(row)
years = sorted(all_by_year)
write_csv("mu-openemr-by-program-year.csv", ["program_year", "providers_attesting_any_ehr", "providers_attesting_with_openemr", "percent"],
          [(y, len(all_by_year[y]), len(oe_by_year[y]), round(100 * len(oe_by_year[y]) / len(all_by_year[y]), 3)) for y in years])
ever_oe = set().union(*oe_by_year.values())
ever_all = set().union(*all_by_year.values())
peak = max(oe_by_year, key=lambda y: len(oe_by_year[y]))
figure("mu.openemr_providers_ever", {"openemr": len(ever_oe), "all": len(ever_all), "percent": round(100 * len(ever_oe) / len(ever_all), 3)},
       f"distinct providers ever attesting with OpenEMR, program years {years[0]}-{years[-1]}", source("MU_REPORT.csv"), "239")
figure("mu.openemr_peak", {"year": peak, "providers": len(oe_by_year[peak])}, "program year with the most OpenEMR attesters", source("MU_REPORT.csv"), "172 in 2013")
for col, name, column, n in ((3, "states", "state", 20), (5, "specialties", "specialty", 20), (2, "provider-types", "provider_type", 10)):
    write_csv(f"mu-openemr-{name}.csv", [column, "attestations"], collections.Counter(r[col] for r in oe_rows).most_common(n))
write_csv("mu-openemr-products.csv", ["vendor", "product", "version", "attestations"],
          [(*k, n) for k, n in collections.Counter((r[17], r[18], r[19]) for r in oe_rows).most_common()])
floor(len(ever_all) > 300_000 and len(ever_oe) > 200, f"MU totals below floor ({len(ever_all)} all, {len(ever_oe)} OpenEMR)")
figure("mu.header", header[:23], "the file's column names (indices used above)", source("MU_REPORT.csv"))

# ------------------------------------------------------------------ Real World Testing reports
rwt = []
for y in (2023, 2024, 2025):
    text = subprocess.run(["pdftotext", "-layout", str(RAW / f"rwt-{y}.pdf"), "-"], capture_output=True, text=True, check=True).stdout
    groups = {g: int(n) for g, n in re.findall(r"(Primary/Specialty Care|Behavioral Health Care) \((\d+) practices? submitted reports?\)", text)}
    total = sum(groups.values())
    rwt.append((y, total, groups.get("Primary/Specialty Care", 0), groups.get("Behavioral Health Care", 0)))
    floor(len(groups) == 2 and total > 0, f"RWT {y}: practice counts not found ({groups})")
write_csv("rwt-practices.csv", ["year", "practices", "primary_specialty", "behavioral_health"], rwt)
figure("rwt.practices", {str(y): t for y, t, _, _ in rwt}, "US practices that sent a Real World Testing usage report",
       {"files": [source(f"rwt-{y}.pdf") for y in (2023, 2024, 2025)]}, "9 in 2023, 14 in 2024, 6 in 2025")

# ------------------------------------------------------------------ Translations
def git_show(path: str) -> str:
    return subprocess.run(["git", "-C", str(OPENEMR_REPO), "show", f"{COMMIT}:{path}"], capture_output=True, text=True, check=True).stdout


lang = git_show("contrib/util/language_translations/currentLanguage_utf8.sql")
langs = {int(m.group(1)): m.group(3) for m in re.finditer(r"\((\d+), '([a-z]{2})', '([^']*)', \d\)", lang)}
per = collections.Counter()
for m in re.finditer(r"\((\d+),\s*(\d+),\s*(\d+),\s*'((?:[^'\\]|\\.)*)'\)", lang):
    if m.group(4).strip():
        per[int(m.group(3))] += 1
dummy = next(i for i, n in langs.items() if n == "dummy")
constants = per[dummy]  # the "dummy" language holds one row per constant
coverage = sorted(((n, per[i], round(100 * per[i] / constants, 1)) for i, n in langs.items() if n not in ("dummy", "English (Standard)")),
                  key=lambda r: -r[1])
write_csv("translation-coverage.csv", ["language", "translated_strings", "percent_of_list"], coverage)
code_rx = r"\bxl[ta]?\(\s*'([^'\\]|\\.)*'\s*\)|\bxl[ta]?\(\s*\"([^\"\\]|\\.)*\"\s*\)"
grep = subprocess.run(["git", "-C", str(OPENEMR_REPO), "grep", "-h", "-o", "-E", code_rx, COMMIT, "--", "*.php", "*.twig", "*.html",
                       ":!vendor", ":!contrib/util/language_translations"], capture_output=True, text=True, check=True).stdout
in_code = {re.sub(r"['\"]\s*\)$", "", re.sub(r"^xl[ta]?\(\s*['\"]", "", s)) for s in grep.splitlines()}
listed = set(git_show("contrib/util/language_translations/currentConstants.txt").splitlines())
missing = sorted(in_code - listed)
(DATA / "strings-missing-from-translation-list.txt").write_text("\n".join(missing) + "\n")
oe_src = {"repository": MANIFEST["openemr_source"]["repository"], "commit": COMMIT, "files": MANIFEST["openemr_source"]["files"]}
figure("translations.list_size", constants, "strings in the translation list (currentLanguage_utf8.sql)", oe_src, "13,234 (usage doc)")
figure("translations.strings_in_code", len(in_code), "distinct literal strings passed to xl()/xlt()/xla() in the code (a lower bound)", oe_src, "roughly 10,900")
figure("translations.missing_from_list", len(missing), "of those, not in the translation list, so shown in English in every language", oe_src, "about 2,400")
floor(len(langs) > 30 and constants > 10_000 and len(in_code) > 9_000, "translation figures below floor")

# ------------------------------------------------------------------ output
DATA.mkdir(exist_ok=True)
(DATA / "figures.json").write_text(json.dumps(figures, indent=1, ensure_ascii=False) + "\n")
lines = ["# Figures", "", "Generated by `derive.py` from the files in `raw/` (see `raw/MANIFEST.json` for where and when each was retrieved).", "",
         "| Figure | Value | Published in t/27117 | Source (sha256) |", "|---|---|---|---|"]
for key, f in figures.items():
    if key == "mu.header":
        continue
    src = f["source"]
    if "commit" in src:
        ref = f"openemr/openemr @ {src['commit'][:10]}"
    elif "files" in src:
        ref = ", ".join(f"{s['file']} ({s['sha256'][:12]})" for s in src["files"])
    else:
        ref = f"{src['file']} ({src['sha256'][:12]})"
    val = f["value"] if not isinstance(f["value"], (list, dict)) else json.dumps(f["value"], ensure_ascii=False)
    lines.append(f"| {f['what']} | {val} | {f['published_in_t27117'] or ''} | {ref} |")
(HERE / "FIGURES.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines[4:]))
if problems:
    raise SystemExit("FLOORS FAILED:\n  " + "\n  ".join(problems))
print(f"\nall floors passed; {len(figures)} figures")
