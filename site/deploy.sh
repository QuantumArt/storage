#!/bin/bash
# ─── storage.quantumart.ru — production deploy ───────────────────────────────
# Тянет изменения из git, пересобирает образ, перезапускает контейнер, прогоняет
# smoke-test (loopback + домен). Структура — та же, что у downloads на этом VPS.
#
# Особенность этого проекта: в образе нет байтов. Образ собирает только
# индекс страницы из manifest/manifest.json, а файлы раздаются 302-редиректом
# на ассеты GitHub Release. Поэтому деплой не занимает 1.37 ГБ на диске.
#
# Запуск: ./deploy.sh [--force]
#   --force    Полная пересборка без кэша (пересоздаёт контейнер)
#   (по умолчанию) Инкрементальный деплой (пересборка образа, рестарт контейнера)

set -e

FORCE=false
for arg in "$@"; do
    case $arg in
        --force) FORCE=true; shift ;;
        *) echo "Usage: $0 [--force]"; exit 1 ;;
    esac
done

echo "🚀 Starting storage.quantumart.ru deploy..."
if [ "$FORCE" = true ]; then
    echo "🔥 MODE: Full clean rebuild (--force)"
else
    echo "⚡ MODE: Incremental deploy (default)"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.production.yml"
DOMAIN="storage.quantumart.ru"
PORT=3023
CONTAINER="storage-web"

print_status() { echo "✅ $1"; }
print_error()  { echo "❌ ERROR: $1"; exit 1; }

cd "$SCRIPT_DIR"
echo "📁 Project root: $SCRIPT_DIR"

if ! command -v docker >/dev/null 2>&1; then
    print_error "docker not found on PATH."
fi
print_status "Pre-flight checks passed"

echo ""
echo "📥 Step 1: Pulling latest changes..."

# Авторизация для git на этом VPS.
#
# Глобальный конфиг (/root/.gitconfig) содержит credential.helper=store, и его
# ~/.git-credentials отдаёт токен, созданный под другой репозиторий — на
# QuantumArt/storage GitHub отвечает 403. Helper'ы опрашиваются по очереди, и
# первый ответивший выигрывает, поэтому глобальный store перебивает локальный.
#
# Обходим это тремя средствами:
#   GIT_CONFIG_GLOBAL=/dev/null  — выбрасывает глобальный конфиг целиком, store
#                                  перестаёт участвовать (общий файл на общем
#                                  сервере не трогаем);
#   GIT_CONFIG_SYSTEM=/dev/null  — то же для системного конфига;
#   credential.helper через -c  — единственный оставшийся источник кредов.
# Значение токена нигде не сохраняется: читается из .credentials.env.
if [ -z "${GH_TOKEN:-}" ]; then
    CREDS_FILE="$SCRIPT_DIR/../.credentials.env"
    if [ -f "$CREDS_FILE" ]; then
        set -a; . "$CREDS_FILE"; set +a
    fi
fi

GH_HELPER='!f() { echo username=x-access-token; echo password="$GH_TOKEN"; }; f'

# Репозиторий публичный, поэтому токен для fetch не нужен: GitHub отдаёт
# публичные репозитории, не запрашивая авторизацию. Проверено — fetch проходит
# даже с подложенным чужим токеном в ~/.git-credentials, глобальный
# credential.helper=store при этом не опрашивается.
#
# Раньше шаг пропускался целиком при отсутствии токена, и это была ошибка:
# «нет токена» ≠ «нечем тянуть», из-за неё деплой собирал устаревший образ и
# требовал ручного `git merge` перед собой.
#
# Нейтрализация глобального конфига оставлена по двум причинам:
#   1. чужой токен из общего /root/.git-credentials не должен уходить на GitHub
#      ни при каких условиях; если репозиторий станет приватным, получим
#      внятную ошибку авторизации, а не 403 от чужого токена;
#   2. поведение деплоя не зависит от того, что ещё лежит в общих файлах
#      на сервере.
#
# Ни одна из попыток не роняет деплой: если сеть недоступна или рабочая копия
# изменена, собираем образ из того, что уже лежит на диске. Код меняется
# редко, а упавший деплой хуже отставшего.
PRE_PULL_HASH=$(git rev-parse HEAD 2>/dev/null || echo "unknown")

