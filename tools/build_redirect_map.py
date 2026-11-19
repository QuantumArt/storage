#!/usr/bin/env python3
"""Собрать карту редиректов для алиаса storage.qp.qsupport.ru.

Зачем: внутри 66 PDF нашего релиза 80 ссылок ведут на storage.qp.qsupport.ru —
домен, у которого больше нет DNS-записи. Читатель PDF кликает по ссылке и
получает ошибку. Этот алиас отдаёт те же пути на новые адреса (302), и ссылки
внутри PDF продолжают работать.

Вход:  manifest/redirect-paths.txt — все пути на старом хосте, которые
       встречаются в наших проектах (внутри PDF релиза, в разметке
       quantumart). Список зафиксирован, чтобы карта была воспроизводимой.
Выход: manifest/redirect-map.json       — правила в машинном виде
       site/nginx/storage.qp.qsupport.ru.map — блок map для nginx

Категории и их порядок (в блоке map сначала проверяются точные ключи, потом
регулярки по порядку):

  1. четыре точных исключения — на оригинале имя битое, у нас правильное;
  2. qa_official_site/images/downloads/       → наше хранилище;
  3. qa_official_site/images/presentation|documents/ → наше хранилище;
  4. документы по расширению (.pdf/.docx/.doc) → наше хранилище;
  5. qa_official_site/images/*   → quantumart.ru/_cdn/images/...
  6. qa_official_site/contents/* → quantumart.ru/_cdn/contents/...

Запуск:
    python3 tools/build_redirect_map.py
    python3 tools/build_redirect_map.py --check   # дополнительно проверить цели
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATHS = ROOT / "manifest" / "redirect-paths.txt"
JSON_OUT = ROOT / "manifest" / "redirect-map.json"
NGINX_OUT = ROOT / "site" / "nginx" / "storage.qp.qsupport.ru.map"

STORE = "https://storage.quantumart.ru/downloads/"
CDN = "https://quantumart.ru/_cdn/"
OLD_PREFIX = "qa_official_site/"

# Точные исключения. На старом хосте эти имена битые (опечатка или другой
# формат), у нас файлы лежат под правильными именами. Без исключений ссылка
# внутри PDF вела бы в никуда.
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
    """Путь в том виде, в каком его отдаёт nginx в переменной $uri.

    $uri уже схлопывает повторяющиеся слеши и декодирует %XX, поэтому ключ
    в карте должен быть таким же: с один слешем и в UTF-8, а не в
    percent-encoding.
    """
    p = path.lstrip("/")
    while "//" in p:
        p = p.replace("//", "/")
    return p


def target(path: str) -> tuple[str | None, str]:
    """Куда отправляем запрос. None — правила для этого пути нет."""
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
        print("ВНИМАНИЕ: без правила:", norule)
    return rows


def nginx_block(rows: list[list]) -> str:
    bucket = 64
    while bucket < len(rows) * 4:
        bucket *= 2
    lines = [
        "# Сгенерировано tools/build_redirect_map.py из manifest/redirect-paths.txt.",
        "# Не редактировать: правки пропадут при следующей генерации.",
        f"# Правил: {len(rows)}.",
        "",
        f"map_hash_bucket_size {bucket};   # для {len(rows)} точных ключей",
        "map_hash_max_size 4096;",
        "",
        "map $uri $qp_redirect_target {",
        '    default "";',
    ]
    for path, tgt, _kind in rows:
        lines.append(f'    "/{path}" "{tgt}";')
    lines.append("}")
    return "\n".join(lines) + "\n"


def check(rows: list[list]) -> int:
    """Проверить, что все цели отвечают 200. Медленно: 360 запросов."""
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
    print(f"целей проверено: {len(rows)}, не-200: {len(bad)}")
    for code, path, tgt in bad:
        print(f"  [{code}] {path}\n       -> {tgt}")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="дополнительно проверить, что цели отвечают 200")
    args = ap.parse_args()

    rows = build()
    JSON_OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
    NGINX_OUT.parent.mkdir(parents=True, exist_ok=True)
    NGINX_OUT.write_text(nginx_block(rows), encoding="utf-8")
    print(f"правил: {len(rows)}")
    print(f"записано: {JSON_OUT.relative_to(ROOT)}, {NGINX_OUT.relative_to(ROOT)}")
    if args.check:
        return check(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
