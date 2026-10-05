#!/usr/bin/env python3
"""Пересобрать manifest/manifest.json с диска.

Зачем отдельный шаг: fetch_origin.py пишет манифест по своему списку URL, и
запуск со списком документов quantumart затёр бы общий манифест записями только
этих файлов. Манифест — это то, из чего собираются страница индекса и карта
имён для nginx, то есть он обязан описывать всё, что сервис раздаёт. Список
раздаваемого выводится из одного места, а не из истории запусков.

    python3 tools/refresh_manifest.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
FILES = ROOT / "files"
MANIFEST = ROOT / "manifest" / "manifest.json"
LISTS = [
    ROOT / "manifest" / "source-urls.txt",
    ROOT / "manifest" / "source-urls-docs.txt",
]
CHUNK = 1 << 20

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_origin import RENAMES  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    urls: dict[str, str] = {}
    for lst in LISTS:
        if not lst.exists():
            continue
        for line in lst.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            original = unquote(line.rsplit("/", 1)[-1])
            urls[RENAMES.get(original, original)] = line

    files, unknown = [], []
    for p in sorted(FILES.iterdir()):
        if p.name.startswith(".") or p.suffix in (".part", ".chunk"):
            continue
        if p.name not in urls:
            unknown.append(p.name)
            continue
        original = next((k for k, v in RENAMES.items() if v == p.name), None)
        entry = {"name": p.name, "url": urls[p.name],
                 "size": p.stat().st_size, "sha256": sha256(p)}
        if original:
            entry["original_name"] = original
        files.append(entry)

    listed = set(urls) - {f["name"] for f in files}
    manifest = {
        "release": "v1",
        "repo": "QuantumArt/storage",
        "count": len(files),
        "total_bytes": sum(f["size"] for f in files),
        "files": files,
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"записано: {MANIFEST.relative_to(ROOT)}")
    print(f"файлов: {len(files)}, суммарно {manifest['total_bytes'] / 1e9:.2f} ГБ")
    if unknown:
        print("ВНИМАНИЕ: на диске, но не в списках URL:")
        for n in unknown:
            print(f"  {n}")
    if listed:
        print("ВНИМАНИЕ: в списках URL, но нет на диске:")
        for n in sorted(listed):
            print(f"  {n}")
    return 1 if (unknown or listed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
