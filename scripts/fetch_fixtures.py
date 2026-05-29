"""Fetch small, real SEC fixtures for parser unit tests.

Saves trimmed, well-formed XML under fixtures/sec/. Public data, no auth — but SEC
requires a User-Agent (env SEC_USER_AGENT, format: "Name email@example.com").
Respects the ~8 req/sec courtesy limit. Re-runnable; overwrites the fixtures.

    SEC_USER_AGENT="Name email@example.com" python scripts/fetch_fixtures.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import time

import requests
from lxml import etree

UA = os.environ.get("SEC_USER_AGENT")
if not UA:
    sys.exit("SEC_USER_AGENT not set (format: 'Name email@example.com')")

OUT = pathlib.Path("fixtures/sec")
OUT.mkdir(parents=True, exist_ok=True)
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept-Encoding": "gzip, deflate"})


def get(url: str) -> requests.Response:
    time.sleep(0.15)  # ~7 req/sec, under SEC's 10/sec limit
    r = SESSION.get(url, timeout=30)
    r.raise_for_status()
    return r


def latest_accession(cik10: str, form: str) -> str:
    rec = get(f"https://data.sec.gov/submissions/CIK{cik10}.json").json()["filings"]["recent"]
    for form_t, acc in zip(rec["form"], rec["accessionNumber"]):
        if form_t == form:
            return acc
    sys.exit(f"no {form} filing found for CIK {cik10}")


def filing_dir(cik_int: int, accession: str) -> tuple[str, list[str]]:
    base = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession.replace('-', '')}"
    items = get(f"{base}/index.json").json()["directory"]["item"]
    return base, [i["name"] for i in items]


def find_xml(base: str, names: list[str], marker: str) -> tuple[str, str]:
    for n in names:
        if n.lower().endswith(".xml"):
            txt = get(f"{base}/{n}").text
            if marker in txt:
                return n, txt
    sys.exit(f"no .xml containing {marker!r} in {base}")


def main() -> None:
    # --- 13F-HR information table (Berkshire Hathaway) ---
    acc = latest_accession("0001067983", "13F-HR")
    base, names = filing_dir(1067983, acc)
    name, txt = find_xml(base, names, "infoTable")
    root = etree.fromstring(txt.encode())
    infos = [e for e in root.iter() if etree.QName(e).localname == "infoTable"]
    for extra in infos[3:]:                       # keep 3 positions; drop the rest
        extra.getparent().remove(extra)
    (OUT / "13f_berkshire_sample.xml").write_bytes(etree.tostring(root, pretty_print=True))
    print(f"13F-HR  {acc}  {name}  -> kept {min(3, len(infos))}/{len(infos)} positions")

    # --- Form 4 ownership document (Palantir as issuer) ---
    acc = latest_accession("0001321655", "4")
    base, names = filing_dir(1321655, acc)
    name, txt = find_xml(base, names, "ownershipDocument")
    (OUT / "form4_sample.xml").write_text(txt, encoding="utf-8")
    print(f"Form 4  {acc}  {name}  -> {len(txt)} bytes")


if __name__ == "__main__":
    main()
