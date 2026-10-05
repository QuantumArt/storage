#!/usr/bin/env python3
"""Собрать маппинг старых ссылок на новые и спеку для коллеги из downloads.

Читает:
  manifest/manifest.json                     — имена, размеры, sha256 (fetch_origin.py)
  docs/EXTERNAL-LINKS.md репозитория downloads — где каждая ссылка встречается
  (необязательно) исходники downloads          — в каких файлах лежит ссылка

Пишет:
  manifest/mapping.json   — машинный маппинг old_url → new_url + метаданные
  manifest/migration.csv  — две колонки, для механической замены
  docs/LINK-MIGRATION.md  — спека для коллеги

    python3 tools/build_migration.py
    python3 tools/build_migration.py --downloads-dir ~/Projects/downloads
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "manifest" / "manifest.json"
MAPPING = ROOT / "manifest" / "mapping.json"
CSV_OUT = ROOT / "manifest" / "migration.csv"
SPEC = ROOT / "docs" / "LINK-MIGRATION.md"

# Единый источник правды по переименованиям — загрузчик, который качает файлы.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_origin import RENAMES  # noqa: E402

OLD_BASE = "https://storage.qp.qsupport.ru/qa_official_site/images/downloads/"
NEW_BASE = "https://storage.quantumart.ru/downloads/"
REPO = "QuantumArt/storage"
RELEASE_TAG = "v1"

# Допустимые символы в имени ассета. Ровно эта же регулярка стоит во
# внутриконтейнерном nginx (site/nginx/default.conf) — имя, которое ей не
# соответствует, получит 404 на живом сайте.
ASSET_SAFE = re.compile(r"^[A-Za-z0-9._-]+$")

URL_RE = re.compile(r"^- `(https://storage\.qp\.qsupport\.ru/[^`]+)`\s*$")
PAGES_RE = re.compile(r"^\s+- на: (.+)$")


def parse_external_links(path: Path) -> dict[str, list[str]]:
    """URL → список страниц, где встречается. Блок выбран по заголовку раздела.

    Формат в документе — две строки на запись: сама ссылка, затем «- на: …».
    """
    out: dict[str, list[str]] = {}
    inside = False
    pending: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("### "):
            inside = line.startswith("### `storage.qp.qsupport.ru`")
            pending = None
            continue
        if not inside:
            continue
        m = URL_RE.match(line)
        if m:
            pending = m.group(1)
            out.setdefault(pending, [])
            continue
        m = PAGES_RE.match(line)
        if m and pending:
            out[pending] = [p.strip(" `") for p in m.group(1).split(", ")]
    if not out:
        raise SystemExit(f"не нашлось ни одной ссылки storage.qp в {path}")
    return out


def scan_sources(downloads_dir: Path) -> dict[str, list[str]]:
    """URL → список файлов исходников downloads, где ссылка встречается."""
    hits: dict[str, list[str]] = {}
    for p in sorted(downloads_dir.rglob("*")):
        if not p.is_file() or p.suffix not in {".html", ".json", ".py", ".md"}:
            continue
        if any(part in {".git", "dist", ".beads"} for part in p.parts):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        found = sorted(set(re.findall(r"https://storage\.qp\.qsupport\.ru/[^\s\"'`<)]+", text)))
        if found:
            for u in found:
                hits.setdefault(u.rstrip("/"), []).append(str(p.relative_to(downloads_dir)))
    return hits


def build(downloads_dir: Path | None) -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    by_name = {f["name"]: f for f in manifest["files"]}

    pages: dict[str, list[str]] = {}
    src_hits: dict[str, list[str]] = {}
    if downloads_dir:
        doc = downloads_dir / "docs" / "EXTERNAL-LINKS.md"
        if doc.exists():
            pages = parse_external_links(doc)
        src_hits = scan_sources(downloads_dir)

    rows = []
    for f in manifest["files"]:
        # Старый URL берём из манифеста как есть, а не собираем из имени:
        # одна ссылка на оригинале содержит двойной слеш
        # (…/downloads//QP7_Active_Directory.pdf), и пересборка из имени его
        # потеряла бы. Коллеге нужна точная строка для замены.
        # Манифест после --normalize хранит ASCII-имя в name и оригинал
        # в original_name; до нормализации name ещё с кириллицей.
        old = f["url"]
        original = f.get("original_name") or unquote(old.rsplit("/", 1)[-1])
        name = RENAMES.get(original, original)
        new = NEW_BASE + name
        rows.append({
            "name": name,
            "original_name": original,
            "renamed": name != original,
            "old_url": old,
            "new_url": new,
            "size": f["size"],
            "sha256": f["sha256"],
            "pages": pages.get(old, []),
            "source_files": sorted(set(
                src_hits.get(old, []) + src_hits.get(old.rstrip("/"), [])
            )),
        })
    rows.sort(key=lambda r: r["name"])

    unmapped = [r["old_url"] for r in rows if r["old_url"] not in pages]
    return {
        "repo": REPO,
        "release_tag": RELEASE_TAG,
        "old_base": OLD_BASE,
        "new_base": NEW_BASE,
        "count": len(rows),
        "total_bytes": sum(r["size"] for r in rows),
        "renames": RENAMES,
        "urls_in_docs_without_manifest_entry": unmapped,
        "files": rows,
    }


def write_spec(m: dict) -> None:
    renamed = [r for r in m["files"] if r["renamed"]]
    all_pages = sorted({p for r in m["files"] for p in r["pages"]})
    all_files = sorted({f for r in m["files"] for f in r["source_files"]})

    lines = [
        "# Перенос ссылок на новое хранилище: `storage.quantumart.ru`",
        "",
        f"Машиночитаемая версия этой спеки — [`manifest/mapping.json`](../manifest/mapping.json),",
        "двухколоночная таблица для замены — [`manifest/migration.csv`](../manifest/migration.csv).",
        "",
        "## 1. Суть задачи",
        "",
        f"В исходниках портала **{len(all_files)} файлов** суммарно ведут {m['count']} ссылок на",
        "`storage.qp.qsupport.ru` — это внешний хост, который мы больше не используем.",
        f"Двоичные файлы ({m['total_bytes'] / 1e9:.2f} ГБ, {m['count']} шт.) перенесены в",
        f"GitHub Release [`{REPO}`](https://github.com/{REPO}) тега `{RELEASE_TAG}`, а наш nginx",
        "раздаёт их редиректом 302. Обслуживает зеркало ссылок теперь наш домен.",
        "",
        "## 2. Правило замены",
        "",
        "Заменяется **только префикс**. Имя файла после него не трогаем.",
        "",
        "```",
        f"было:  {m['old_base']}<файл>",
        f"стало: {m['new_base']}<файл>",
        "```",
        "",
        "Ничего больше менять не нужно: ни портрет страниц, ни подписи кнопок, ни",
        "количество вхождений. Одна ссылка на оригинале иногда встречается на",
        "нескольких страницах — заменяются все вхождения.",
        "",
        "### Что заменять НЕ надо",
        "",
        "Остальные домены остаются как есть: `github.com` (лицензии и репозитории",
        "исходников), `quantumart.ru` (логотип), `reestr.digital.gov.ru` (реестр",
        "российского ПО), `www.npmjs.com` (пакеты), `wiki.qpublishing.ru`,",
        "`nuget.qsupport.ru`. Их суммарно 62 ссылки, они не наше хранилище.",
        "",
        "## 3. Единственное исключение — переименование",
        "",
    ]
    if renamed:
        lines += [
            "Один файл на оригинале содержит в имени **кириллическую букву «с»**",
            "(U+0441) вместо латинской `c`. Такое имя требует перцент-энкодинга в URL и",
            "ломает ссылки при копировании, поэтому в новом хранилище файл назван ASCII:",
            "",
            "| было | стало |",
            "|---|---|",
        ]
        for r in renamed:
            lines.append(f"| `{r['old_url']}` | `{r['new_url']}` |")
        lines += [
            "",
            "Байты файла не изменялись — это тот же документ, только имя на диске.",
            "",
        ]
    lines += [
        "## 4. Где именно менять",
        "",
        f"Ссылки лежат в {len(all_files)} файлах исходников (старый путь → новый путь):",
        "",
    ]
    for f in all_files:
        lines.append(f"- `site/{f}`")
    lines += [
        "",
        "Страницы, на которых эти ссылки встречаются, — из перечня ниже.",
        "",
        "## 5. Как проверить, что перенос сделан правильно",
        "",
        "```bash",
        "# 1. Старых ссылок не осталось ни в одной строке исходников:",
        "grep -rn 'storage.qp.qsupport.ru' site/src && echo 'ЕСТЬ ХВОСТЫ' || echo 'чисто'",
        "",
        f"# 2. Новых ссылок столько, сколько было (ожидается {m['count']} "
        "уникальных вхождений):",
        "grep -rho 'https://storage.quantumart.ru/downloads/[^\"]*' site/src | sort -u | wc -l",
        "",
        "# 3. Пересобрать сайт — падать не должен ни один шаг:",
        "python3 build.py",
        "",
        "# 4. Каждая ссылка из собранного сайта отдаёт 302 на ассет GitHub:",
        "grep -rho 'https://storage.quantumart.ru/downloads/[^\"]*' dist | sort -u | while read -r u; do",
        "  printf '%-70s %s\\n' \"$u\" \"$(curl -s -o /dev/null -w '%{http_code}' \"$u\")\"",
        "done",
        "```",
        "",
        "Ожидаемый результат п. 4: у всех файлов `302` (редирект на ассет GitHub).",
        "Если где-то `404` — такого файла нет в манифесте, ищи его в",
        "[`manifest/mapping.json`](../manifest/mapping.json) и переименуй ссылку на",
        "имя оттуда.",
        "",
        "## 6. Что изменится для посетителя",
        "",
        "Пользователь по-прежнему видит наш домен. Технически запрос уходит так:",
        "",
        "```",
        "браузер → storage.quantumart.ru/downloads/QP8.zip → 302 →",
        "github.com/QuantumArt/storage/releases/download/v1/QP8.zip → 302 →",
        "objects.githubusercontent.com (файл)",
        "```",
        "",
        "Два редиректа — норма для ассетов GitHub. Имя сохраняемое файла",
        "остаётся прежним, браузер положит файл под тем же именем.",
        "",
        "## 7. Откат",
        "",
        "Весь перенос — это изменение 13 файлов исходников плюс сборка. Откат:",
        "",
        "```bash",
        "git revert <коммит с заменой ссылок>",
        "python3 build.py",
        "```",
        "",
        "Внешний хост `storage.qp.qsupport.ru` на момент составления спеки отвечает",
        "на все 98 файлов кодом `200`, поэтому откат восстанавливает работоспособные",
        "ссылки.",
        "",
        "## 8. Полный перечень (98 файлов)",
        "",
        "| файл | размер | страницы |",
        "|---|---:|---|",
    ]
    for r in m["files"]:
        pages = ", ".join(f"`{p}`" for p in r["pages"]) or "—"
        lines.append(f"| `{r['name']}` | {r['size'] / 1e6:.2f} МБ | {pages} |")

    SPEC.parent.mkdir(parents=True, exist_ok=True)
    SPEC.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--downloads-dir", default="",
                    help="путь к репозиторию downloads (для списка файлов-исходников)")
    args = ap.parse_args()

    if not MANIFEST.exists():
        raise SystemExit(f"нет {MANIFEST} — сначала tools/fetch_origin.py")

    m = build(Path(args.downloads_dir).expanduser() if args.downloads_dir else None)

    MAPPING.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    with CSV_OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["old_url", "new_url"])
        for r in m["files"]:
            w.writerow([r["old_url"], r["new_url"]])
    write_spec(m)

    print(f"файлов в маппинге: {m['count']}, суммарно {m['total_bytes'] / 1e9:.2f} GB")
    print(f"записано: {MAPPING.relative_to(ROOT)}, {CSV_OUT.relative_to(ROOT)}, "
          f"{SPEC.relative_to(ROOT)}")
    if m["urls_in_docs_without_manifest_entry"]:
        print("ВНИМАНИЕ: в EXTERNAL-LINKS.md есть ссылки, которых нет в манифесте:")
        for u in m["urls_in_docs_without_manifest_entry"]:
            print(f"  {u}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
