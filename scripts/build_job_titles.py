"""Build data/job_titles.json, the job-title type-ahead list, from the O*NET Database.

Run: python scripts/build_job_titles.py 31.0

Downloads job_titles.csv for that O*NET release from onetcenter.org (CC BY 4.0)
and keeps every Job Title and Short Title once, case-insensitively, with
whitespace tidied. Titles are otherwise used as published, so the form's footer
carries O*NET's verbatim credit, which names the version stored in the file.
"""
import csv
import io
import json
import os
import sys
import urllib.request

version = sys.argv[1]
url = f"https://www.onetcenter.org/dl_files/database/db_{version.replace('.', '_')}_csv/job_titles.csv"
with urllib.request.urlopen(url, timeout=60) as response:
    rows = csv.DictReader(io.StringIO(response.read().decode("utf-8")))
    titles = {}
    for row in rows:
        for title in (row["Job Title"], row["Short Title"]):
            title = " ".join(title.split())
            if title:
                titles.setdefault(title.casefold(), title)

out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "job_titles.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump({"onet_version": version, "titles": sorted(titles.values(), key=str.casefold)},
              f, ensure_ascii=False, indent=0)
    f.write("\n")
print(f"{len(titles)} titles from O*NET {version} -> {out}")
