#!/bin/bash
# ─── Скачать бинарники QP с оригинального хранилища и выдать sha256 ─────────
# Сгенерировано tools/make_vps_script.py из manifest/source-urls.txt.
# Правь источник, а не этот файл: при следующей генерации правки пропадут.
#
# Смысл: на VPS канал до storage.qp.qsupport.ru быстрый и стабильный, с машины
# агента он рвётся. Скачав здесь, получаем независимый второй экземпляр
# каждого файла — два прохода сводятся сверкой sha256, и это единственный
# способ доказать, что файл не побит: у оригинала нет эталонных хешей,
# в ETag IIS лежит только метка «время+размер».
#
# Запуск:
#   ./fetch_on_vps.sh                     # в /tmp/qp-files
#   OUT=/srv/whatever ./fetch_on_vps.sh   # в другой каталог
#   LIMIT=5 ./fetch_on_vps.sh             # первые 5 URL — проверить скрипт
#   FORCE=1 ./fetch_on_vps.sh             # перекачать всё начисто
#
# Что проверяется по ходу:
#   1. размер каждого файла против Content-Length оригинала;
#   2. целостность архива его же средствами (unzip -t, tar -t, маркеры PDF).
# Результат: /tmp/qp-files.sha256 в формате sha256sum — его можно скормить
# локальному `sha256sum -c`.

set -uo pipefail

OUT="${OUT:-/tmp/qp-files}"
JOBS="${JOBS:-6}"
FORCE="${FORCE:-0}"
LIST=$(mktemp)
mkdir -p "$OUT"

cat > "$LIST" <<'URLS_EOF'
https://storage.qp.qsupport.ru/qa_official_site/images/downloads//QP7_Active_Directory.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/API_ASP.NET_ENG.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/Components.zip
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/Database.Pg.zip
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/Database.zip
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/Developer_Guide_ASP.NET_ENG.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/Editor_Guide_RUS.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/Help_to_QP7_Backend_Explorer_ENG.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/Help_to_QP7_Backend_Explorer_RUS.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/Multisite_Object_Loading.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/QA_LicenceInfo.zip
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/QP7_Installation_Guide_RUS.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/QP7_Notifications.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/QP7_OnScreen.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/QP7_Security_Model.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/QP7_Workflow.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/QP8.ConsoleDbUpdate.zip
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/QP8.ProductCatalog.Impact.zip
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/QP8.ProductCatalog.PdfGenerator.zip
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/QP8.ProductCatalog.Pg.zip
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/QP8.ProductCatalog.zip
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/QP8.Widgets.Pg.zip
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/QP8.Widgets.zip
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/QP8.zip
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/QP8_CMS_Postgres_Pro.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/QP8_PG.zip
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/QP8_ProductCatalog_Postgres_Pro.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/QPCodeClean.zip
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/QPDatabaseSqlRunner.zip
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/QPWebService.zip
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/QP_Setup_7.9.7.0..zip
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/Quantumart.zip
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/Release_Notes_RUS.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/SQL_injection.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/configuration_file.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/demo_qp.zip
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/demosite_rus.tar.gz
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/demosite_rus_db.tar.gz
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/functional_char_angular.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/functional_char_graphql.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/functional_char_react.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/graphql-config.tar
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/graphql.tar.gz
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/install_angular.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/install_graphql.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/install_react.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/mapping.zip
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/process_angular.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/process_graphql.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/process_react.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/publishing.zip
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp-search-install-manifests.tar.gz
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp-search.tar.gz
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp.tar.gz
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-admin-man.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-dev-man.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-dpc-functional-requirements.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-dpc-impact-functional-requirements.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-dpc-impact-user-man.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-dpc-pdf-functional-requirements.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-dpc-pdf-user-man.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-dpc-user-man.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-editor-man.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-functional-characteristics.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-graphql-user-man.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-pg-admin-man.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-pg-functional-сharacteristics.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-product-catalog-database.tar.gz
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-product-catalog-demo-manifests.tar.gz
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-product-catalog-demo.tar.gz
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-product-catalog-impact-linux.tar.gz
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-product-catalog-impact-manifests.tar.gz
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-product-catalog-linux.tar.gz
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-product-catalog-manifests.tar.gz
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-product-catalog-pdf-manifests.tar.gz
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-product-catalog-pdf.tar.gz
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-search-admin-user-man.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-search-api-developer-man.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-search-architecture.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-search-functions.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-search-installation-manual.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-search-integration-developer-man.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-search-processes.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-widgets-admin-man.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-widgets-angular-user-man.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-widgets-dev-man.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-widgets-editor-man.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-widgets-functional-requirements.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qp8-widgets-react_user_man.pdf
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/qpconfig.tar
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/source.zip
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/template.zip
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/widget-angular-config.tar
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/widget-angular.tar.gz
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/widget-config.tar
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/widget-react-config.tar
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/widget-react.tar.gz
https://storage.qp.qsupport.ru/qa_official_site/images/downloads/widget.tar.gz
URLS_EOF

