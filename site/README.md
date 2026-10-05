# storage.quantumart.ru — хранилище файлов QP

Сервис раздачи дистрибутивов, баз данных, руководств и архивов QP. Заменяет
внешний хост `storage.qp.qsupport.ru`, на который ссылается портал
`downloads.quantumart.ru`.

## Как устроено

```
браузер → https://storage.quantumart.ru/downloads/<файл>
        → nginx на VPS (:443)
        → контейнер storage-web на 127.0.0.1:3022
        → 302 на https://github.com/anisimovs/storage/releases/download/v1/<файл>
        → GitHub отдаёт байты
```

Сам сервис ничего не хранит: в образе есть только страница со списком файлов,
всё остальное — редиректы. Байты лежат ассетами GitHub Release.

Причина такого устройства и разбор альтернатив — в
[`../docs/DEPLOY-SPEC.md`](../docs/DEPLOY-SPEC.md), раздел 2.

## Состав

| Файл | Назначение |
|---|---|
| `Dockerfile` | Двухстадийная сборка: генерация индекса из манифеста → nginx |
| `site/nginx/default.conf` | Внутриконтейнерный конфиг: 302-редиректы, 404, healthcheck |
| `site/nginx/storage.quantumart.ru` | Хостовый server block: TLS + reverse proxy |
| `site/docker-compose.production.yml` | Контейнер `storage-web`, порт `127.0.0.1:3022` |
| `site/deploy.sh` | Деплой: pull → build → restart → smoke-test |
| `tools/fetch_origin.py` | Скачать бинарники с оригинала, посчитать sha256, манифест |
| `tools/build_index.py` | Сгенерировать страницу со списком файлов |
| `tools/build_migration.py` | Маппинг старых ссылок на новые + спека для коллеги |
| `manifest/manifest.json` | Имя, размер, sha256 каждого файла |
| `manifest/mapping.json` | old_url → new_url + страницы, где встречается |
| `manifest/migration.csv` | Таблица замены для коллеги |
| `files/` | Локальная копия бинарников (1.37 ГБ), **в git не идёт** |

## Локальная работа

```bash
# 1. Скачать 98 файлов с оригинала в files/ и собрать манифест (~1.37 ГБ)
python3 tools/fetch_origin.py

# 2. Применить переименования (кириллица → ASCII) к диску и манифесту
python3 tools/fetch_origin.py --normalize

# 3. Пересобрать маппинг и спеку для коллеги
python3 tools/build_migration.py --downloads-dir ~/Projects/downloads

# 4. Собрать и запустить контейнер локально
docker compose -f site/docker-compose.production.yml build
docker compose -f site/docker-compose.production.yml up -d
curl -I http://127.0.0.1:3022/downloads/QP8.zip     # 302 на GitHub
```

Сервис можно гонять локально целиком: редирект формируется без обращения к
GitHub, скачивать байты для проверки не нужно.

## Грабли

- **Python не качает оригинал.** Сертификат `storage.qp.qsupport.ru` выпущен
  на новом корне Let's Encrypt (ISRG Root YR), которого нет в старых
  trust-store: `urllib`/`requests` падают с `CERTIFICATE_VERIFY_FAILED`, `curl`
  работает. Отсюда subprocess-обёртка над curl в `tools/fetch_origin.py`.
- **Файл с кириллицей в имени.** `qp8-pg-functional-сharacteristics.pdf` →
  `qp8-pg-functional-characteristics.pdf`. Оригинальное имя — в поле
  `original_name` манифеста.
- **Токен открывает только `anisimovs/storage`.** На `downloads` и `quantumart`
  отдаёт 404, поэтому спека для коллеги лежит в этом репозитории.
- **Репозиторий обязан быть публичным.** Ассеты приватного репозитория
  анонимно не отдаются.
- **Только 302, никогда 301.** 301 закешируется браузером навсегда.

## Документы

- [`../docs/DEPLOY-SPEC.md`](../docs/DEPLOY-SPEC.md) — runbook деплоя, грабли,
  чек-лист
- [`../docs/LINK-MIGRATION.md`](../docs/LINK-MIGRATION.md) — спека для
  коллеги: как перенести ссылки на новое хранилище
