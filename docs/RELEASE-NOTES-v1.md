# Файлы QP — снимок оригинального хранилища

Первый срез содержимого хранилища QP. Файлы перенесены с внешнего хоста
`storage.qp.qsupport.ru` (путь `qa_official_site/images/downloads/`) 2026-10-05
и обслуживаются зеркалом портала `downloads.quantumart.ru`.

## Состав

- **98 файлов**, суммарно **1.37 ГБ**
- 4 файла крупнее 100 MiB (лимит Git на GitHub), максимум — `QP8.ProductCatalog.zip`, 183.9 МБ
- Форматы: zip-архивы дистрибутивов, tar.gz с исходниками и демо-сайтами, PDF-руководства

Полный перечень с размерами и sha256 — в
[`manifest/manifest.json`](../manifest/manifest.json) репозитория.

## Как пользоваться

```bash
# Один файл
curl -LO https://github.com/QuantumArt/storage/releases/download/v1/QP8.zip

# Через наш домен (302-редирект на ассет этого релиза)
curl -LO https://storage.quantumart.ru/downloads/QP8.zip
```

## Проверка целостности

sha256 каждого файла — в `manifest/manifest.json`. Сверить:

```bash
curl -sL https://github.com/QuantumArt/storage/releases/download/v1/QP8.zip | shasum -a 256
python3 -c "import json;d=json.load(open('manifest/manifest.json'));print([f['sha256'] for f in d['files'] if f['name']=='QP8.zip'][0])"
```

## Отличия от оригинала

Одно: файл `qp8-pg-functional-сharacteristics.pdf` переименован в
`qp8-pg-functional-characteristics.pdf`. На оригинале в имени стоит кириллическая
буква «с» (U+0441) вместо латинской `c` — такое имя приходится перцент-энкодить
в ссылках. Содержимое файла не изменялось, sha256 совпадает с оригиналом;
оригинальное имя зафиксировано в манифесте полем `original_name`.

Остальные 97 файлов сохранили имена, размеры и содержимое один в один.

## Политика обновления

Тег `v1` — неизменяемый срез. Новые или обновлённые бинарники публикуются
новым релизом (`v2`, `v3`, …); существующие теги не переиспользуются и ассеты
в них не заменяются, чтобы не ломать закэшированные у пользователей ссылки.
Соответствие имён файлов релизам — в `manifest/mapping.json`.

## Происхождение

Все файлы — дистрибутивы, документация и демо-стенды продуктов Quantum Art,
публично раздававшиеся с `storage.qp.qsupport.ru`. Снимок сделан для
независимости портала от внешнего хостинга.