fetch_and_merge() {
    if [ -n "${GH_TOKEN:-}" ]; then
        GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null \
            git -c credential.helper="$GH_HELPER" pull --ff-only
    else
        # Публичный репозиторий: анонимный fetch. Пустой credential.helper
        # гарантирует, что чужие креды не подставятся, даже если где-то выше по
        # конфигурации снова появится store.
        GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null \
            git -c credential.helper= fetch origin main \
        && git merge --ff-only origin/main
    fi
}

if fetch_and_merge; then
    POST_PULL_HASH=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
    if [ "$PRE_PULL_HASH" = "$POST_PULL_HASH" ]; then
        echo "ℹ️  Изменений нет — продолжаю пересборку (инкрементальный деплой)"
    else
        print_status "Получено обновление: $PRE_PULL_HASH → $POST_PULL_HASH"
    fi
else
    echo "⚠️  Не удалось обновить код с GitHub — деплой продолжится из текущей"
    echo "   рабочей копии ($PRE_PULL_HASH)."
    echo "   Причины: нет сети, рабочая копия изменена, или репозиторий стал"
    echo "   приватным и нужен токен в ~/storage/.credentials.env (GH_TOKEN=…)."
    echo "   Проверить вручную:"
    echo "     GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null \\"
    echo "       git -c credential.helper= fetch origin main && git merge --ff-only origin/main"
fi

echo ""
echo "🐳 Step 2: Docker compose..."
if [ "$FORCE" = true ]; then
    echo "🔥 FORCE MODE: Stopping container, cleaning build cache..."
    docker compose -f "$COMPOSE_FILE" down --remove-orphans
    docker builder prune -af
    echo "🔥 Building from scratch..."
    docker compose -f "$COMPOSE_FILE" build --no-cache --pull
    docker compose -f "$COMPOSE_FILE" up -d --force-recreate
else
    echo "⚡ NORMAL MODE: Rebuilding image (with cache)..."
    docker compose -f "$COMPOSE_FILE" build web
    docker compose -f "$COMPOSE_FILE" up -d --force-recreate web
fi
print_status "Container started"

echo ""
echo "🏥 Step 3: Health check..."
sleep 5
WEB_CONTAINER=$(docker ps --filter "name=$CONTAINER" --format "{{.Names}}" | head -1)
if [ -z "$WEB_CONTAINER" ]; then
    print_error "Container not running. Check: docker compose -f $COMPOSE_FILE ps"
fi
echo "📋 web: $WEB_CONTAINER"
docker logs "$WEB_CONTAINER" --tail 30

echo ""
echo "🌐 Step 4: HTTP smoke test..."
echo "  Loopback (Docker direct):"
# Порт 3023, а не 3022: 3022 занят контейнером nuget-baget.
for path in / /healthz; do
    code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT$path")
    echo "    $path → HTTP $code"
    if [ "$code" != "200" ]; then
        print_error "Loopback: expected 200, got $code on $path"
    fi
done

# Файл отдаётся редиректом на ассет GitHub. Проверяем сам 302 и его цель:
# редирект без Location — это молча сломанный сервис, который отвечает кодом,
# а качать нечего.
echo "  Редирект на ассет:"
code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/downloads/QP8.zip")
loc=$(curl -s -o /dev/null -w '%{redirect_url}' "http://127.0.0.1:$PORT/downloads/QP8.zip")
echo "    /downloads/QP8.zip → HTTP $code"
echo "    Location: $loc"
if [ "$code" != "302" ]; then
    print_error "Expected 302 for a file, got $code"
fi
case "$loc" in
    *github.com/QuantumArt/storage/releases/download/v1/QP8.zip) ;;
    *) print_error "Redirect target is wrong: $loc" ;;
esac

