"""Сгенерировать человекочитаемый индекс хранилища из манифеста.

Индекс — единственная страница, которую сам storage отдаёт: список файлов с
размерами и sha256, плюс напоминание, что сами байты лежат в GitHub Release.
Нужен, чтобы открыть `https://storage.quantumart.ru/` руками и убедиться, что
сервис жив и состав файлов ожидаемый.

Запускается в стадии сборки образа (вход: /build, выход: /build/index.html).
"""

from __future__ import annotations

import html
import json
from pathlib import Path

BASE = "https://storage.quantumart.ru/downloads/"
RELEASE = "https://github.com/anisimovs/storage/releases/tag/v1"

TYPES = {
    ".zip": "zip-архив",
    ".gz": "gzip-архив",
    ".tar": "tar-архив",
    ".pdf": "PDF-документ",
}


def kind(name: str) -> str:
    for ext, label in TYPES.items():
        if name.endswith(ext):
            return label
    return "файл"


def main() -> None:
    manifest = json.loads(Path("manifest.json").read_text(encoding="utf-8"))
    files = sorted(manifest["files"], key=lambda f: f["name"])
    total = sum(f["size"] for f in files)

    rows = "\n".join(
        f'      <tr><td><a href="{BASE}{html.escape(f["name"])}">{html.escape(f["name"])}</a></td>'
        f'<td class="n">{f["size"] / 1e6:.2f} МБ</td>'
        f'<td>{kind(f["name"])}</td>'
        f'<td class="h"><code>{html.escape(f["sha256"][:16])}</code></td></tr>'
        for f in files if f.get("sha256")
    )

    doc = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Хранилище файлов QP — storage.quantumart.ru</title>
<style>
  body {{ font: 15px/1.5 -apple-system, "Segoe UI", Roboto, sans-serif;
         margin: 2rem auto; max-width: 60rem; padding: 0 1rem; color: #1c1c1e; }}
  h1 {{ font-size: 1.4rem; margin: 0 0 .3rem; }}
  p.note {{ color: #6b6b70; margin: 0 0 1.4rem; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ text-align: left; padding: .35rem .6rem; border-bottom: 1px solid #e5e5ea; }}
  th {{ font-size: .8rem; text-transform: uppercase; letter-spacing: .03em; color: #6b6b70; }}
  td.n {{ text-align: right; white-space: nowrap; color: #6b6b70; }}
  td.h code {{ font-size: .78rem; color: #8a8a8e; }}
  a {{ color: #0a58ca; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  footer {{ margin-top: 1.6rem; font-size: .8rem; color: #8a8a8e; }}
</style>
</head>
<body>
  <h1>Хранилище файлов QP</h1>
  <p class="note">Файлов: {len(files)}, суммарно {total / 1e9:.2f} ГБ.
     Ссылки раздаются редиректом на ассеты GitHub; полный состав с полными
     sha256 — в <a href="https://github.com/anisimovs/storage">репозитории</a>.</p>
  <table>
    <thead><tr><th>Файл</th><th>Размер</th><th>Тип</th><th>sha256</th></tr></thead>
    <tbody>
{rows}
    </tbody>
  </table>
  <footer>Источник правды: <a href="{RELEASE}">Release v1</a>.
     Сгенерировано из manifest/manifest.json.</footer>
</body>
</html>
"""
    Path("index.html").write_text(doc, encoding="utf-8")
    print(f"index.html: {len(files)} файлов, {total / 1e9:.2f} ГБ")


if __name__ == "__main__":
    main()
