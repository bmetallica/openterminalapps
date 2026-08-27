FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY otaagent ./otaagent

# Laeuft als root, weil der Docker-Socket es verlangt. Genau deshalb ist
# dieser Dienst so klein wie moeglich gehalten und nur aus dem internen
# Netz erreichbar — die API, die Nutzereingaben verarbeitet, fasst Docker nie an.
EXPOSE 8100

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8100/healthz',timeout=3).status==200 else 1)"

CMD ["uvicorn", "otaagent.main:app", "--host", "0.0.0.0", "--port", "8100"]
