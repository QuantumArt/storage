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
            → proxy_pass 127.0.0.1:3023
            → контейнер storage-web (3023)        Dockerfile + site/nginx/default.conf
            → 302 Location: https://github.com/QuantumArt/storage/releases/download/v1/QP8.zip
            → GitHub: 302 → objects.githubusercontent.com → байты
```

**В образе байтов нет.** Контейнер держит одну страницу — индекс состава
хранилища (`tools/build_index.py` генерирует её из манифеста на стадии сборки).
Всё остальное — редиректы.

Контейнер слушает только `127.0.0.1:3023`. Наружу торчит исключительно
хостовый nginx.

## 2. Где лежат байты и почему именно так

Файлы — ассеты GitHub Release [`QuantumArt/storage`](https://github.com/QuantumArt/storage)
тега `v1`. Причины, по которым отброшены другие варианты:

| Вариант | Почему не выбран |
|---|---|
| Бинарники в git | GitHub жёстко блокирует файлы крупнее 100 MiB, а у нас 4 таких: `QP8.ProductCatalog.zip` (183.9 МБ), `QP8.ProductCatalog.Pg.zip` (175.7 МБ), `qp8-product-catalog-linux.tar.gz` (175.1 МБ), `QP8.zip` (171.1 МБ). Опция невозможна физически. |
| Git LFS | Файлы проходят (лимит 2 ГБ на файл), но клон тянет 1.37 ГБ на каждом новом сервере, нужен `git-lfs` на VPS, а перебор квоты без способа оплаты даёт тихую поломку: клон возвращает только pointer-файлы, деплой падает без внятной ошибки. |
| Байты на диске VPS, манифест в git | Рабочий вариант, но раздача зависит от диска сервера, а не от репозитория. |
| **Release + 302 (выбрано)** | Суммарный размер и трафик ассетов GitHub не лимитирует (по документации), лимит только на файл. Бэкап лежит не в git. URL для посетителя — наш домен, тег релиза — внутренняя деталь: переезд хранилища его не сломает. |

**Следствие приватности:** ассеты приватного репозитория анонимно не отдаются
(web-маршрут отдаёт 404 или редирект на логин, API требует токен). Поэтому
`QuantumArt/storage` **публичный** — это условие работоспособности, а не
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

git remote add origin https://github.com/QuantumArt/storage.git
git push -u origin main

# Видимость — публичная (условие анонимной раздачи ассетов)
curl -sS -X PATCH -H "Authorization: Bearer $GH_TOKEN" \
     -H "Accept: application/vnd.github+json" \
     -d '{"visibility":"public"}' \
     https://api.github.com/repos/QuantumArt/storage | python3 -c \
     'import json,sys; print("visibility:", json.load(sys.stdin)["visibility"])'

# Релиз с ассетами (~1.37 ГБ)
gh release create v1 files/* \
    --repo QuantumArt/storage \
    --title "Файлы QP — снимок оригинального хранилища" \
    --notes-file docs/RELEASE-NOTES-v1.md
```

**Токены.** Локально операции идут через `gh` (OAuth-токен аккаунта `anisimovs`,
scope `repo`) — он открывает и `QuantumArt/storage`. На VPS нужен свой
fine-grained PAT в `~/storage/.credentials.env`, потому что глобальный
`/root/.git-credentials` на том сервере отдаёт токен чужого репозитория
и даёт 403 (см. §3 аналога в `anisimovs/downloads`). Спека для коллеги лежит
здесь: отдельного токена на репозиторий `downloads` у нас нет.

**Проверка, что ассеты отдаются анонимно** (без токена!):

```bash
curl -sI https://github.com/QuantumArt/storage/releases/download/v1/QP8.zip | head -3
# 302 → https://objects.githubusercontent.com/...   это и есть успех
```

Если тут 404 или редирект на логин — репозиторий ещё приватный.

## 4. Первый деплой: порядок шагов

Порядок обязателен: нарушишь — получишь невалидный TLS на боевом домене.

### Шаг 0. Проверить порт и DNS

```bash
docker ps --format '{{.Names}}\t{{.Ports}}'
ss -ltnp | grep 3023
dig +short storage.quantumart.ru A
```

`3023` — следующий свободный после `3022`, который занят контейнером
`nuget-baget` (проект nuget, `nuget.qsupport.ru`). Заняты на момент
2026-10-05: **3001, 3010, 3020, 3021, 3022, 5000, 7700, 8090, 9117**.

