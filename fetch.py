"""Downloads every raw source behind the figures, and records where each came from.

    python3 fetch.py [--skip-mu]

Writes raw/<file> and raw/MANIFEST.json: for each file, its URL, the UTC time it was
retrieved, the HTTP status, its size and its sha256. Re-running replaces both, so the
manifest always describes the files beside it. Translation figures are read from an
OpenEMR git clone at a pinned commit instead (see derive.py); the manifest records the
commit and each file's git blob id.

Needs Python 3.9+, curl and git. OPENEMR_REPO points at a clone of openemr/openemr
(default ~/dev/openemr) that has the commit fetched.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
OPENEMR_REPO = Path(os.environ.get("OPENEMR_REPO", Path.home() / "dev" / "openemr"))
OPENEMR_COMMIT = "36b435a524"  # upstream master, 2026-10-11

# The sourceforge window for "the last year" is the twelve full months before the pack's month.
SF_ALL = "https://sourceforge.net/projects/openemr/files/stats/json?start_date=2002-01-01&end_date=2026-10-10"
SF_12M = "https://sourceforge.net/projects/openemr/files/stats/json?start_date=2025-10-01&end_date=2026-09-30"
# healthit.gov now returns 404 for this file; the Internet Archive's copy of 2025-03-14 is
# the one the analysis used (the id_ form returns the archived bytes unmodified).
MU = "http://web.archive.org/web/20250314103603id_/https://www.healthit.gov/sites/default/files/data/datasets/MU_REPORT.csv"
RWT = {
    2023: "https://www.open-emr.org/wiki/images/6/6b/2023-Real-World-Testing-Results-Report-OpenEMR.pdf",
    2024: "https://www.open-emr.org/wiki/images/a/aa/2024-Real-World-Testing-Results-Report-OpenEMR.pdf",
    2025: "https://www.open-emr.org/wiki/images/a/a8/2025-Real-World-Testing-Results-Report-OpenEMR.pdf",
}
SOURCES = [
    ("sourceforge-all-time.json", SF_ALL, "SourceForge download statistics, all time"),
    ("sourceforge-2025-10-to-2026-09.json", SF_12M, "SourceForge download statistics, October 2025 to September 2026"),
    ("github-releases.json", "https://api.github.com/repos/openemr/openemr/releases?per_page=100", "GitHub releases of openemr/openemr with asset download counts"),
    ("github-repo.json", "https://api.github.com/repos/openemr/openemr", "GitHub repository counters (stars, forks)"),
    ("dockerhub-openemr.json", "https://hub.docker.com/v2/repositories/openemr/openemr/", "Docker Hub counters for openemr/openemr (pulls include CI and automation)"),
] + [(f"rwt-{y}.pdf", u, f"OpenEMR Real World Testing results report {y}, from the OpenEMR wiki") for y, u in RWT.items()] + [
    ("MU_REPORT.csv", MU, "CMS/ONC 'EHR Products Used for Meaningful Use Attestation' (archived 2025-03-14)"),
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(name: str, url: str) -> dict:
    out = RAW / name
    when = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    run = subprocess.run(["curl", "-sSL", "--retry", "3", "-A", "openemr-usage-data", "-o", str(out), "-w", "%{http_code}", url],
                         capture_output=True, text=True)
    status = int(run.stdout or 0)
    if run.returncode != 0 or status != 200 or not out.exists() or out.stat().st_size == 0:
        raise SystemExit(f"{name}: download failed (HTTP {status}) {run.stderr.strip()[:200]}")
    return {"file": name, "url": url, "retrieved_utc": when, "http_status": status, "bytes": out.stat().st_size, "sha256": sha256(out)}


def git_blob(path: str) -> str:
    return subprocess.run(["git", "-C", str(OPENEMR_REPO), "rev-parse", f"{OPENEMR_COMMIT}:{path}"],
                          capture_output=True, text=True, check=True).stdout.strip()


def main() -> None:
    RAW.mkdir(exist_ok=True)
    manifest = {"sources": [], "openemr_source": {}}
    for name, url, what in SOURCES:
        if name == "MU_REPORT.csv" and "--skip-mu" in sys.argv:
            old = json.loads((RAW / "MANIFEST.json").read_text()) if (RAW / "MANIFEST.json").exists() else {"sources": []}
            manifest["sources"] += [s for s in old["sources"] if s["file"] == name]
            continue
        entry = fetch(name, url) | {"what": what}
        manifest["sources"].append(entry)
        print(f"{name:40} {entry['bytes']:>11,} bytes  sha256 {entry['sha256'][:16]}")
    full = subprocess.run(["git", "-C", str(OPENEMR_REPO), "rev-parse", OPENEMR_COMMIT], capture_output=True, text=True, check=True).stdout.strip()
    manifest["openemr_source"] = {
        "repository": "https://github.com/openemr/openemr",
        "commit": full,
        "files": {p: git_blob(p) for p in ("contrib/util/language_translations/currentLanguage_utf8.sql",
                                            "contrib/util/language_translations/currentConstants.txt")},
        "note": "translation figures are computed from these files and from the source tree at this commit",
    }
    (RAW / "MANIFEST.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"manifest: {len(manifest['sources'])} downloads, OpenEMR at {full[:10]}")


if __name__ == "__main__":
    main()