if [ -n "${LIMIT:-}" ]; then
    head -n "$LIMIT" "$LIST" > "$LIST.lim" && mv "$LIST.lim" "$LIST"
fi

TOTAL=$(wc -l < "$LIST" | tr -d ' ')
echo "==> Файлов в задании: $TOTAL, каталог: $OUT, потоков: $JOBS"

# ── TLS ──────────────────────────────────────────────────────────────────────
# Сертификат оригинала выпущен Let's Encrypt на корне ISRG Root YR. На системе
# с устаревшим ca-certificates проверка может не пройти — тогда curl падает с
# CERTIFICATE_VERIFY_FAILED. Правильное лечение — обновить пакет, а не
# отключать проверку; ослабленный режим включается явно:
#   ALLOW_INSECURE=1 ./fetch_on_vps.sh
TLS_ARGS=()
if [ "${ALLOW_INSECURE:-0}" = "1" ]; then
    TLS_ARGS=(-k)
    echo "⚠️  Проверка TLS ОТКЛЮЧЕНА (ALLOW_INSECURE=1) — содержимое не аутентифицировано"
fi

if ! curl -sI "${TLS_ARGS[@]+"${TLS_ARGS[@]}"}" \
        https://storage.qp.qsupport.ru/qa_official_site/images/downloads/API_ASP.NET_ENG.pdf \
        >/dev/null 2>&1; then
    echo "❌ Не удалось достучаться до оригинала с проверкой TLS."
    echo "   Обновите корни:  sudo apt-get update && sudo apt-get install --reinstall ca-certificates"
    echo "   Или ослабьте:    ALLOW_INSECURE=1 $0"
    rm -f "$LIST"
    exit 1
fi
echo "==> TLS в порядке, оригинал отвечает"

# ── проверка целостности форматом ───────────────────────────────────────────
# Молчаливый вывод: результат проверки возвращается кодом, а вердикт печатает
# вызывающий. Иначе строка «битый архив» попадёт в разбор результатов как
# отдельный файл.
have_zipcheck=0; command -v unzip >/dev/null 2>&1 && have_zipcheck=1

check_format() {
    local f="$1" n="$2"
    if [ "$have_zipcheck" = "1" ] && case "$n" in *.zip) true;; *) false;; esac; then
        unzip -tqq "$f" >/dev/null 2>&1
        return $?
    fi
    case "$n" in
        *.tar.gz|*.tgz) tar -tzf "$f" >/dev/null 2>&1 ;;
        *.tar)          tar -tf  "$f" >/dev/null 2>&1 ;;
        *.pdf)          head -c 5 "$f" | grep -q '%PDF-' \
                      && tail -c 2048 "$f" | grep -q '%%EOF' ;;
        *)              return 0 ;;
    esac
}