Порт указан в трёх местах, и они должны совпадать:
`site/docker-compose.production.yml`, `site/deploy.sh` (переменная `PORT`) и
`site/nginx/storage.quantumart.ru` (`proxy_pass`). Занятый порт проявится не
сразу: контейнер поднимется, но хостовой nginx будет проксировать в чужие
контейнеры.

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

Репозиторий **публичный** — клон работает анонимно, токен не нужен:

```bash
git clone https://github.com/QuantumArt/storage.git ~/storage
```

**Если каталог `~/storage` уже существует** (а он обычно существует — ради
`.secrets/cloudflare.ini`), клон падает с
`destination path already exists and is not an empty directory`. Клонировать
поверх нельзя: клон затёр бы секреты. Сначала посмотри, что внутри:

```bash
ls -la ~/storage
```

Если там только `.secrets/` (и, возможно, `.credentials.env`) — инициализируй на
месте, git их не тронет:

```bash
cd ~/storage
git init
git remote add origin https://github.com/QuantumArt/storage.git
GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null \
  git -c credential.helper= fetch origin main
git checkout -B main origin/main
git log --oneline        # убедись, что коммиты есть, а .secrets на месте
```

`GIT_CONFIG_GLOBAL=/dev/null` обязателен: глобальный
`credential.helper=store` на этом сервере отдаёт чужой токен и даёт 403 даже на
публичный репозиторий.

Если в каталоге нет ничего ценного — удали его и клонируй как показано выше.

`.credentials.env` на VPS нужен **только** для `git pull` внутри `deploy.sh`.
Без токена скрипт теперь не падает, а печатает предупреждение и собирает образ
из того, что уже лежит на диске: код меняется редко, и деплой от этого не
страдает.

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
curl -I http://127.0.0.1:3023/
curl -I http://127.0.0.1:3023/downloads/QP8.zip     # 302 + Location

# через хостовый nginx, до переключения DNS
curl -I --resolve storage.quantumart.ru:443:127.0.0.1 https://storage.quantumart.ru/

# после переключения
curl -sI https://storage.quantumart.ru/downloads/QP8.zip | head -3
```

**И главное — проверка скачиванием, а не кодом ответа.** Страница `/` отдаётся
даже тогда, когда ни один файл не отдаётся, поэтому «200 на `/`» не доказывает
ничего. Единственная проверка, которая имеет значение: скачать файл по всей
цепочке и сверить хеш.

```bash
cd ~/storage/site && ./deploy.sh          # шаг 5 делает это сам
```

Шаг 5 `deploy.sh` берёт самый маленький pdf из манифеста, скачивает его через
`https://storage.quantumart.ru/downloads/<файл>`, проходит по всей цепочке
(302 → GitHub → байты) и сверяет размер и sha256. Не сошлось — деплой падает.

