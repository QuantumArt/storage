# Хостовый server block для storage.quantumart.ru.
#
# Ставится на VPS timeweb:
# Порт контейнера 3023 (3022 занят nuget-baget). Номер порта должен
# совпадать в этом файле, в docker-compose.production.yml и в deploy.sh.
#
#   sudo cp nginx/storage.quantumart.ru /etc/nginx/sites-available/storage.quantumart.ru
#   sudo ln -s /etc/nginx/sites-available/storage.quantumart.ru \
#            /etc/nginx/sites-enabled/storage.quantumart.ru
#   sudo nginx -t && sudo systemctl reload nginx
#
# Домен не входит в SAN общего сертификата ts.sqlhub.pro (*.sqlhub.pro),
# поэтому сертификат выпускается отдельный, ДО переключения DNS:
#   sudo certbot certonly --dns-cloudflare \
#     --dns-cloudflare-credentials ~/storage/.secrets/cloudflare.ini \
#     -d storage.quantumart.ru --cert-name storage.quantumart.ru

server {
    listen 80;
    listen [::]:80;
    server_name storage.quantumart.ru;

    # ACME-челлендж certbot.
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name storage.quantumart.ru;

    ssl_certificate     /etc/letsencrypt/live/storage.quantumart.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/storage.quantumart.ru/privkey.pem;

    # Файлы крупные (максимум 184 МБ), поэтому клиентский таймаут по умолчанию
    # 60 с на медленных каналах даёт обрыв. Снимаем кеш на уровне nginx:
    # редирект на GitHub всё равно меняет целевой хост.
    proxy_buffering off;
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;

    # Двоичные файлы. Пользователь видит наш домен, дальше — 302 на GitHub.
    location /downloads/ {
        proxy_pass http://127.0.0.1:3023;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        proxy_pass http://127.0.0.1:3023;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