# ── скачивание одного файла ──────────────────────────────────────────────────
# Каждый файл завершается ровно одной строкой: OK / CACHED / FAIL. По этой
# строке считается итог, поэтому промежуточные сообщения (REDO) уходят в stderr
# и в подсчёт не попадают.
fetch_one() {
    local url="$1" name out want size tmp rc
    name="${url##*/}"
    out="$OUT/$name"

    want=$(curl -sI "${TLS_ARGS[@]+"${TLS_ARGS[@]}"}" "$url" \
           | tr -d '\r' | awk 'tolower($1)=="content-length:"{print $2}' | tail -1)
    if [ -z "$want" ]; then
        echo "FAIL $name no-content-length"
        return 1
    fi

    if [ "$FORCE" = "1" ]; then rm -f "$out"; fi

    if [ -f "$out" ]; then
        size=$(wc -c < "$out" 2>/dev/null | tr -d ' ')
        if [ "$size" = "$want" ] && check_format "$out" "$name"; then
            echo "CACHED $name"
            return 0
        fi
        # Правильный размер НЕ означает целый файл: оригинал один раз отдал
        # битые байты с корректным Content-Length, и такой файл проходит
        # проверку размера. Поэтому файл с верным размером, но непроходящим
        # форматом, перекачивается.
        echo "REDO $name (размер $size из $want, формат не прошёл) — перекачиваю" >&2
        rm -f "$out"
    fi

    tmp="$out.part"
    rm -f "$tmp"
    # --retry на сетевых обрывах; соединения на VPS стабильные, но мало ли.
    curl -fL ${TLS_ARGS[@]+"${TLS_ARGS[@]}"} \
         --retry 5 --retry-delay 3 --retry-connrefused \
         --max-time 3600 -o "$tmp" "$url"
    rc=$?
    if [ $rc -ne 0 ]; then
        echo "FAIL $name curl-rc-$rc"
        rm -f "$tmp"
        return 1
    fi

    size=$(wc -c < "$tmp" 2>/dev/null | tr -d ' ')
    if [ "$size" != "$want" ]; then
        # Оригинал один раз ответил 200 вместо 206 на запрос диапазона, и файл
        # получился длиннее нужного. Молча принимать такое нельзя.
        echo "FAIL $name size-$size-expected-$want"
        rm -f "$tmp"
        return 1
    fi

    if ! check_format "$tmp" "$name"; then
        echo "FAIL $name broken-archive"
        rm -f "$tmp"
        return 1
    fi

    mv -f "$tmp" "$out"
    echo "OK $name"
    return 0
}

export -f fetch_one check_format
export OUT FORCE have_zipcheck

# ── прогон ───────────────────────────────────────────────────────────────────
# Свой цикл вместо xargs: вариант с tr и нулевым разделителем не переносим
# (GNU tr требует полный октетный escape, на укороченном ругается
# «empty string2»), и такая ошибка тихо оставляла результат пустым — скрипт
# рапортовал «всё скачано», не скачав ничего. Цикл на чистом bash работает
# одинаково и на VPS, и на macOS.
echo "==> Скачиваю..."
LOG=$(mktemp)
i=0
while IFS= read -r url || [ -n "$url" ]; do
    [ -z "$url" ] && continue
    fetch_one "$url" >> "$LOG" 2>/dev/null &
    i=$((i + 1))
    if [ $((i % JOBS)) -eq 0 ]; then wait; fi
done < "$LIST"
wait
RESULTS=$(cat "$LOG")

OKN=$(grep -cE '^(OK|CACHED) ' "$LOG")
FAILN=$(grep -cE '^FAIL ' "$LOG")
grep -E '^FAIL ' "$LOG" | head -20 || true
echo "==> Файлов готово: $OKN из $TOTAL"
echo "==> С ошибками:    $FAILN"
if [ $((OKN + FAILN)) -ne "$TOTAL" ]; then
    echo "⚠️  ВНИМАНИЕ: $((OKN + FAILN)) вердиктов на $TOTAL заданий — часть файлов"
    echo "    не отдала ни OK, ни FAIL. Проверь лог: $LOG"
fi

# ── сводка ───────────────────────────────────────────────────────────────────
echo ""
echo "==> sha256 всех файлов, лежащих в $OUT:"
HASHTOOL=$(command -v sha256sum || command -v shasum || echo "")
if [ -z "$HASHTOOL" ]; then
    echo "❌ Нет ни sha256sum, ни shasum — манифест не собрать."
    rm -f "$LIST"; exit 1
fi
( cd "$OUT" && "$HASHTOOL" ./* 2>/dev/null ) | sed "s|\./||" | sort -k2 > "$OUT.sha256"
wc -l < "$OUT.sha256" | xargs echo "    строк в манифесте:"
echo "    манифест: $OUT.sha256"
du -sh "$OUT" | awk '{print "    объём: "$1}'

if [ "$FAILN" -ne 0 ] || [ "$OKN" -ne "$TOTAL" ]; then
    echo ""
    echo "❌ Есть проблемные файлы — перезапусти скрипт, он докачает только их:"
    grep -E '^FAIL ' "$LOG" | head -20
else
    echo ""
    echo "✅ Все файлы скачаны, размеры и целостность в порядке."
fi
echo "Забери манифест:  scp root@<vps>:$OUT.sha256 ."
rm -f "$LIST" "$LOG"
