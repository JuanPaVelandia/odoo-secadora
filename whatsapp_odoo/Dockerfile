# Bot de consultas Odoo por WhatsApp.
# Desplegable en Easypanel como servicio con puerto 8080 expuesto.
FROM python:3.12-slim

WORKDIR /app

# Instalar dependencias primero: esta capa se reaprovecha entre despliegues
# mientras no cambien las versiones.
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    "anthropic>=0.40" \
    "fastapi>=0.110" \
    "uvicorn[standard]>=0.27" \
    "httpx>=0.27" \
    "psycopg[binary]>=3.1"

COPY pg_client.py evolution.py meta_wa.py adjuntos.py historial.py agente.py servidor.py ./

# Sin root: si algo se cuela, que no tenga la máquina entera.
RUN useradd --create-home --shell /usr/sbin/nologin bot
USER bot

# El filestore de Odoo se monta como volumen de SOLO LECTURA al arrancar:
#   -v /opt/odoo19/.local/share/Odoo/filestore/secadora_2:/odoo-filestore:ro
ENV ODOO_FILESTORE=/odoo-filestore

EXPOSE 8080

HEALTHCHECK --interval=60s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import httpx,sys; sys.exit(0 if httpx.get('http://127.0.0.1:8080/salud', timeout=8).status_code==200 else 1)"

CMD ["uvicorn", "servidor:app", "--host", "0.0.0.0", "--port", "8080"]
