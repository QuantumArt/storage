# Спека деплоя хранилища `storage.quantumart.ru`

Runbook для этого проекта. Общая методика (структура, обход credential store,
порядок первого деплоя) — в `anisimovs/downloads:docs/DEPLOY-SPEC.md`; здесь
только отличия и особенности. Проверено локально 2026-10-05, деплой на VPS
выполняется вручную: с машины агента SSH на timeweb недоступен.

---

## 1. Схема

```
браузер → storage.quantumart.ru/downloads/QP8.zip
            → хостовый nginx (:443, TLS)          ~/storage/site/nginx/storage.quantumart.ru
            → proxy_pass 127.0.0.1:3022
            → контейнер storage-web               Dockerfile + site/nginx/default.conf
            → 302 Location: https://github.com/anisimovs/storage/releases/download/v1/QP8.zip
            → GitHub: 302 → objects.githubusercontent.com → байты
```

**В образе байтов нет.** Контейнер держит одну страницу — индекс состава
хранилища (`tools/build_index.py` генерирует её из манифеста на стадии сборки).
Всё остальное — редиректы.

Контейнер слушает только `127.0.0.1:3022`. Наружу торчит исключительно
хостовый nginx.

## 2. Где лежат байты и почему именно так

Файлы — ассеты GitHub Release [`anisimovs/storage`](https://github.com/anisimovs/storage)
тега `v1`. Причины, по которым отброшены другие варианты:

| Вариант | Почему не выбран |
|---|---|
| Бинарники в git | GitHub жёстко блокирует файлы крупнее 100 MiB, а у нас 4 таких: `QP8.ProductCatalog.zip` (183.9 МБ), `QP8.ProductCatalog.Pg.zip` (175.7 МБ), `qp8-product-catalog-linux.tar.gz` (175.1 МБ), `QP8.zip` (171.1 МБ). Опция невозможна физически. |
| Git LFS | Файлы проходят (лимит 2 ГБ на файл), но клон тянет 1.37 ГБ на каждом новом сервере, нужен `git-lfs` на VPS, а перебор квоты без способа оплаты даёт тихую поломку: клон возвращает только pointer-файлы, деплой падает без внятной ошибки. |
| Байты на диске VPS, манифест в git | Рабочий вариант, но раздача зависит от диска сервера, а не от репозитория. |
| **Release + 302 (выбрано)** | Суммарный размер и трафик ассетов GitHub не лимитирует (по документации), лимит только на файл. Бэкап лежит не в git. URL для посетителя — наш домен, тег релиза — внутренняя деталь: переезд хранилища его не сломает. |

**Следствие приватности:** ассеты приватного репозитория анонимно не отдаются
(web-маршрут отдаёт 404 или редирект на логин, API требует токен). Поэтому
`anisimovs/storage` **публичный** — это условие работоспособности, а не
оформление. Перед публикацией убедиться, что в индексе нет секретов:
`git ls-files | grep -E 'credentials|secrets'` должен вернуть пусто.

**Что попадает в публичный репозиторий:** код деплоя, `manifest/`
(имена, размеры, sha256, исходные URL), спека для коллеги. Всё это и так
общедоступно на оригинальном хостинге.

## 3. Подготовка на GitHub

Выполняется один раз, с машины агента (PAT в `.credentials.env`).

```bash
cd ~/Projects/storage
set -a && . .credentials.env && set +a

git remote add origin https://github.com/anisimovs/storage.git
git push -u origin main

# Видимость — публичная (условие анонимной раздачи ассетов)
curl -sS -X PATCH -H "Authorization: Bearer $GH_TOKEN" \
     -H "Accept: application/vnd.github+json" \
     -d '{"visibility":"public"}' \
     https://api.github.com/repos/anisimovs/storage | python3 -c \
     'import json,sys; print("visibility:", json.load(sys.stdin)["visibility"])'

# Релиз с ассетами (~1.37 ГБ)
gh release create v1 files/* \
    --repo anisimovs/storage \
    --title "Файлы QP — снимок оригинального хранилища" \
    --notes-file docs/RELEASE-NOTES-v1.md
```

**Токен — fine-grained, открывает только `anisimovs/storage`.** На `downloads`
и `quantumart` он отдаёт 404, поэтому спека для коллеги лежит здесь, а не в
репозитории downloads.

**Проверка, что ассеты отдаются анонимно** (без токена!):

```bash
curl -sI https://github.com/anisimovs/storage/releases/download/v1/QP8.zip | head -3
# 302 → https://objects.githubusercontent.com/...   это и есть успех
```

Если тут 404 или редирект на логин — репозиторий ещё приватный.

## 4. Первый деплой: порядок шагов

Порядок обязателен: нарушишь — получишь невалидный TLS на боевом домене.

### Шаг 0. Проверить порт и DNS

```bash
docker ps --format '{{.Names}}\t{{.Ports}}'
ss -ltnp | grep 3022
dig +short storage.quantumart.ru A
```

`3022` — следующий свободный после `3021` (downloads). Занятые порты на этом
VPS меняются, поэтому проверять обязательно: занятый порт проявится как
«сайт не открывается у соседа».

### Шаг 1. TLS-сертификат — ДО переключения DNS

Общий SAN-сертификат VPS (`ts.sqlhub.pro`) покрывает только `*.sqlhub.pro`.
`storage.quantumart.ru` в другой зоне — нужен отдельный:

```bash
sudo certbot certonly --dns-cloudflare \
  --dns-cloudflare-credentials ~/storage/.secrets/cloudflare.ini \
  -d storage.quantumart.ru --cert-name storage.quantumart.ru

sudo certbot certificates   # домен в списке?
```

Токен Cloudflare лежит в `~/storage/.secrets/cloudflare.ini` — путь
**в каталоге проекта**, не в `~/.secrets/`. Содержимое не выводить.
Автопродление уже настроено через `certbot.timer`.

### Шаг 2. Забрать код

```bash
cd ~/storage
git init                      # только если каталог уже создан вручную
git remote add origin https://github.com/anisimovs/storage.git
set -a && . .credentials.env && set +a
GH_HELPER='!f() { echo username=x-access-token; echo password="$GH_TOKEN"; }; f'
GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null \
  git -c credential.helper="$GH_HELPER" fetch origin main
git checkout -B main origin/main
```

**Клонировать «поверх» нельзя** — в каталоге уже лежат `.credentials.env` и
`.secrets/`, клон их затёр бы. Инициализация на месте, как показано выше.

### Шаг 3. Поднять контейнер

```bash
cd ~/storage/site && ./deploy.sh
```

Скрипт сам подтянет изменения, пересоберёт образ, перезапустит контейнер и
прогонит smoke-test по loopback (см. `site/deploy.sh`, шаг 4).

### Шаг 4. Подключить хостовый nginx

```bash
sudo cp nginx/storage.quantumart.ru /etc/nginx/sites-available/storage.quantumart.ru
sudo ln -s /etc/nginx/sites-available/storage.quantumart.ru \
         /etc/nginx/sites-enabled/storage.quantumart.ru
sudo nginx -t && sudo systemctl reload nginx
```

### Шаг 5. Переключить DNS

A-запись `storage.quantumart.ru` → IP этого VPS. Только теперь: сертификат уже
выпущен, nginx настроен. Проверить: `dig +short storage.quantumart.ru A`
вернул IP этого сервера.

### Шаг 6. Проверка

```bash
# локально, минуя DNS
curl -I http://127.0.0.1:3022/
curl -I http://127.0.0.1:3022/downloads/QP8.zip     # 302 + Location

# через хостовый nginx, до переключения DNS
curl -I --resolve storage.quantumart.ru:443:127.0.0.1 https://storage.quantumart.ru/

# после переключения
curl -sI https://storage.quantumart.ru/downloads/QP8.zip | head -3
```

## 5. Грабли, специфичные для этого проекта

**Оригинальный хост отдаёт сертификат на новом корне Let's Encrypt (ISRG
Root YR), которого нет в старых trust-store.** `curl` работает — он берёт корни
из системного keychain, а Python `urllib`/`requests` на этой машине падает с
`CERTIFICATE_VERIFY_FAILED`. На VPS python может вести себя так же. Отсюда
правило: **скачивание оригинала делает `curl`**, в `tools/fetch_origin.py` это
учтено. Сам сервис во время работы по HTTPS ни к чему не ходит, поэтому на
деплой это не влияет.

