#!/usr/bin/env python3
"""Проверить, что внутри PDF не осталось ссылок на старый хост и что новые ссылки живы.

После tools/rewrite_pdf_links.py в инструкциях не должно быть ни одной ссылки
на storage.qp.qsupport.ru, а каждая ссылка на наше хранилище или на _cdn
должна отвечать 200.

    python3 tools/check_pdf_links.py
"""

from __future__ import annotations

import concurrent.futures as cf
import re
import subprocess
import sys
from pathlib import Path

try:
    import pikepdf
except ImportError:
    sys.exit("нужен pikepdf: python3 -m pip install pikepdf")

ROOT = Path(__file__).resolve().parent.parent
FILES = ROOT / "files"
OLD_HOST = "storage.qp.qsupport.ru"
RAW = re.compile(rb"https?://storage[.]qp[.]qsupport[.]ru[^\s\)\]<>]*")


def uri_of(annot) -> str | None:
    action = annot.get("/A")
    if action is not None and str(action.get("/S")) == "/URI":
        return str(action.get("/URI"))
    return None


def main() -> int:
    pdfs = sorted(FILES.glob("*.pdf"))
    old_left: list[tuple[str, str]] = []
    targets: set[str] = set()
    per_file = 0

    for p in pdfs:
        data = p.read_bytes()
        for m in RAW.findall(data):
            old_left.append((p.name, m.decode("utf-8", "replace")))
        pdf = pikepdf.open(p)
        for page in pdf.pages:
            for annot in (page.get("/Annots") or []):
                uri = uri_of(annot)
                if uri and ("storage.quantumart.ru" in uri or "_cdn" in uri):
                    targets.add(uri)
        pdf.close()

    print(f"PDF: {len(pdfs)}, уникальных ссылок на наше хранилище/_cdn: {len(targets)}")
    print(f"ссылок на старый хост: {len(old_left)}")
    for name, u in old_left[:20]:
        print(f"  {name}: {u}")

    def head(url: str):
        r = subprocess.run(
            ["curl", "-sS", "-o", "/dev/null", "-L", "--max-time", "30",
             "-w", "%{http_code}", url],
            capture_output=True, text=True)
        return url, r.stdout.strip()

    bad = []
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for url, code in ex.map(head, sorted(targets)):
            if code != "200":
                bad.append((code, url))

    print(f"адресов проверено: {len(targets)}, не-200: {len(bad)}")
    for code, url in bad:
        print(f"  [{code}] {url}")
    return 1 if (old_left or bad) else 0


if __name__ == "__main__":
    raise SystemExit(main())
