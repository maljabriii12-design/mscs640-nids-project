"""Dataset download over plain HTTPS (no AWS CLI needed).

The bucket ``cse-cic-ids2018`` is public and anonymously readable. This
module lists ``Processed Traffic Data for ML Algorithms/`` through the S3
REST listing API and streams each CSV to disk. Downloads resume with HTTP
Range requests, and files whose size already matches are skipped.
"""
from __future__ import annotations

import logging
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

log = logging.getLogger(__name__)

BUCKET_URL = "https://cse-cic-ids2018.s3.amazonaws.com/"
PREFIX = "Processed Traffic Data for ML Algorithms/"
NS = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}


def list_files() -> list[tuple[str, int]]:
    url = BUCKET_URL + "?" + urllib.parse.urlencode({"list-type": "2", "prefix": PREFIX})
    with urllib.request.urlopen(url, timeout=60) as r:
        root = ET.fromstring(r.read())
    out = []
    for c in root.findall("s3:Contents", NS):
        key = c.find("s3:Key", NS).text
        size = int(c.find("s3:Size", NS).text)
        if key.endswith(".csv"):
            out.append((key, size))
    return out


def download(raw_dir: str | Path, only: str | None = None) -> list[Path]:
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    got = []
    for key, size in list_files():
        name = key.split("/")[-1]
        if only and only not in name:
            continue
        dest = raw_dir / name
        have = dest.stat().st_size if dest.exists() else 0
        if have == size:
            log.info("already have %s", name)
            got.append(dest)
            continue
        req = urllib.request.Request(BUCKET_URL + urllib.parse.quote(key))
        if have:
            req.add_header("Range", f"bytes={have}-")
        log.info("downloading %s (%.0f MB)%s", name, size / 2 ** 20,
                 f", resuming at {have / 2 ** 20:.0f} MB" if have else "")
        with urllib.request.urlopen(req, timeout=120) as r, open(dest, "ab" if have else "wb") as fh:
            done = have
            while chunk := r.read(8 * 2 ** 20):
                fh.write(chunk)
                done += len(chunk)
                print(f"\r  {done / 2 ** 20:8.0f} / {size / 2 ** 20:.0f} MB", end="", flush=True)
        print()
        got.append(dest)
    return got
