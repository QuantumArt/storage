# Хранилище файлов QP: собирает индекс из манифеста и раздаёт 302-редиректы.
# Сами байты в образ не попадают и на сервере не хранятся — они лежат в
# GitHub Release (см. docs/DEPLOY-SPEC.md, раздел «Где лежат байты»).

FROM python:3.12-alpine AS builder
WORKDIR /build
COPY manifest/manifest.json ./manifest.json
COPY tools/build_index.py ./build_index.py
RUN python3 build_index.py

FROM nginx:1.27-alpine AS runtime
COPY --from=builder /build/index.html /usr/share/nginx/html/index.html
COPY site/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /build/assets.map /etc/nginx/conf.d/assets.conf
EXPOSE 80
# 127.0.0.1, а не localhost: внутри контейнера localhost резолвится
# в ::1, а nginx слушает только IPv4 — healthcheck на localhost стабильно
# падал и ронял контейнер в unhealthy при живом сайте.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget --spider -q http://127.0.0.1/healthz || exit 1