**Один файл на оригинале назван с кириллической «с»** —
`qp8-pg-functional-сharacteristics.pdf` (U+0441 вместо латинской `c`). На диске
хранится как `qp8-pg-functional-characteristics.pdf`; оригинальное имя лежит в
манифесте полем `original_name`. Переименование применяется
`tools/fetch_origin.py --normalize`, оно же приводит в порядок манифест.

**В одной из старых ссылок двойной слеш** — `.../downloads//QP7_Active_Directory.pdf`.
Оригинал его отдаёт, новое хранилище — нет. Для коллеги это не проблема
(ссылка заменяется целиком), но при ручной сверке не смущайся разницей.

**Имя файла в URL ограничено `[A-Za-z0-9._-]+`.** Внутриконтейнерный nginx
отсекает всё остальное и отдаёт 404. Так отсекаются вложенные пути, обход
каталога и несуществующие имена.

**301 здесь нельзя, только 302.** Постоянный редирект закешируется браузером
намертво, и при последующем переезде хранилища старые ссылки останутся битыми.

## 6. Обновление состава файлов

```bash
# 1. Добавить/обновить файл локально
curl -fLo files/QP8.1.zip https://storage.qp.qsupport.ru/qa_official_site/images/downloads/QP8.1.zip

# 2. Пересобрать манифест с sha256 (--force перекачает перечисленное заново,
#    без него докачаются только недостающие)
python3 tools/fetch_origin.py

# 3. Пересобрать спеку и маппинг для коллеги
python3 tools/build_migration.py --downloads-dir ~/Projects/downloads

# 4. Новый релиз: старый v1 остаётся как есть, навсегда
gh release create v2 files/* --repo anisimovs/storage --title "…" --notes-file …

# 5. Обновить REPO/RELEASE_TAG в site/nginx/default.conf и tools/build_migration.py,
#    закоммитить, запушить, задеплоить
```

