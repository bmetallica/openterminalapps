# Paketquellen (Handbuch Kapitel 26): aptly und ein kleiner Steuerdienst.
#
# aptly macht die eigentliche Arbeit — Spiegel, eigenes Repository,
# Snapshots, Signieren. Der Steuerdienst daneben ist das, womit die OTA-API
# spricht: Er fuehrt aptly-Befehle aus, haelt sie hintereinander (aptly
# vertraegt keine zwei gleichzeitig) und schreibt mit, was passiert. Alles
# aus Debians eigenen Paketen, nichts aus pip — der Dienst soll sich auch auf
# einer Anlage bauen lassen, deren einziger Weg nach draussen ein Debian-Spiegel
# ist.
FROM debian:13

ARG DEBIAN_FRONTEND=noninteractive
# `python3-python-multipart`, nicht `python3-multipart`: Das zweite ist ein
# anderes Paket gleichen Zwecks, und FastAPI lehnt Uploads damit ab — der
# Dienst startete gar nicht erst.
RUN apt-get update && apt-get install -y --no-install-recommends \
      aptly gnupg debian-archive-keyring ca-certificates curl dpkg \
      python3 python3-venv python3-fastapi python3-uvicorn python3-python-multipart \
 && apt-get clean && rm -rf /var/lib/apt/lists/* \
 && aptly version

WORKDIR /app
COPY otarepo ./otarepo
ENV PYTHONUNBUFFERED=1
EXPOSE 8200
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8200/healthz || exit 1
CMD ["python3", "-m", "uvicorn", "otarepo.main:app", "--host", "0.0.0.0", "--port", "8200"]
