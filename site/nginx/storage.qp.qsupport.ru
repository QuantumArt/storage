# Хостовый server block для алиаса storage.qp.qsupport.ru.
#
# Зачем: внутри 66 PDF нашего релиза 80 ссылок ведут на storage.qp.qsupport.ru —
# домен, у которого больше нет DNS-записи. Читатель PDF кликает по ссылке и
# получает ошибку. Этот vhost отвечает на те же пути 302-редиректом на новые
# адреса, и ссылки внутри PDF продолжают работать.
#
# DNS править не нужно: CNAME storage.qp.qsupport.ru → storage.quantumart.ru
# уже стоит (серое облако, proxied=false) и ведёт на этот же VPS (217.198.6.66).
# Ломается только TLS и маршрутизация на origin — их чинит этот vhost.
#
# Установка на VPS timeweb (шаги выполняет владелец):
#
#   1) Сертификат. Домен второго уровня: Universal SSL Cloudflare его не
#      покрывает, а запись у нас не проксируется — поэтому только DNS-01.
#      Токен зоны qsupport.ru лежит на сервере в /root/nuget/.secrets/cloudflare.ini
#      (им же выпущен nuget.qsupport.ru):
#        sudo certbot certonly --dns-cloudflare \
#          --dns-cloudflare-credentials /root/nuget/.secrets/cloudflare.ini \
#          -d storage.qp.qsupport.ru --cert-name storage.qp.qsupport.ru
#
#   2) Файлы. Блок map лежит отдельно и подключается include'ом: include
#      стоит на уровне http{}, поэтому map попадает именно туда.
#        sudo cp nginx/storage.qp.qsupport.ru     /etc/nginx/sites-available/
#        sudo cp nginx/storage.qp.qsupport.ru.map /etc/nginx/sites-available/
#        sudo ln -s /etc/nginx/sites-available/storage.qp.qsupport.ru \
#                 /etc/nginx/sites-enabled/storage.qp.qsupport.ru
#
#   3) Проверка и перезапуск:
#        sudo nginx -t && sudo systemctl reload nginx
#
#   Откат: убрать симлинк из sites-enabled, затем nginx -t && systemctl reload nginx.
#
# Карта редиректов (360 правил) собирается tools/build_redirect_map.py из
# manifest/redirect-paths.txt. Файл .map — результат сборки, руками не правится.

include /etc/nginx/sites-available/storage.qp.qsupport.ru.map;

server {
    listen 80;
    listen [::]:80;
    server_name storage.qp.qsupport.ru;

    # ACME-челлендж certbot.
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    # Старый стиль http2, а не директива `http2 on;`: такая есть только
    # начиная с nginx 1.25, на сервере 1.24. Формат тот же, что у соседних
    # доменов (izida, kuma, nuget.qsupport.ru).
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name storage.qp.qsupport.ru;

    ssl_certificate     /etc/letsencrypt/live/storage.qp.qsupport.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/storage.qp.qsupport.ru/privkey.pem;

    # Свои файлы журнала: на сервере один nginx обслуживает много доменов,
    # и общий access.log невозможно читать по одному сайту.
    access_log /var/log/nginx/storage.qp.qsupport.ru.access.log;
    error_log  /var/log/nginx/storage.qp.qsupport.ru.error.log;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;

    location / {
        default_type text/plain;

        # Точное правило из карты. `if` с `return` — безопасное применение
        # директивы if: проверяем одну переменную и сразу выходим.
        if ($qp_redirect_target != "") {
            return 302 $qp_redirect_target;
        }

        # Запасные правила для путей, которых ещё нет в карте: новые
        # инструкции в новых PDF ссылаются на старый домен, а точные правила
        # для их файлов появятся только с очередным релизом.
        rewrite ^/qa_official_site/images/downloads/(.+)$ https://storage.quantumart.ru/downloads/$1 redirect;
        rewrite ^/qa_official_site/images/(?:presentation|documents)/(.+)$ https://storage.quantumart.ru/downloads/$1 redirect;
        rewrite ~*^/qa_official_site/images/(.+\.(?:pdf|docx|doc))$ https://storage.quantumart.ru/downloads/$1 redirect;
        rewrite ^/qa_official_site/contents/(.+)$ https://quantumart.ru/_cdn/contents/$1 redirect;
        rewrite ^/qa_official_site/images/(.+)$ https://quantumart.ru/_cdn/images/$1 redirect;

        # Старый хост на каталоге отдавал 404 — повторяем.
        return 404 "not found\n";
    }
}
