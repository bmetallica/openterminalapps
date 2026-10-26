FROM python:3.13-slim AS runtime

# Sicherheitsupdates der Basis. `OTA_PAKETSTAND` wechselt jede Woche
# (Makefile) und baut diese Schicht damit spaetestens woechentlich neu —
# sonst hielte der Build-Cache sie auf dem Stand vom ersten Bau.
ARG OTA_PAKETSTAND=
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY ota ./ota
COPY alembic.ini .
COPY migrations ./migrations

# Unprivilegiert laufen. Die API fasst Docker nie an — das macht ausschliesslich
# der Agent. Deshalb braucht sie hier auch keine besonderen Rechte.
RUN useradd -r -u 10001 -m ota && chown -R ota:ota /app
USER ota

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=3).status==200 else 1)"

CMD ["uvicorn", "ota.main:app", "--host", "0.0.0.0", "--port", "8000"]