**Старый тег не переиспользуется.** Если бинарь обновился в том же имени, нужен
новый тег и новая ссылка на ассет — иначе браузеры и CDN отдадут закэшированную
старую версию. В заметках релиза писать, что изменилось.

## 7. Откат

```bash
cd ~/storage/site
docker compose -f docker-compose.production.yml down
sudo rm /etc/nginx/sites-enabled/storage.quantumart.ru
sudo nginx -t && sudo systemctl reload nginx
```

Плюс откат A-записи DNS. Контейнер поднимается обратно в любой момент — он ни
от чего на сервере не зависит. Ассеты при откате остаются: откатывается только
раздача.

## 8. Чек-лист

- [ ] Порт 3022 свободен (`docker ps`, `ss -ltnp`)
- [ ] `.credentials.env` и `.secrets/` в `.gitignore`; `git status --short` чист
- [ ] Секретов в истории нет: `git log -p --all | grep -c 'github_pat_\|GH_TOKEN=gith'` → 0
- [ ] Репозиторий публичный: `curl -s ... /repos/anisimovs/storage | grep '"visibility"'`
- [ ] Релиз `v1` создан, 98 ассетов: `gh release view v1 --repo anisimovs/storage`
- [ ] Ассет отдаётся анонимно: `curl -sI https://github.com/anisimovs/storage/releases/download/v1/QP8.zip`
- [ ] Сертификат выпущен, домен в `certbot certificates`
- [ ] `nginx -t` проходит **до** reload
- [ ] DNS переключён **после** сертификата и nginx
- [ ] `curl -I https://storage.quantumart.ru/downloads/QP8.zip` → 302 на `objects.githubusercontent.com`
