FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Docker-CLI mit buildx. Gebraucht wird ausschliesslich der Bau von Golden
# Images: Auf einem Host mit containerd-Image-Store legt der klassische
# Build-Endpunkt (den das Python-SDK nutzt) bei Multi-Plattform-Basisimages
# kein benutzbares Image im Store ab — es entsteht und verschwindet wieder.
# BuildKit mit "--load" ist dafuer der unterstuetzte Weg.
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates curl gnupg \
 && install -m 0755 -d /etc/apt/keyrings \
 && curl -fsSL https://download.docker.com/linux/debian/gpg \
      -o /etc/apt/keyrings/docker.asc \
 && chmod a+r /etc/apt/keyrings/docker.asc \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
      https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
      > /etc/apt/sources.list.d/docker.list \
 && apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      docker-ce-cli docker-buildx-plugin \
 && apt-get purge -y gnupg && apt-get autoremove -y \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

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
