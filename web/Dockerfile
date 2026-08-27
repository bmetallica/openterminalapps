# Mehrstufiger Build: Auf dem Host wird kein Node und kein npm gebraucht.
# Alles läuft im Container — der Host braucht nur Docker.

# ---------- Stufe 1: bauen ----------
FROM node:22-alpine AS build

WORKDIR /app

# Erst die Manifeste, damit die Abhängigkeitsschicht im Cache bleibt,
# solange sich nur der Quellcode ändert.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src

RUN npx tsc -b && npx vite build

# ---------- Stufe 2: ausliefern ----------
FROM nginx:alpine AS runtime

COPY --from=build /app/dist /usr/share/nginx/html
COPY --from=build /app/dist/index.html /usr/share/nginx/html/index.html

# nginx-Konfiguration kommt aus dem Compose-Mount, damit sie ohne
# Neubau des Images anpassbar bleibt.

# 127.0.0.1 statt localhost: localhost löst im Container zuerst auf ::1 auf,
# nginx lauscht aber nur auf IPv4.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1/healthz || exit 1

EXPOSE 80
