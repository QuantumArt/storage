#!/usr/bin/env python3
"""Переписать ссылки на старый хост внутри PDF инструкций.

Зачем: ссылки внутри PDF ведут на storage.qp.qsupport.ru — домен без
DNS-записи. Читатель инструкции кликает по ссылке и получает ошибку.
Алиас-перенаправление мы не поднимаем, поэтому единственный способ починить
ссылки — переписать их прямо в файлах, которые мы раздаём.

Что меняется: только текст ссылок (аннотации /A /URI). Содержимое страниц,
картинки, шрифты и разметка не трогаются — проверяется побайтовым сравнением
распакованных потоков содержимого до и после.

Чего это стоит: байты перестают совпадать с оригиналом. Оригинальные файлы
остаются в истории git, их хеши — в manifest/reference-sha256.txt (это
baseline для скачивания с оригинала, он остаётся нетронутым), а хеши того,
что мы раздаём, — в manifest/manifest.json.

Требуется pikepdf (qpdf):
    python3 -m venv .venv-pdf && .venv-pdf/bin/pip install pikepdf
    .venv-pdf/bin/python tools/rewrite_pdf_links.py

Запуск:
    python3 tools/rewrite_pdf_links.py            # переписать
    python3 tools/rewrite_pdf_links.py --dry-run  # только показать, что будет
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

try:
    import pikepdf
except ImportError:
    sys.exit("нужен pikepdf: python3 -m pip install pikepdf  (или venv, см. докстринг)")

ROOT = Path(__file__).resolve().parent.parent
FILES = ROOT / "files"
MAP = ROOT / "manifest" / "link-map.json"
REWRITTEN = ROOT / "manifest" / "rewritten-files.txt"

OLD_HOST = "storage.qp.qsupport.ru"


def link_map() -> dict[str, str]:
    rows = json.loads(MAP.read_text(encoding="utf-8"))
    return {r[0]: r[1] for r in rows}


def key_of(url: str) -> str:
    p = unquote(urlsplit(url).path).lstrip("/")
    while "//" in p:
        p = p.replace("//", "/")
    return p


def uri_of(annot) -> str | None:
    action = annot.get("/A")
    if action is not None and str(action.get("/S")) == "/URI":
        return str(action.get("/URI"))
    return None


def stream_bytes(contents) -> bytes:
    """Содержимое страницы.

    /Contents бывает не одним потоком, а массивом потоков (несколько блоков
    содержимого на страницу) — тогда чтение одного объекта падает с
    «operation for stream attempted on object of type array».
    """
    if contents is None:
        return b""
    try:
        return contents.read_bytes()
    except Exception:
        return b"".join(c.read_bytes() for c in contents)


def page_fingerprints(pdf) -> list[tuple[str, str]]:
    """Отпечатки страниц: хеш потока содержимого + размер страницы.

    Сравниваются до и после перезаписи: если содержимое изменилось, значит
    инструмент тронул не только ссылки.
    """
    out = []
    for page in pdf.pages:
        data = stream_bytes(page.get("/Contents"))
        out.append((hashlib.sha256(data).hexdigest(),
                    str(page.get("/MediaBox", ""))))
    return out


def rewrite_one(path: Path, mapping: dict[str, str], dry_run: bool) -> dict:
    report = {"file": path.name, "replaced": 0, "unmapped": [], "size_before": 0,
              "size_after": 0, "status": "skipped"}
    original_bytes = path.read_bytes()
    report["size_before"] = len(original_bytes)

    pdf = pikepdf.open(path)
    before = page_fingerprints(pdf)
    targets = []
    for page in pdf.pages:
        annots = page.get("/Annots")
        if not annots:
            continue
        for annot in annots:
            uri = uri_of(annot)
            if not uri or OLD_HOST not in uri:
                continue
            key = key_of(uri)
            if key not in mapping:
                report["unmapped"].append(uri)
                continue
            targets.append((annot, mapping[key]))

    if not targets:
        pdf.close()
        return report

    report["replaced"] = len(targets)
    if dry_run:
        pdf.close()
        report["status"] = "dry-run"
        return report

    for annot, new_uri in targets:
        annot["/A"]["/URI"] = pikepdf.String(new_uri)

    tmp = path.with_suffix(".pdf.tmp")
    pdf.save(str(tmp), compress_streams=True)
    pdf.close()

    # Проверка результата до того, как он заменит оригинал.
    check = pikepdf.open(str(tmp))
    after = page_fingerprints(check)
    left = []
    for page in check.pages:
        for annot in (page.get("/Annots") or []):
            uri = uri_of(annot)
            if uri and OLD_HOST in uri:
                left.append(uri)
    check.close()

    if len(before) != len(after) or before != after:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"{path.name}: содержимое страниц изменилось — правка отменена")
    if left:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"{path.name}: остались ссылки на старый хост — правка отменена")

    os.replace(tmp, path)
    report["size_after"] = path.stat().st_size
    report["status"] = "rewritten"
    return report


def remember(path: Path) -> None:
    """Отметить файл как переписанный: загрузчик не должен вернуть оригинал."""
    names = []
    if REWRITTEN.exists():
        names = [l.strip() for l in REWRITTEN.read_text(encoding="utf-8").splitlines()
                 if l.strip() and not l.startswith("#")]
    if path.name not in names:
        names.append(path.name)
    REWRITTEN.write_text(
        "# Файлы, в которых ссылки на старый хост переписаны на новые адреса.\n"
        "#\n"
        "# Байты этих файлов намеренно отличаются от оригинала на старом хосте:\n"
        "# переписаны тексты ссылок внутри PDF. Оригинальные хеши — в\n"
        "# manifest/reference-sha256.txt (baseline для скачивания с оригинала),\n"
        "# хеши того, что мы раздаём, — в manifest/manifest.json.\n"
        "#\n"
        "# tools/fetch_origin.py не перекачивает эти файлы: иначе правка\n"
        "# ссылок молча потерялась бы.\n"
        + "\n".join(sorted(names)) + "\n",
        encoding="utf-8")
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="только показать, что будет переписано")
    args = ap.parse_args()

    mapping = link_map()
    pdfs = sorted(FILES.glob("*.pdf"))
    print(f"PDF в files/: {len(pdfs)}")
    changed = 0
    problems = 0
    for p in pdfs:
        try:
            rep = rewrite_one(p, mapping, args.dry_run)
        except Exception as exc:
            print(f"  ОШИБКА {p.name}: {exc}")
            problems += 1
            continue
        if rep["status"] in ("rewritten", "dry-run"):
            changed += 1
            delta = rep["size_after"] - rep["size_before"] if rep["size_after"] else 0
            print(f"  {rep['replaced']:3} ссылок  {p.name}"
                  f"{'' if not delta else f'  ({delta/1e6:+.2f} МБ)'}")
            if rep["unmapped"]:
                problems += 1
                for u in rep["unmapped"]:
                    print(f"        НЕ В КАРТЕ: {u}")
            if not args.dry_run:
                remember(p)
        elif rep["status"] == "skipped" and rep["size_before"]:
            pass
    print(f"переписано файлов: {changed}, проблем: {problems}")
    if not args.dry_run and changed:
        print("далее: python3 tools/refresh_manifest.py, перезалить ассеты, "
              "пересобрать и задеплоить образ")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
