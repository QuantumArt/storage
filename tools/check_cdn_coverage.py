"""Проверка покрытия ссылок quantumart на локальные ассеты _cdn.

Использование: python3 tools/check_cdn_coverage.py
Ничего не меняет, только читает.
"""
from __future__ import annotations

import html
import json
import os
import re

QROOT = "/Users/anisimovs/Projects/quantumart"
MIG = os.path.join(QROOT, "site/src/data/link-migration.json")
BLOCKS = os.path.join(QROOT, "site/src/data/blocks.json")
CDN = os.path.join(QROOT, "site/src/static/_cdn")

data = open(MIG, encoding="utf-8").read()
mig = json.loads(data)
old = mig["cdn_prefix_old"]
docs = mig["documents"]

raw = open(BLOCKS, encoding="utf-8").read()

# URL целиком: останавливаемся на пробеле, кавычке или обратном слэше
pattern = re.compile(r"https://storage\.qp\.qsupport\.ru/[^\"\'\\]*?(?=[\s\"\'\\]|$)")
urls = set(pattern.findall(raw))

missing = []
docs_count = 0
for u in sorted(urls):
    if u in docs:
        docs_count += 1
        continue
    if not u.startswith(old):
        missing.append(("НЕ-ПРЕФИКС", u))
        continue
    tail = html.unescape(u[len(old):])
    if not os.path.exists(os.path.join(CDN, tail)):
        missing.append(("НЕТ-ФАЙЛА", tail))

print(f"уникальных ссылок на старый домен в blocks.json: {len(urls)}")
print(f"из них ведут на документы (storage.quantumart.ru): {docs_count}")
print(f"cdn-целей, которых нет в site/src/static/_cdn: {len(missing)}")
for kind, name in missing:
    print(f"   [{kind}] {name}")
