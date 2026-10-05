# Перенос ссылок на новое хранилище: `storage.quantumart.ru`

Машиночитаемая версия этой спеки — [`manifest/mapping.json`](../manifest/mapping.json),
двухколоночная таблица для замены — [`manifest/migration.csv`](../manifest/migration.csv).

## 1. Суть задачи

В исходниках портала **14 файлов** суммарно ведут 98 ссылок на
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

Ссылки лежат в 14 файлах исходников (старый путь → новый путь):

- `site/docs/EXTERNAL-LINKS.md`
- `site/site/src/data/archive.json`
- `site/site/src/data/index.json`
- `site/site/src/pages/Angular/index.html`
- `site/site/src/pages/DPC.Impact/index.html`
- `site/site/src/pages/DPC.PdfGenerator/index.html`
- `site/site/src/pages/DPC.html`
- `site/site/src/pages/GraphQL/index.html`
- `site/site/src/pages/QP79.html`
- `site/site/src/pages/QP8.html`
- `site/site/src/pages/QP8_PG.html`
- `site/site/src/pages/React/index.html`
- `site/site/src/pages/Widgets.html`
- `site/site/src/pages/search.html`

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

Внешний хост `storage.qp.qsupport.ru` на момент составления спеки отвечает
на все 98 файлов кодом `200`, поэтому откат восстанавливает работоспособные
ссылки.

## 8. Полный перечень (98 файлов)

