# NOKAHI AgroRoute — imagem da API + web (serve agroroute.despaxai.com)
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FORWARDED_ALLOW_IPS=* \
    AGROROUTE_TENANTS=/app/seed/tenants.json

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agroroute ./agroroute
COPY web ./web
# seed dos tenants fica FORA do volume de dados (que guarda só o banco)
COPY data/tenants.json ./seed/tenants.json

EXPOSE 8000

# Escuta na porta injetada pela plataforma ($PORT, ex.: Railway/Render); 8000 no
# local. Forma SHELL para que ${PORT} seja expandido em tempo de execução.
# 1 worker + SQLite é correto e simples; para múltiplos workers use DATABASE_URL
# apontando para PostgreSQL (ver DEPLOY.md). UvicornWorker honra proxy headers.
CMD gunicorn agroroute.api:app \
    -k uvicorn.workers.UvicornWorker \
    -b 0.0.0.0:${PORT:-8000} --workers 1 --timeout 120 \
    --forwarded-allow-ips "*" --access-logfile -
