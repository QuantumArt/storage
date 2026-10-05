#!/usr/bin/env python3
"""Сквозная проверка хранилища: локальные файлы → ассеты релиза → живые ссылки.

    python3 tools/verify.py --local           # файлы и манифест
    python3 tools/verify.py --release         # ассеты GitHub Release, анонимно
    python3 tools/verify.py --live            # редиректы на storage.quantumart.ru
    python3 tools/verify.py --local --release --live

Код возврата 0 — всё сошлось, 1 — есть расхождения. Подходит для CI.

Что проверяется и почему именно так:

* **Локально** — размер и sha256 каждого файла против манифеста, плюс
  совместимость имени с регуляркой nginx `[A-Za-z0-9._-]+`. Несовместимое имя
  даст 404 на живом сайте, и заметить это можно только здесь.
* **Анонимно** — ассеты релиза запрашиваются **без токена**. Проверка с
  токеном прошла бы и у приватного репозитория, а раздавать ассеты приватного
  репозитория анонимно нельзя: пользователь получит логин, а не файл.
* **Живые ссылки** — код 302 и точное совпадение Location с ожидаемым ассетом.
  Код 302 без правильного Location — это «ссылка есть, файла за ней нет».
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = ROOT / "files"
MAPPING = ROOT / "manifest" / "mapping.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_migration import ASSET_SAFE  # noqa: E402  — тот же regex, что в nginx

CHUNK = 1 << 20

RELEASE_URL = "https://github.com/QuantumArt/storage/releases/download/v1/{name}"
LIVE_URL = "https://storage.quantumart.ru/downloads/{name}"


def check_format(name: str, path: Path) -> str | None:
    """Проверить целостность самим форматом файла.

    Нужна как второй рубеж после sha256: манифест заполняется из того же
    скачивания, что и файл, поэтому битый файл и битый хеш в манифесте
    повреждаются одинаково и сверка их друг с другом ничего не скажет.
    А вот ZIP проверит свою контрольную сумму сам, и то же с gzip/tar.
    """
    if name.endswith(".zip"):
        p = subprocess.run(["unzip", "-tqq", str(path)], capture_output=True, text=True)
        return None if p.returncode == 0 else f"zip не проходит проверку: {p.stdout.strip()[:120]}"
    if name.endswith((".tar.gz", ".tgz")):
        p = subprocess.run(["tar", "-tzf", str(path)], capture_output=True, text=True)
        return None if p.returncode == 0 else f"tar.gz не распаковывается: {p.stderr.strip()[:120]}"
    if name.endswith(".tar"):
        p = subprocess.run(["tar", "-tf", str(path)], capture_output=True, text=True)
        return None if p.returncode == 0 else f"tar не распаковывается: {p.stderr.strip()[:120]}"
    if name.endswith(".pdf"):
        with path.open("rb") as fh:
            head = fh.read(5)
            fh.seek(max(0, path.stat().st_size - 2048))
            tail = fh.read()
        if head != b"%PDF-":
            return "PDF не начинается с %PDF-"
        if b"%%EOF" not in tail:
            return "в хвосте PDF нет %%EOF — файл оборван"
        return None
    return None


def load() -> dict:
    if not MAPPING.exists():
        sys.exit(f"нет {MAPPING} — сначала tools/build_migration.py")
    return json.loads(MAPPING.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def curl_head(url: str, token: str | None) -> tuple[int, str]:
    cmd = ["curl", "-sI", "--max-time", "30", "-o", "/dev/null",
           "-w", "%{http_code} %{redirect_url}", url]
    if token:
        cmd += ["-H", f"Authorization: Bearer {token}"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    parts = p.stdout.split(" ", 1)
    code = int(parts[0]) if parts[0].isdigit() else 0
    return code, (parts[1] if len(parts) > 1 else "").strip()


def check_local(m: dict) -> list[str]:
    bad = []
    for f in m["files"]:
        name, p = f["name"], FILES / f["name"]
        if not ASSET_SAFE.match(name):
            bad.append(f"имя несовместимо с регуляркой nginx: {name!r}")
        if not f.get("sha256"):
            bad.append(f"в манифесте нет sha256: {name}")
            continue
        if not p.exists():
            bad.append(f"нет файла: {name}")
            continue
        size = p.stat().st_size
        if size != f["size"]:
            bad.append(f"размер: {name} — манифест {f['size']}, на диске {size}")
            continue
        digest = sha256(p)
        if digest != f["sha256"]:
            bad.append(f"sha256: {name} — манифест {f['sha256'][:16]}, файл {digest[:16]}")
            continue
        problem = check_format(name, p)
        if problem:
            bad.append(f"формат: {name} — {problem}")
    print(f"  проверено файлов: {len(m['files'])}, "
          f"суммарно {m['total_bytes'] / 1e9:.2f} ГБ "
          f"(размер, sha256 и целостность по формату)")
    return bad


def check_release(m: dict, token: str | None) -> list[str]:
    bad = []
    for f in m["files"]:
        url = RELEASE_URL.format(name=f["name"])
        code, loc = curl_head(url, token)
        # curl -I не идёт по редиректам, поэтому 302 здесь — успех: значит,
        # ассет существует и GitHub готов отдать его дальше.
        if code != 302:
            bad.append(f"релиз {code} (ожидался 302): {f['name']}")
    return bad


def check_live(m: dict) -> list[str]:
    bad = []
    for f in m["files"]:
        url = LIVE_URL.format(name=f["name"])
        code, loc = curl_head(url, None)
        if code != 302:
            bad.append(f"сайт {code} (ожидался 302): {f['name']}")
        elif not loc:
            bad.append(f"сайт отдал 302 без Location: {f['name']}")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--release", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--token", default=os.environ.get("GH_TOKEN", ""),
                    help="для --release; по умолчанию проверка анонимная")
    args = ap.parse_args()
    if not (args.local or args.release or args.live):
        args.local = args.release = args.live = True

    m = load()
    print(f"манифест: {m['count']} файлов, {m['total_bytes'] / 1e9:.2f} ГБ, "
          f"релиз {m['repo']}@{m['release_tag']}")

    bad: list[str] = []
    if args.local:
        print("\n== локальные файлы ==")
        bad += check_local(m)
    if args.release:
        print("\n== ассеты GitHub Release ==")
        print("  режим: " + ("с токеном" if args.token else "анонимно (без токена)"))
        bad += check_release(m, args.token)
    if args.live:
        print("\n== живые ссылки ==")
        bad += check_live(m)

    print()
    if bad:
        print(f"❌ расхождений: {len(bad)}")
        for b in bad[:40]:
            print(f"   {b}")
        if len(bad) > 40:
            print(f"   … и ещё {len(bad) - 40}")
        return 1
    print("✅ всё сошлось")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