| файл | размер | страницы |
|---|---:|---|
| `API_ASP.NET_ENG.pdf` | 0.22 МБ | `/QP79`, `/archive/` |
| `Components.zip` | 0.14 МБ | `/archive/` |
| `Database.Pg.zip` | 1.54 МБ | `/`, `/QP8_PG` |
| `Database.zip` | 1.87 МБ | `/`, `/QP8_PG` |
| `Developer_Guide_ASP.NET_ENG.pdf` | 0.47 МБ | `/QP79`, `/archive/` |
| `Editor_Guide_RUS.pdf` | 2.82 МБ | `/QP79`, `/archive/` |
| `Help_to_QP7_Backend_Explorer_ENG.pdf` | 0.78 МБ | `/archive/` |
| `Help_to_QP7_Backend_Explorer_RUS.pdf` | 0.85 МБ | `/archive/` |
| `Multisite_Object_Loading.pdf` | 0.18 МБ | `/archive/` |
| `QA_LicenceInfo.zip` | 0.12 МБ | `/archive/` |
| `QP7_Active_Directory.pdf` | 0.12 МБ | `/archive/` |
| `QP7_Installation_Guide_RUS.pdf` | 0.97 МБ | `/QP79`, `/archive/` |
| `QP7_Notifications.pdf` | 0.27 МБ | `/archive/` |
| `QP7_OnScreen.pdf` | 0.14 МБ | `/archive/` |
| `QP7_Security_Model.pdf` | 0.28 МБ | `/archive/` |
| `QP7_Workflow.pdf` | 0.58 МБ | `/archive/` |
| `QP8.ConsoleDbUpdate.zip` | 21.07 МБ | `/` |
| `QP8.ProductCatalog.Impact.zip` | 28.48 МБ | `/DPC.Impact/` |
| `QP8.ProductCatalog.PdfGenerator.zip` | 63.63 МБ | `/DPC.PdfGenerator/` |
| `QP8.ProductCatalog.Pg.zip` | 175.73 МБ | `/DPC` |
| `QP8.ProductCatalog.zip` | 183.90 МБ | `/DPC` |
| `QP8.Widgets.Pg.zip` | 95.68 МБ | `/Widgets` |
| `QP8.Widgets.zip` | 96.01 МБ | `/Widgets` |
| `QP8.zip` | 171.09 МБ | `/QP8` |
| `QP8_CMS_Postgres_Pro.pdf` | 0.22 МБ | `/QP8_PG` |
| `QP8_PG.zip` | 34.05 МБ | `/QP8_PG` |
| `QP8_ProductCatalog_Postgres_Pro.pdf` | 0.22 МБ | `/DPC` |
| `QPCodeClean.zip` | 0.01 МБ | `/archive/` |
| `QPDatabaseSqlRunner.zip` | 0.01 МБ | `/archive/` |
| `QPWebService.zip` | 0.19 МБ | `/archive/` |
| `QP_Setup_7.9.7.0.zip` | 35.01 МБ | `/QP79` |
| `Quantumart.zip` | 0.32 МБ | `/archive/` |
| `Release_Notes_RUS.pdf` | 0.28 МБ | `/archive/` |
| `SQL_injection.pdf` | 0.14 МБ | `/archive/` |
| `configuration_file.pdf` | 0.17 МБ | `/archive/` |
| `demo_qp.zip` | 16.29 МБ | `/` |
| `demosite_rus.tar.gz` | 35.06 МБ | `/` |
| `demosite_rus_db.tar.gz` | 1.82 МБ | `/`, `/Widgets` |
| `functional_char_angular.pdf` | 0.27 МБ | `/Angular/` |
| `functional_char_graphql.pdf` | 0.29 МБ | `/GraphQL/` |
| `functional_char_react.pdf` | 0.31 МБ | `/React/` |
| `graphql-config.tar` | 0.01 МБ | `/GraphQL/` |
| `graphql.tar.gz` | 4.82 МБ | `/GraphQL/` |
| `install_angular.pdf` | 1.11 МБ | `/Angular/` |
| `install_graphql.pdf` | 0.49 МБ | `/GraphQL/` |
| `install_react.pdf` | 1.14 МБ | `/React/` |
| `mapping.zip` | 0.01 МБ | `/archive/` |
| `process_angular.pdf` | 0.42 МБ | `/Angular/` |
| `process_graphql.pdf` | 0.41 МБ | `/GraphQL/` |
| `process_react.pdf` | 0.42 МБ | `/React/` |
| `publishing.zip` | 2.67 МБ | `/archive/` |
| `qp-search-install-manifests.tar.gz` | 0.00 МБ | `/search` |
| `qp-search.tar.gz` | 23.91 МБ | `/search` |
| `qp.tar.gz` | 47.14 МБ | `/QP8_PG` |
| `qp8-admin-man.pdf` | 1.51 МБ | `/QP8` |
| `qp8-dev-man.pdf` | 5.87 МБ | `/QP8`, `/QP8_PG` |
| `qp8-dpc-functional-requirements.pdf` | 0.83 МБ | `/DPC` |
| `qp8-dpc-impact-functional-requirements.pdf` | 0.78 МБ | `/DPC.Impact/` |
| `qp8-dpc-impact-user-man.pdf` | 1.40 МБ | `/DPC.Impact/` |
| `qp8-dpc-pdf-functional-requirements.pdf` | 0.78 МБ | `/DPC.PdfGenerator/` |
| `qp8-dpc-pdf-user-man.pdf` | 1.82 МБ | `/DPC.PdfGenerator/` |
| `qp8-dpc-user-man.pdf` | 5.81 МБ | `/DPC` |
| `qp8-editor-man.pdf` | 8.14 МБ | `/QP8`, `/QP8_PG` |
| `qp8-functional-characteristics.pdf` | 0.23 МБ | `/QP8` |
| `qp8-graphql-user-man.pdf` | 1.70 МБ | `/GraphQL/` |
| `qp8-pg-admin-man.pdf` | 3.53 МБ | `/QP8_PG` |
| `qp8-pg-functional-characteristics.pdf` | 0.30 МБ | `/QP8_PG` |
| `qp8-product-catalog-database.tar.gz` | 3.92 МБ | `/`, `/DPC` |
| `qp8-product-catalog-demo-manifests.tar.gz` | 0.00 МБ | `/DPC` |
| `qp8-product-catalog-demo.tar.gz` | 1.99 МБ | `/DPC` |
| `qp8-product-catalog-impact-linux.tar.gz` | 25.08 МБ | `/DPC.Impact/` |
| `qp8-product-catalog-impact-manifests.tar.gz` | 0.00 МБ | `/DPC.Impact/` |
| `qp8-product-catalog-linux.tar.gz` | 175.14 МБ | `/DPC` |
| `qp8-product-catalog-manifests.tar.gz` | 0.00 МБ | `/DPC` |
| `qp8-product-catalog-pdf-manifests.tar.gz` | 0.00 МБ | `/DPC.PdfGenerator/` |
| `qp8-product-catalog-pdf.tar.gz` | 59.72 МБ | `/DPC.PdfGenerator/` |
| `qp8-search-admin-user-man.pdf` | 0.84 МБ | `/search` |
| `qp8-search-api-developer-man.pdf` | 0.57 МБ | `/search` |
| `qp8-search-architecture.pdf` | 0.48 МБ | `/search` |
| `qp8-search-functions.pdf` | 0.85 МБ | `/search` |
| `qp8-search-installation-manual.pdf` | 1.53 МБ | `/search` |
| `qp8-search-integration-developer-man.pdf` | 0.62 МБ | `/search` |
| `qp8-search-processes.pdf` | 0.37 МБ | `/search` |
| `qp8-widgets-admin-man.pdf` | 1.64 МБ | `/Widgets` |
| `qp8-widgets-angular-user-man.pdf` | 1.41 МБ | `/Angular/` |
| `qp8-widgets-dev-man.pdf` | 1.14 МБ | `/Widgets` |
| `qp8-widgets-editor-man.pdf` | 2.64 МБ | `/Widgets` |
| `qp8-widgets-functional-requirements.pdf` | 0.80 МБ | `/Widgets` |
| `qp8-widgets-react_user_man.pdf` | 3.15 МБ | `/React/` |
| `qpconfig.tar` | 0.02 МБ | `/QP8_PG` |
| `source.zip` | 7.33 МБ | `/archive/` |
| `template.zip` | 0.00 МБ | `/search` |
| `widget-angular-config.tar` | 0.01 МБ | `/Angular/` |
| `widget-angular.tar.gz` | 13.09 МБ | `/Angular/` |
| `widget-config.tar` | 0.01 МБ | `/Widgets` |
| `widget-react-config.tar` | 0.01 МБ | `/React/` |
| `widget-react.tar.gz` | 10.17 МБ | `/React/` |
| `widget.tar.gz` | 69.33 МБ | `/Widgets` |