echo "  404 (неизвестное имя и каталог без файла):"
for path in /downloads/ /downloads/definitely-missing.zip /definitely-missing; do
    code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT$path")
    echo "    $path → HTTP $code (ожидается 404)"
    if [ "$code" != "404" ]; then
        print_error "Expected 404 for $path, got $code"
    fi
done

echo "  External (через хостовый nginx, если уже настроен):"
for path in / /downloads/QP8.zip; do
    code=$(curl -sk -o /dev/null -w '%{http_code}' "https://$DOMAIN$path" || echo "000")
    echo "    $path → HTTP $code"
    if [ "$code" != "200" ] && [ "$code" != "302" ]; then
        echo "    ⚠️  ожидались 200 или 302, получили $code — нормально, если DNS/сертификат ещё не переключены"
    fi
done
print_status "HTTP smoke test done"

echo ""
echo "📦 Step 5: Сквозная проверка скачиванием..."
# Код ответа на / ничего не доказывает: страница индекса отдаётся даже когда ни
# один файл не отдаётся. Единственная проверка, которая имеет значение, —
# скачать файл по всей цепочке (наш домен → 302 → GitHub → байты) и сверить
# sha256 с манифестом. Именно так на проекте nuget не заметили сбой, при
# котором / отдавал 200, healthcheck был green, а файлы не открывались.
MANIFEST="$SCRIPT_DIR/../manifest/manifest.json"
if [ ! -f "$MANIFEST" ]; then
    echo "  ⚠️  нет $MANIFEST — сверять не с чем, пропускаю"
elif ! curl -s -o /dev/null --max-time 10 "https://$DOMAIN/" ; then
    echo "  ⚠️  $DOMAIN не отвечает — вероятно, DNS ещё не переключён. Пропускаю."
else
    # Берём самый маленький pdf: быстро, и на нём сразу видно битый файл.
    SAMPLE=$(python3 -c "
import json
d = json.load(open('$MANIFEST', encoding='utf-8'))
c = [f for f in d['files'] if f['name'].endswith('.pdf')]
c.sort(key=lambda f: f['size'])
print(f"{c[0]['name']} {c[0]['size']} {c[0]['sha256']}" if c else '')" 2>/dev/null)
    if [ -z "$SAMPLE" ]; then
        echo "  ⚠️  в манифесте нет pdf для проверки"
    else
        set -- $SAMPLE
        NAME=$1; SIZE=$2; SHA=$3
        echo "  Пробую $NAME ($(( SIZE / 1024 )) КБ)…"
        TMPF=$(mktemp)
        code=$(curl -sL --max-time 300 -o "$TMPF" -w '%{http_code}' "https://$DOMAIN/downloads/$NAME")
        got_size=$(wc -c < "$TMPF" | tr -d ' ')
        if command -v sha256sum >/dev/null 2>&1; then
            got_sha=$(sha256sum "$TMPF" | cut -d' ' -f1)
        else
            got_sha=$(shasum -a 256 "$TMPF" | cut -d' ' -f1)
        fi
        rm -f "$TMPF"
        echo "    код $code, размер $got_size (ожидался $SIZE)"
        echo "    sha256 ${got_sha:0:16}… (ожидался ${SHA:0:16}…)"
        if [ "$got_size" != "$SIZE" ] || [ "$got_sha" != "$SHA" ]; then
            print_error "Сквозная проверка не сошлась: файл не доходит до пользователя целым"
        fi
        print_status "Файл скачан по всей цепочке и совпал с манифестом"
    fi
fi


echo ""
echo "🎉 Deploy complete!"
docker compose -f "$COMPOSE_FILE" ps
echo ""
echo "💡 Полезные команды:"
echo "   Логи:           docker logs $WEB_CONTAINER -f"
echo "   Рестарт:        docker compose -f $COMPOSE_FILE restart web"
echo "   Reload nginx:   sudo systemctl reload nginx"
echo ""
echo "⚠️  Ассеты лежат в GitHub Release. Проверить, что релиз на месте:"
echo "   gh release view v1 --repo QuantumArt/storage"
