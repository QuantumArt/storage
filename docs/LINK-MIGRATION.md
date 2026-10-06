# Перенос ссылок на новое хранилище: `storage.quantumart.ru`

Машиночитаемая версия этой спеки — [`manifest/mapping.json`](../manifest/mapping.json),
двухколоночная таблица для замены — [`manifest/migration.csv`](../manifest/migration.csv).

## 1. Суть задачи

В исходниках портала **1 файлов** суммарно ведут 98 ссылок на
`storage.qp.qsupport.ru` — это внешний хост, который мы больше не используем.
Двоичные файлы (1.47 ГБ, 98 шт.) перенесены в
GitHub Release [`QuantumArt/storage`](https://github.com/QuantumArt/storage) тега `v1`, а наш nginx
раздаёт их редиректом 302. Обслуживает зеркало ссылок теперь наш домен.

## 2. Правило замены

Заменяется **только префикс**. Имя файла после него не трогаем.

```
было:  https://storage.qp.qsupport.ru/qa_official_site/images/downloads/<файл>
стало: https://storage.quantumart.ru/downloads/<файл>
```

Ничего больше менять не нужно: ни портрет страниц, ни подписи кнопок, ни
количество вхождений. Одна ссылка на оригинале иногда встречается на
нескольких страницах — заменяются все вхождения.

### Что заменять НЕ надо

Остальные домены остаются как есть: `github.com` (лицензии и репозитории
исходников), `quantumart.ru` (логотип), `reestr.digital.gov.ru` (реестр
российского ПО), `www.npmjs.com` (пакеты), `wiki.qpublishing.ru`,
`nuget.qsupport.ru`. Их суммарно 62 ссылки, они не наше хранилище.

## 3. Единственное исключение — переименование

Один файл на оригинале содержит в имени **кириллическую букву «с»**
(U+0441) вместо латинской `c`. Такое имя требует перцент-энкодинга в URL и
ломает ссылки при копировании, поэтому в новом хранилище файл назван ASCII:

| было | стало |
|---|---|
| `https://storage.qp.qsupport.ru/qa_official_site/images/downloads/QP_Setup_7.9.7.0..zip` | `https://storage.quantumart.ru/downloads/QP_Setup_7.9.7.0.zip` |
| `https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-pg-functional-сharacteristics.pdf` | `https://storage.quantumart.ru/downloads/qp8-pg-functional-characteristics.pdf` |

Байты файла не изменялись — это тот же документ, только имя на диске.

## 4. Где именно менять

Ссылки лежат в 1 файлах исходников (старый путь → новый путь):

- `site/site/src/data/link-migration.json`

Страницы, на которых эти ссылки встречаются, — из перечня ниже.

## 5. Как проверить, что перенос сделан правильно

```bash
# 1. Старых ссылок не осталось ни в одной строке исходников:
grep -rn 'storage.qp.qsupport.ru' site/src && echo 'ЕСТЬ ХВОСТЫ' || echo 'чисто'

# 2. Новых ссылок столько, сколько было (ожидается 98 уникальных вхождений):
grep -rho 'https://storage.quantumart.ru/downloads/[^"]*' site/src | sort -u | wc -l

# 3. Пересобрать сайт — падать не должен ни один шаг:
python3 build.py

# 4. Каждая ссылка из собранного сайта отдаёт 302 на ассет GitHub:
grep -rho 'https://storage.quantumart.ru/downloads/[^"]*' dist | sort -u | while read -r u; do
  printf '%-70s %s\n' "$u" "$(curl -s -o /dev/null -w '%{http_code}' "$u")"
done
```

Ожидаемый результат п. 4: у всех файлов `302` (редирект на ассет GitHub).
Если где-то `404` — такого файла нет в манифесте, ищи его в
[`manifest/mapping.json`](../manifest/mapping.json) и переименуй ссылку на
имя оттуда.

## 6. Что изменится для посетителя

Пользователь по-прежнему видит наш домен. Технически запрос уходит так:

```
браузер → storage.quantumart.ru/downloads/QP8.zip → 302 →
github.com/QuantumArt/storage/releases/download/v1/QP8.zip → 302 →
objects.githubusercontent.com (файл)
```

Два редиректа — норма для ассетов GitHub. Имя сохраняемое файла
остаётся прежним, браузер положит файл под тем же именем.

## 7. Откат

Весь перенос — это изменение 13 файлов исходников плюс сборка. Откат:

```bash
git revert <коммит с заменой ссылок>
python3 build.py
```

**Откат на старый хост больше не вернёт работоспособные ссылки.**
`storage.qp.qsupport.ru` отключён: DNS-запись удалена, хост не резолвится
(проверено 2026-10-06, `curl: (6) Could not resolve host`). Поэтому `git revert`
вернёт ссылки на мёртвый адрес, и все 98 кнопок на портале станут битыми —
вместо «возврата к рабочему состоянию» получится поломка.

Откатываться есть только если **новое** хранилище перестанет работать. Тогда
порядок другой:

1. Проверить, что сломалось: `python3 tools/verify.py --live` в репозитории
   `storage` (запускается с любой машины, токен не нужен для живой проверки).
2. Откатить сайт, чтобы ссылки перестали отдавать 404: `git revert` того же
   коммита со ссылками — да, файлы перестанут открываться, но не будет
   неотличимой от «сломанной ссылки» тишины, и в логах будет видно, что
   дело в отключённом хосте.
3. Восстановить файлы и ссылку: новый релиз `v2` на новом адресе — это
   отдельная работа, шаблон процедуры в `docs/DEPLOY-SPEC.md`, раздел 6.

Практически: пока работает новое хранилище, откатываться не на что. Откат
имеет смысл только как «снять ссылки совсем», а не «вернуть как было».

## 8. Полный перечень (98 файлов)

| файл | размер | страницы |
|---|---:|---|
| `API_ASP.NET_ENG.pdf` | 0.22 МБ | — |
| `Components.zip` | 0.14 МБ | — |
| `Database.Pg.zip` | 1.54 МБ | — |
| `Database.zip` | 1.87 МБ | — |
| `Developer_Guide_ASP.NET_ENG.pdf` | 0.47 МБ | — |
| `Editor_Guide_RUS.pdf` | 2.82 МБ | — |
| `Help_to_QP7_Backend_Explorer_ENG.pdf` | 0.78 МБ | — |
| `Help_to_QP7_Backend_Explorer_RUS.pdf` | 0.85 МБ | — |
| `Multisite_Object_Loading.pdf` | 0.18 МБ | — |
| `QA_LicenceInfo.zip` | 0.12 МБ | — |
| `QP7_Active_Directory.pdf` | 0.12 МБ | — |
| `QP7_Installation_Guide_RUS.pdf` | 0.97 МБ | — |
| `QP7_Notifications.pdf` | 0.27 МБ | — |
| `QP7_OnScreen.pdf` | 0.14 МБ | — |
| `QP7_Security_Model.pdf` | 0.28 МБ | — |
| `QP7_Workflow.pdf` | 0.58 МБ | — |
| `QP8.ConsoleDbUpdate.zip` | 21.07 МБ | — |
| `QP8.ProductCatalog.Impact.zip` | 28.48 МБ | — |
| `QP8.ProductCatalog.PdfGenerator.zip` | 63.63 МБ | — |
| `QP8.ProductCatalog.Pg.zip` | 175.73 МБ | — |
| `QP8.ProductCatalog.zip` | 183.90 МБ | — |
| `QP8.Widgets.Pg.zip` | 95.68 МБ | — |
| `QP8.Widgets.zip` | 96.01 МБ | — |
| `QP8.zip` | 171.09 МБ | — |
| `QP8_CMS_Postgres_Pro.pdf` | 0.22 МБ | — |
| `QP8_PG.zip` | 34.05 МБ | — |
| `QP8_ProductCatalog_Postgres_Pro.pdf` | 0.22 МБ | — |
| `QPCodeClean.zip` | 0.01 МБ | — |
| `QPDatabaseSqlRunner.zip` | 0.01 МБ | — |
| `QPWebService.zip` | 0.19 МБ | — |
| `QP_Setup_7.9.7.0.zip` | 35.01 МБ | — |
| `Quantumart.zip` | 0.32 МБ | — |
| `Release_Notes_RUS.pdf` | 0.28 МБ | — |
| `SQL_injection.pdf` | 0.14 МБ | — |
| `configuration_file.pdf` | 0.17 МБ | — |
| `demo_qp.zip` | 16.29 МБ | — |
| `demosite_rus.tar.gz` | 35.06 МБ | — |
| `demosite_rus_db.tar.gz` | 1.82 МБ | — |
| `functional_char_angular.pdf` | 0.27 МБ | — |
| `functional_char_graphql.pdf` | 0.29 МБ | — |
| `functional_char_react.pdf` | 0.31 МБ | — |
| `graphql-config.tar` | 0.01 МБ | — |
| `graphql.tar.gz` | 4.82 МБ | — |
| `install_angular.pdf` | 1.11 МБ | — |
| `install_graphql.pdf` | 0.49 МБ | — |
| `install_react.pdf` | 1.14 МБ | — |
| `mapping.zip` | 0.01 МБ | — |
| `process_angular.pdf` | 0.42 МБ | — |
| `process_graphql.pdf` | 0.41 МБ | — |
| `process_react.pdf` | 0.42 МБ | — |
| `publishing.zip` | 2.67 МБ | — |
| `qp-search-install-manifests.tar.gz` | 0.00 МБ | — |
| `qp-search.tar.gz` | 23.91 МБ | — |
| `qp.tar.gz` | 47.14 МБ | — |
| `qp8-admin-man.pdf` | 1.51 МБ | — |
| `qp8-dev-man.pdf` | 5.87 МБ | — |
| `qp8-dpc-functional-requirements.pdf` | 0.83 МБ | — |
| `qp8-dpc-impact-functional-requirements.pdf` | 0.78 МБ | — |
| `qp8-dpc-impact-user-man.pdf` | 1.40 МБ | — |
| `qp8-dpc-pdf-functional-requirements.pdf` | 0.78 МБ | — |
| `qp8-dpc-pdf-user-man.pdf` | 1.82 МБ | — |
| `qp8-dpc-user-man.pdf` | 5.81 МБ | — |
| `qp8-editor-man.pdf` | 8.14 МБ | — |
| `qp8-functional-characteristics.pdf` | 0.23 МБ | — |
| `qp8-graphql-user-man.pdf` | 1.70 МБ | — |
| `qp8-pg-admin-man.pdf` | 3.53 МБ | — |
| `qp8-pg-functional-characteristics.pdf` | 0.30 МБ | — |
| `qp8-product-catalog-database.tar.gz` | 3.92 МБ | — |
| `qp8-product-catalog-demo-manifests.tar.gz` | 0.00 МБ | — |
| `qp8-product-catalog-demo.tar.gz` | 1.99 МБ | — |
| `qp8-product-catalog-impact-linux.tar.gz` | 25.08 МБ | — |
| `qp8-product-catalog-impact-manifests.tar.gz` | 0.00 МБ | — |
| `qp8-product-catalog-linux.tar.gz` | 175.14 МБ | — |
| `qp8-product-catalog-manifests.tar.gz` | 0.00 МБ | — |
| `qp8-product-catalog-pdf-manifests.tar.gz` | 0.00 МБ | — |
| `qp8-product-catalog-pdf.tar.gz` | 59.72 МБ | — |
| `qp8-search-admin-user-man.pdf` | 0.84 МБ | — |
| `qp8-search-api-developer-man.pdf` | 0.57 МБ | — |
| `qp8-search-architecture.pdf` | 0.48 МБ | — |
| `qp8-search-functions.pdf` | 0.85 МБ | — |
| `qp8-search-installation-manual.pdf` | 1.53 МБ | — |
| `qp8-search-integration-developer-man.pdf` | 0.62 МБ | — |
| `qp8-search-processes.pdf` | 0.37 МБ | — |
| `qp8-widgets-admin-man.pdf` | 1.64 МБ | — |
| `qp8-widgets-angular-user-man.pdf` | 1.41 МБ | — |
| `qp8-widgets-dev-man.pdf` | 1.14 МБ | — |
| `qp8-widgets-editor-man.pdf` | 2.64 МБ | — |
| `qp8-widgets-functional-requirements.pdf` | 0.80 МБ | — |
| `qp8-widgets-react_user_man.pdf` | 3.15 МБ | — |
| `qpconfig.tar` | 0.02 МБ | — |
| `source.zip` | 7.33 МБ | — |
| `template.zip` | 0.00 МБ | — |
| `widget-angular-config.tar` | 0.01 МБ | — |
| `widget-angular.tar.gz` | 13.09 МБ | — |
| `widget-config.tar` | 0.01 МБ | — |
| `widget-react-config.tar` | 0.01 МБ | — |
| `widget-react.tar.gz` | 10.17 МБ | — |
| `widget.tar.gz` | 69.33 МБ | — |
