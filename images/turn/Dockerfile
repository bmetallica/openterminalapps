# coturn, wie es upstream erscheint — plus die Sicherheitsupdates seines
# Alpine, die dem fertigen Image hinterherhinken (gemessen 2026-10-26: 39
# behebbare Funde in musl, zlib, nghttp2 …). Der TURN-Dienst ist der einzige
# Teil von OTA, der aus dem Netz direkt erreichbar ist; hier lohnt die eigene
# Schicht. Zum Wochenstempel siehe api/Dockerfile.
FROM coturn/coturn:4.18-alpine3.24

USER root
ARG OTA_PAKETSTAND=
RUN apk upgrade --no-cache
USER nobody:nogroup