На проекте nuget сбой с похожим признаком (`/v3/index.json` отдаёт 200,
healthcheck green, а файлы не открываются) был пойман именно так.

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
gh release create v2 files/* --repo QuantumArt/storage --title "…" --notes-file …

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

## 8. Грабли, унаследованные от соседних проектов

Этот сервер обслуживает несколько проектов, и часть ошибок уже оплачена на
соседях. Здесь они собраны, чтобы не повторять.

| Грабля | Где bitten | Что сделано здесь |
|---|---|---|
| **Порт занят соседом.** 3022 уже занят `nuget-baget` | этот проект изначально планировался на 3022 | Порт **3023**. Проверять `docker ps` перед первым запуском; номер должен совпадать в compose, `deploy.sh` и `nginx/storage.quantumart.ru` |
| **Коллизия имён compose-проектов.** Имя берётся из basename каталога, а каталог у всех `site/` | `nuget`: `down --remove-orphans` в `~/nuget/site` снёс бы боевой `downloads-web` | В compose прописано `name: storage` |
| **Healthcheck на `localhost` вместо `127.0.0.1`** | `downloads`: контейнер уходил в `unhealthy` при живом сайте | `127.0.0.1` и в compose, и в `Dockerfile` |
| **Обрезка архива на таймауте.** 20+ МБ рвётся и оставляет невалидный файл, который выглядит скачанным | `nuget`: `SeleniumExtension 1.0.8–1.0.13` | Тот же класс ловушки пойман здесь трижды, см. §5. Лечится кусочной закачкой + проверкой формата |
| **`xargs -I{}` не масштабируется** | `nuget`: на 629 аргументах `command line cannot be assembled, too long` | Скрипты на цикле, без `xargs -I` |
| **Код ответа на `/` ничего не доказывает** | `nuget`: `/v3/index.json` отдавал 200, healthcheck был green, а файлы не открывались | `deploy.sh`, шаг 5: скачивание файла со сверкой sha256 |
| **Инструмент проверки, который нельзя заставить ошибиться** | `downloads`: скрипт рапортовал «полное совпадение», не заходя на URL без завершающего слэша | У каждой проверки есть обязательный негативный тест, см. `docs/VERIFICATION.md` §5 |
| **Секреты в коммите** | общий риск | `.credentials.env` и `.secrets/` в `.gitignore`, проверка в чек-листе |

**Читать перед деплоем:** `anisimovs/nuget:site/VALIDATION.md` (приёмка и
журнал грабель) и `anisimovs/downloads:docs/DEPLOY-SPEC.md` §3 (авторизация
git на этом VPS).

## 9. Чек-лист

- [ ] Порт 3023 свободен (`docker ps`, `ss -ltnp`)
- [ ] `name: storage` в compose: без него проект называется как каталог
      (`site`) и совпадает с downloads и nuget — `down --remove-orphans`
      в этой папке снёс бы чужие боевые контейнеры
- [ ] `.credentials.env` и `.secrets/` в `.gitignore`; `git status --short` чист
- [ ] Секретов в истории нет: `git log -p --all | grep -c 'github_pat_\|GH_TOKEN=gith'` → 0
- [ ] Репозиторий публичный: `curl -s ... /repos/QuantumArt/storage | grep '"visibility"'`
- [ ] Релиз `v1` создан, 98 ассетов: `gh release view v1 --repo QuantumArt/storage`
- [ ] Ассет отдаётся анонимно: `curl -sI https://github.com/QuantumArt/storage/releases/download/v1/QP8.zip`
- [ ] Сертификат выпущен, домен в `certbot certificates`
- [ ] `nginx -t` проходит **до** reload
- [ ] DNS переключён **после** сертификата и nginx
- [ ] `curl -I https://storage.quantumart.ru/downloads/QP8.zip` → 302 на `objects.githubusercontent.com`

## 10. Логи

### Где лежат

| Слой | Файл | Что пишет | Переживает пересоздание контейнера |
|---|---|---|---|
| Контейнер | `~/storage/site/logs/access.log` | все запросы, пришедшие в контейнер | **да** |
| Контейнер | `~/storage/site/logs/error.log` | ошибки nginx от уровня `warn` | **да** |
| Хостовый nginx | `/var/log/nginx/storage.quantumart.ru.access.log` | все запросы к домену | **да** |
| Хостовый nginx | `/var/log/nginx/storage.quantumart.ru.error.log` | ошибки прокси: 502, таймауты | **да** |

Каталог логов контейнера переопределяется переменной окружения
`ST_LOGS_DIR`, по умолчанию `./logs` рядом с compose-файлом.

**Почему не в `/tmp`:** `/tmp` чистится при перезагрузке. Постоянные данные
кладут рядом с проектом, это же решение в соседнем проекте `downloads`.

**Почему не в `docker logs`:** nginx в образе пишет в `/dev/stdout`, но том
монтируется поверх `/var/log/nginx`, и symlink-и заменяются настоящими
файлами. Побочный эффект: `docker logs storage-web` показывает только вывод
при сбоях и рестартах, но не журнал посещений. В `deploy.sh` шаг 3 поэтому
печатает хвосты файлов, а не `docker logs` — в соседнем проекте там стоит
`docker logs`, и после перехода на файлы он показывает пустоту.

### Как смотреть

```bash
tail -f ~/storage/site/logs/access.log              # кто и что качает
grep ' 404 ' ~/storage/site/logs/access.log         # запросы к несуществующим файлам
grep -E ' (500|502|503|504) ' ~/storage/site/logs/access.log
sudo tail -f /var/log/nginx/storage.quantumart.ru.error.log   # ошибки прокси
```

В access.log видно и код, и URL. Наш 404 отличается от 404-а GitHub: свой
контейнер отвечает `404` сразу, если имени нет в манифесте, и тогда записи в
логе **не будет** — запрос дальше не уходит.

### Ротация

У соседей ротации нет, и логи растут без ограничений. Здесь она приезжает
вместе с проектом:

```bash
sudo cp ~/storage/site/logrotate-storage /etc/logrotate.d/storage
sudo chown root:root /etc/logrotate.d/storage
sudo chmod 644 /etc/logrotate.d/storage
sudo logrotate -d /etc/logrotate.d/storage    # проверка, без применения
```

`copytruncate` обязателен: nginx держит файл открытым, и простое
переименование его не отпустит.

Журнал docker (`json-file`) ограничен отдельно: `max-size 10m`,
`max-file 3` в compose. Основные логи в stdout не идут, но вывод при падении
контейнера идёт, а цикл рестартов без ограничения съел бы диск.
