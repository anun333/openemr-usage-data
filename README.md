# OpenEMR usage data, with provenance

The figures behind "OpenEMR by the numbers" (community.open-emr.org t/27117), each with the
file it came from, when that file was retrieved, its checksum, and the script that turns it
into the figure. Every source is public. Nobody counts OpenEMR installations, so each figure
measures something narrower, and says what.

**The figures are in [FIGURES.md](FIGURES.md)**, with the value published in t/27117 beside
each one. The tables behind them are in `data/`.

## Re-running

```
python3 fetch.py      # downloads raw/ and writes raw/MANIFEST.json (URL, time, size, sha256)
python3 derive.py     # computes data/ and FIGURES.md, and stops if any figure falls below its floor
```

You need Python 3.9+, curl, git, `pdftotext` (poppler-utils), and a clone of openemr/openemr
(`OPENEMR_REPO`, default `~/dev/openemr`) containing the commit named in `fetch.py`. Counts that
keep growing (downloads, pulls, stars) will be higher on a later run; the manifest says when
each was read.

## What each figure measures

| Figure | Source | What it is | What it isn't |
|---|---|---|---|
| SourceForge downloads | SourceForge's statistics API for the openemr project (`raw/sourceforge-*.json`) | Release downloads from SourceForge, all time and October 2025 to September 2026, by month, country and operating system | Installs. SourceForge's newest release is 8.0.0 (February 2026), so downloads there are falling as people use GitHub and Docker. The operating system is the downloading computer's, not the server's |
| GitHub release downloads | GitHub API, `raw/github-releases.json` | Downloads of each release's files (`data/github-release-downloads.csv`, archives and all assets) | Installs, or upgrades in place |
| Docker Hub pulls | Docker Hub API, `raw/dockerhub-openemr.json` | Cumulative pulls of `openemr/openemr` | Installs: CI and automation pull too |
| Meaningful Use attestations | CMS/ONC "EHR Products Used for Meaningful Use Attestation", the Internet Archive's copy of 2025-03-14 (healthit.gov now returns 404) | Distinct US providers (NPI, or CCN for hospitals) who attested with OpenEMR (vendor `OEMR`, or a product named OpenEMR, Open EMR or LibreHealth) in each program year, and in all | Current use: the program ended in 2017. Only aggregates are published here; the file itself names individual clinicians |
| Real World Testing reports | OpenEMR's results reports to ONC, from the OpenEMR wiki (`raw/rwt-*.pdf`) | US practices that sent a usage report each year, by type, as each report states | A census: it counts practices that answered the yearly request |
| Translations | `currentLanguage_utf8.sql` and `currentConstants.txt` in openemr/openemr at the pinned commit, and the code itself | Each language's share of the translation list; literal strings passed to `xl()`, `xlt()` and `xla()` in the code; those missing from the list | The strings built by concatenation, which this count can't see (so the code count is a lower bound) |

`data/strings-missing-from-translation-list.txt` lists the strings in the code that aren't in the
translation list, so translators can see what's missing.

## Files

- `fetch.py`, `derive.py`: the scripts.
- `raw/MANIFEST.json`: every download's URL, retrieval time (UTC), HTTP status, size and sha256, plus the OpenEMR commit and blob ids used for the translation figures.
- `raw/`: the downloaded files. `MU_REPORT.csv` is large and not kept in git; its checksum is in the manifest, and `fetch.py` downloads it again.
- `data/`: the derived tables. `data/figures.json` has every figure with its source.

## License

The scripts are GPL-3.0-or-later (LICENSE). The data come from the public sources named above, under their own terms.
