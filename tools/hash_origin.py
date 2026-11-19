"""Побайтовая сверка файлов релиза с оригиналом storage.qp.qsupport.ru (параллельно).

Оригинал доступен по IP (DNS-запись удалена), поэтому идём через --resolve.

Важное: оригинал отдаёт файлы через ARR и при параллельной нагрузке обрывает
соединение на середине. Обрыв НЕ является расхождением содержимого — это
 оборванная загрузка. Поэтому результат проверяется по двум признакам:
   1. длина ответа совпадает с content-length из HEAD,
   2. sha256 совпадает с эталоном манифеста.
Недокачанное перекачивается (до 5 попыток), и только исчерпание попыток
фиксируется как MISMATCH — с указанием, что это «обрыв», а не «другое
содержимое».

Результат пишется построчно в /tmp/orig_sha256.tsv — прогресс переживает
перезапуск, уже посчитанные файлы пропускаются.

Использование: python3 tools/hash_origin.py [число потоков]
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ORIG_IP = "91.216.147.7"
ORIG_HOST = "storage.qp.qsupport.ru"
OLD_BASE = ""  # старый URL берётся из манифеста целиком
OUT = "/tmp/orig_sha256.tsv"
ATTEMPTS = 5

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def targets():
    """Возвращает (имя, полный старый URL, sha256, размер).

    Старый URL берётся из манифеста целиком: у файлов проекта downloads это
    .../images/downloads/<файл>, у документов quantumart — .../images/presentation/
    и .../images/documents/. Префикс не вырезается, иначе для quantumart
    получился бы несуществующий путь и пустой ответ.
    """
    out = []
    for name in ("mapping.json", "mapping-quantumart.json"):
        m = json.load(open(os.path.join(ROOT, "manifest", name)))
        for f in m["files"]:
            out.append((f["name"], f["old_url"], f["sha256"], f["size"]))
    return out


def load_done():
    done = {}
    if os.path.exists(OUT):
        for line in open(OUT):
            parts = line.rstrip("\n").split("\t")
            if len(parts) == 4 and parts[2] == "OK":
                done[parts[0]] = parts
    return done


def head_len(old):
    r = subprocess.run(
        ["curl", "-sSI", "--max-time", "60",
         "--resolve", f"{ORIG_HOST}:443:{ORIG_IP}", old],
        capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if line.lower().startswith("content-length:"):
            return int(line.split(":", 1)[1].strip())
    return None


def hash_one(job):
    name, old, ours, our_size = job
    expected = head_len(old) or our_size
    data = b""
    for attempt in range(1, ATTEMPTS + 1):
        r = subprocess.run(
            ["curl", "-sS", "--max-time", "900",
             "--resolve", f"{ORIG_HOST}:443:{ORIG_IP}", old],
            capture_output=True)
        data = r.stdout
        if len(data) == expected:
            break
        print(f"  обрыв {name}: {len(data)} из {expected} (попытка {attempt})", flush=True)
    h = hashlib.sha256(data).hexdigest()
    if len(data) != expected:
        status = "TRUNCATED"
    elif h == ours:
        status = "OK"
    else:
        status = "MISMATCH"
    row = [name, str(len(data)), status, h]
    with open(OUT, "a") as fh:
        fh.write("\t".join(row) + "\n")
    print(f"{status:9} {name} {row[1]}", flush=True)
    return row


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    done = load_done()
    todo = [t for t in targets() if t[0] not in done]
    print(f"к сверке: {len(todo)} (уже {len(done)})", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        rows = list(ex.map(hash_one, todo))
    bad = [r for r in rows if r[2] != "OK"]
    print(f"\nсверено {len(rows)} | OK {len(rows)-len(bad)} | проблем {len(bad)}")
    for r in bad:
        print(f"  {r[2]} {r[0]} {r[1]} {r[3]}")


if __name__ == "__main__":
    main()
