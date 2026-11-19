#!/usr/bin/env python3
"""Собрать карту соответствия старых ссылок новым.

Зачем: внутри PDF-инструкций релиза (66 файлов) 80 ссылок ведут на
storage.qp.qsupport.ru — домен, у которого больше нет DNS-записи. Карта
переводит каждый такой путь на рабочий адрес: файлы хранилища → наше
хранилище, картинки и содержимое → quantumart.ru/_cdn.

Вход:  manifest/link-paths.txt — все пути на старом хосте, встречающиеся в
       наших проектах. Список зафиксирован, чтобы карта была
       воспроизводимой.
Выход: manifest/link-map.json — соответствия старых путей новым адресам.

Категории и их порядок:

  1. четыре точных исключения — на оригинале имя битое, у нас правильное;
  2. qa_official_site/images/downloads/       → наше хранилище;
  3. qa_official_site/images/presentation|documents/ → наше хранилище;
  4. документы по расширению (.pdf/.docx/.doc) → наше хранилище;
  5. qa_official_site/images/*   → quantumart.ru/_cdn/images/...
  6. qa_official_site/contents/* → quantumart.ru/_cdn/contents/...

Запуск:
    python3 tools/build_link_map.py
    python3 tools/build_link_map.py --check   # дополнительно проверить цели
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATHS = ROOT / "manifest" / "link-paths.txt"
OUT = ROOT / "manifest" / "link-map.json"

STORE = "https://storage.quantumart.ru/downloads/"
CDN = "https://quantumart.ru/_cdn/"
OLD_PREFIX = "qa_official_site/"

# Точные исключения. На старом хосте эти имена битые (опечатка или другой
# формат), у нас файлы лежат под правильными именами.
EXACT = {
    "qa_official_site/images/downloads/QP_Setup_7.9.7.0..zip":
        STORE + "QP_Setup_7.9.7.0.zip",
    "qa_official_site/images/downloads/qp8-pg-functional-\u0441haracteristics.pdf":
        STORE + "qp8-pg-functional-characteristics.pdf",
    "qa_official_site/images/downloads/qp8-search-installation-man.pdf":
        STORE + "qp8-search-installation-manual.pdf",
    "qa_official_site/images/downloads/widget_config.tar":
        STORE + "widget-config.tar",
}

# Тестовые фикстуры из tests/ проектов: на старом хосте их тоже нет.
FIXTURES = {"a.png", "\u043e\u0431.jpg"}

DOC_EXT = (".pdf", ".docx", ".doc")


def normalize(path: str) -> str:
    """Путь в том виде, в каком он стоит в ссылке.

    Двойные слеши схлопываются: в PDF-ссылках реально встречается
    «images//laptop.svg», а новый адрес строим от нормализованного пути.
    """
    p = path.lstrip("/")
    while "//" in p:
        p = p.replace("//", "/")
    return p


def target(path: str) -> tuple[str | None, str]:
    """Куда отправляем запрос. None — соответствия для этого пути нет."""
    p = normalize(path)
    if p in EXACT:
        return EXACT[p], "exact"
    if p.startswith("qa_official_site/images/downloads/"):
        return STORE + p[len("qa_official_site/images/downloads/"):], "store"
    if p.startswith(("qa_official_site/images/presentation/",
                     "qa_official_site/images/documents/")):
        return STORE + p.rsplit("/", 1)[1], "store"
    if p.startswith("qa_official_site/images/"):
        tail = p[len("qa_official_site/images/"):]
        if tail.lower().endswith(DOC_EXT):
            return STORE + tail, "store"
    if p.startswith(OLD_PREFIX):
        return CDN + p[len(OLD_PREFIX):], "cdn"
    return None, "none"


def read_paths() -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for line in PATHS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line in seen:
            continue
        seen.add(line)
        out.append(line)
    return out


def build() -> list[list]:
    rows, norule = [], []
    for p in read_paths():
        if p in FIXTURES:
            continue
        t, kind = target(p)
        if t is None:
            norule.append(p)
            continue
        rows.append([normalize(p), t, kind])
    rows.sort(key=lambda r: r[0])
    if norule:
        print("ВНИМАНИЕ: без соответствия:", norule)
    return rows


def check(rows: list[list]) -> int:
    """Проверить, что все новые адреса отвечают 200. Медленно: 360 запросов."""
    def head(row):
        path, tgt, _kind = row
        r = subprocess.run(
            ["curl", "-sS", "-o", "/dev/null", "-L", "--max-time", "30",
             "-w", "%{http_code}", tgt],
            capture_output=True, text=True)
        return path, tgt, r.stdout.strip()

    bad = []
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for path, tgt, code in ex.map(head, rows):
            if code != "200":
                bad.append((code, path, tgt))
    print(f"адресов проверено: {len(rows)}, не-200: {len(bad)}")
    for code, path, tgt in bad:
        print(f"  [{code}] {path}\n       -> {tgt}")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="дополнительно проверить, что адреса отвечают 200")
    args = ap.parse_args()

    rows = build()
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    print(f"соответствий: {len(rows)}")
    print(f"записано: {OUT.relative_to(ROOT)}")
    if args.check:
        return check(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
