#!/usr/bin/env python3
"""Проверить, что каждая ссылка на старый хост внутри PDF покрыта картой редиректов.

Обещание алиаса storage.qp.qsupport.ru: любой путь, который встречается
внутри PDF нашего релиза, отвечает 302 на рабочий адрес. Список этих путей
лежит в manifest/redirect-paths.txt, правила — в manifest/redirect-map.json.

Ссылки в PDF лежат в аннотациях как обычный текст (без сжатия потоков),
поэтому ищутся прямо в байтах файла.

    python3 tools/check_redirect_map.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
FILES = ROOT / "files"
MAP = ROOT / "manifest" / "redirect-map.json"

OLD = re.compile(rb"https?://storage[.]qp[.]qsupport[.]ru[^\s\)\]<>]*")


def norm(path: str) -> str:
    p = path.lstrip("/")
    while "//" in p:
        p = p.replace("//", "/")
    return p


def main() -> int:
    rows = json.loads(MAP.read_text(encoding="utf-8"))
    mapped = {r[0] for r in rows}

    pdfs = sorted(FILES.glob("*.pdf"))
    found: set[str] = set()
    per_pdf: dict[str, int] = {}
    for pdf in pdfs:
        data = pdf.read_bytes()
        hits = OLD.findall(data)
        if hits:
            per_pdf[pdf.name] = len(hits)
        for h in hits:
            found.add(h.decode("utf-8", "replace"))

    missing = []
    for u in sorted(found):
        path = norm(unquote(urlsplit(u).path))
        if path not in mapped:
            missing.append((u, path))

    print(f"PDF в релизе: {len(pdfs)}, из них со ссылками на старый хост: {len(per_pdf)}")
    print(f"уникальных ссылок на старый хост: {len(found)}")
    print(f"покрыто картой: {len(found) - len(missing)}, не покрыто: {len(missing)}")
    for u, path in missing:
        print(f"  НЕ ПОКРЫТО: {u}")
        print(f"             путь: {path}")
    print()
    print("ссылок по PDF:")
    for name, n in sorted(per_pdf.items(), key=lambda kv: -kv[1]):
        print(f"  {n:3}  {name}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
