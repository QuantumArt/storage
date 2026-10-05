#!/usr/bin/env python3
"""Скачать бинарники с оригинального хранилища и собрать манифест.

Оригинал: https://storage.qp.qsupport.ru/qa_official_site/images/downloads/
Список берётся из manifest/source-urls.txt (выгрузка из docs/EXTERNAL-LINKS.md
проекта downloads), результат кладётся в files/ и сверяется по sha256.

Почему curl, а не urllib/requests: сертификат оригинала выпущен Let's Encrypt
на новом корне ISRG Root YR, которого нет в старых trust-store (в частности в
macOS system python и в python на VPS). curl берёт корни из системного
keychain и работает, urllib падает с CERTIFICATE_VERIFY_FAILED.

    python3 tools/fetch_origin.py                 # докачать недостающее
    python3 tools/fetch_origin.py --force         # перекачать всё
    python3 tools/fetch_origin.py --jobs 8
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
URLS = ROOT / "manifest" / "source-urls.txt"
FILES = ROOT / "files"
MANIFEST = ROOT / "manifest" / "manifest.json"

RETRIES = 8
CHUNK = 1 << 20
CHUNK_BYTES = 8 << 20   # размер куска при скачивании
CHUNK_TRIES = 20        # попыток на один кусок, прежде чем сдаться на файл

# Единственный файл на оригинале с не-ASCII именем: кириллическая «с» (U+0441)
# вместо латинской c. На диске хранится в ASCII — иначе имя приходится
# перцент-энкодить в каждой ссылке. Оригинальное имя сохраняется в манифесте
# как original_name. Маппинг общий с tools/build_migration.py.
RENAMES = {
    "qp8-pg-functional-сharacteristics.pdf": "qp8-pg-functional-characteristics.pdf",
}


def read_urls() -> list[str]:
    if not URLS.exists():
        sys.exit(f"нет списка ссылок: {URLS}")
    seen: dict[str, None] = {}
    for line in URLS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            seen.setdefault(line, None)
    return list(seen)


def target_name(url: str) -> str:
    """Имя файла на диске = последний сегмент пути, ровно как на оригинале."""
    return unquote(urlsplit(url).path.rsplit("/", 1)[-1])


def curl_size(url: str) -> int:
    p = subprocess.run(
        ["curl", "-sSI", "--max-time", "40", url],
        capture_output=True, text=True,
    )
    for line in p.stdout.splitlines():
        if line.lower().startswith("content-length:"):
            return int(line.split(":", 1)[1].strip())
    return -1


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def fetch(url: str, force: bool) -> dict:
    original = target_name(url)
    name = RENAMES.get(original, original)
    dest = FILES / name
    want = curl_size(url)
    if want < 0:
        return {"url": url, "name": name, "size": 0, "sha256": "", "status": "failed",
                "error": "оригинал не отдал Content-Length — размер неизвестен, "
                         "кусочную докачку применять не к чему"}

    if dest.exists() and not force:
        have = dest.stat().st_size
        if have == want:
            rec = {"url": url, "name": name, "size": have, "sha256": sha256(dest),
                   "status": "cached"}
            if name != original:
                rec["original_name"] = original
            return rec
        dest.unlink()

    tmp = dest.with_suffix(dest.suffix + ".part")
    # Оригинал отдаёт крупные файлы медленно и обрывает длинные соединения, а
    # после обрыва один раз ответил 200 вместо 206 — и `curl -C -` дописал файл
    # целиком к остатку. На диске оказалось 259.9 МБ вместо 175.1 МБ: такой файл
    # выглядит скачанным, но битый. Поэтому качаем явными кусками и проверяем
    # каждый ответ: код 206 и ровно запрошенное число байт. Побочный эффект
    # лучше прежнего: обрыв стоит максимум один кусок, а не весь файл заново.
    last_err = ""
    for attempt in range(1, RETRIES + 1):
        have = tmp.stat().st_size if tmp.exists() else 0
        if have > want:
            # Файл длиннее ожидаемого — прошлый ответ пришёл не по диапазону.
            tmp.unlink()
            have = 0
        if have == want:
            tmp.replace(dest)
            rec = {"url": url, "name": name, "size": dest.stat().st_size,
                   "sha256": sha256(dest), "status": "downloaded"}
            if name != original:
                rec["original_name"] = original
            return rec

        chunk_tries = 0
        while have < want and chunk_tries < CHUNK_TRIES:
            end = min(have + CHUNK_BYTES, want) - 1
            expected = end - have + 1
            p = subprocess.run(
                ["curl", "-sS", "-f", "-r", f"{have}-{end}",
                 "--max-time", "600", "--retry", "0",
                 "-o", str(tmp) + ".chunk", url],
                capture_output=True, text=True,
            )
            chunk = Path(str(tmp) + ".chunk")
            got = chunk.stat().st_size if chunk.exists() else 0
            if p.returncode == 0 and got == expected:
                with tmp.open("ab") as out, chunk.open("rb") as src:
                    shutil.copyfileobj(src, out, CHUNK)
                chunk.unlink()
                have += expected
                chunk_tries = 0
                continue
            chunk.unlink(missing_ok=True)
            chunk_tries += 1
            last_err = (p.stderr.strip() or f"chunk {have}-{end}: "
                        f"got {got} of {expected}")[:200]
            time.sleep(3)
        if chunk_tries >= CHUNK_TRIES:
            break   # кусок не берётся — следующая попытка на весь файл
        time.sleep(min(2 ** attempt, 15))
    tmp.unlink(missing_ok=True)
    return {"url": url, "name": name, "size": want, "sha256": "", "status": "failed",
            "error": last_err}


def normalize_names() -> int:
    """Привести имена на диске и в манифесте к ASCII-виду (идемпотентно).

    Отдельный режим, потому что манифест пишется по итогам загрузки, а переименование
    может быть применено к уже скачанным файлам без повторной закачки 1.37 ГБ.
    """
    changed = 0
    for original, ascii_name in RENAMES.items():
        src, dst = FILES / original, FILES / ascii_name
        if src.exists() and not dst.exists():
            src.rename(dst)
            changed += 1

    if not MANIFEST.exists():
        return changed
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    touched = False
    for entry in manifest["files"]:
        name = entry["name"]
        if name in RENAMES:
            entry["original_name"] = name
            entry["name"] = RENAMES[name]
            touched = True
    if touched:
        MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    return changed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--normalize", action="store_true",
                    help="только применить переименования к файлам и манифесту")
    ap.add_argument("--out", default="files",
                    help="каталог для скачивания (по умолчанию files/)")
    args = ap.parse_args()

    if args.out != "files":
        # Второй проход идёт в отдельный каталог: первый сохраняется как
        # эталон для сверки двух независимых загрузок по sha256.
        global FILES, MANIFEST
        FILES = (ROOT / args.out).resolve()
        MANIFEST = FILES.parent / f"{FILES.name}-manifest.json"

    if args.normalize:
        changed = normalize_names()
        print(f"переименовано файлов: {changed}")
        for f in sorted(FILES.glob("*")):
            if not f.name.isascii():
                print(f"  ОСТАЛОСЬ НЕ-ASCII ИМЯ: {f.name}")
        return 0

    if shutil.which("curl") is None:
        sys.exit("curl не найден")

    urls = read_urls()
    FILES.mkdir(parents=True, exist_ok=True)
    print(f"файлов в списке: {len(urls)}, каталог: {FILES}", flush=True)

    results: list[dict] = []
    done = 0
    with cf.ThreadPoolExecutor(max_workers=args.jobs) as ex:
        for r in ex.map(lambda u: fetch(u, args.force), urls):
            results.append(r)
            done += 1
            print(f"[{done:3}/{len(urls)}] {r['status']:>10}  "
                  f"{r['size'] / 1e6:8.2f} MB  {r['name']}", flush=True)

    results.sort(key=lambda r: r["name"])
    total = sum(r["size"] for r in results if r["size"] > 0)
    manifest = {
        "source_base": "https://storage.qp.qsupport.ru/qa_official_site/images/downloads/",
        "count": len(results),
        "total_bytes": total,
        "files": results,
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    failed = [r for r in results if r["status"] == "failed"]
    print(f"\nскачано/проверено: {len(results) - len(failed)}/{len(results)}, "
          f"всего {total / 1e9:.2f} GB")
    if failed:
        print("НЕ СКАЧАНО:", flush=True)
        for r in failed:
            print(f"  {r['name']}: {r.get('error', '?')}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
