#!/usr/bin/env bash
# Ein Wegwerf-Verzeichnis zum Entwickeln und Prüfen der AD/LDAP-Anbindung.
#
# **Gehört nicht zum Stack.** Es steht bewusst nicht in der
# docker-compose.yml: Ein Verzeichnisdienst, der beim `make up` mitstartet,
# wäre eine Einladung, gegen ihn zu produzieren. Wer ihn braucht, startet ihn
# von Hand und beendet ihn danach.
#
#   scripts/ldap-test-server.sh start    # starten und befüllen
#   scripts/ldap-test-server.sh stop     # spurlos entfernen
#   scripts/ldap-test-server.sh show     # was drinsteht
#
# Es hängt im selben internen Netz wie die API — sonst käme sie nicht heran.

set -uo pipefail

NAME="ota-ldap-test"
IMAGE="osixia/openldap:1.5.0"
DOMAIN="ota.test"
BASE="dc=ota,dc=test"
ADMIN_DN="cn=admin,$BASE"
ADMIN_PW="pruefadmin-2026"
NETWORK="${OTA_INTERNAL_NETWORK:-ota_internal}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

start() {
  if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
    echo "Läuft schon. Für einen frischen Stand erst 'stop'."
    return 0
  fi

  echo "Starte $NAME im Netz $NETWORK …"
  docker run -d --name "$NAME" --network "$NETWORK" \
    -e LDAP_ORGANISATION="OTA Testverzeichnis" \
    -e LDAP_DOMAIN="$DOMAIN" \
    -e LDAP_ADMIN_PASSWORD="$ADMIN_PW" \
    -e LDAP_TLS_VERIFY_CLIENT=never \
    "$IMAGE" >/dev/null || return 1

  docker cp "$ROOT/deploy/ldap-test/seed.ldif" "$NAME:/tmp/seed.ldif" >/dev/null
  docker cp "$ROOT/deploy/ldap-test/acl.ldif" "$NAME:/tmp/acl.ldif" >/dev/null

  # Einspielen, bis es wirklich drinsteht — und nicht einmal blind.
  #
  # Das Abbild startet slapd während seines eigenen Hochlaufs neu. Ein
  # `ldapadd`, das genau in diesen Moment fällt, scheitert lautlos: Die
  # Rückgabe geht nach /dev/null, und übrig bleibt ein leeres Verzeichnis,
  # das aussieht, als wäre die Basis falsch. Genau daran ist dieser Test
  # zweimal hängengeblieben.
  #
  # Geprüft wird deshalb am Ergebnis: Kann das **Dienstkonto** eine Person
  # lesen? Das deckt beide Schritte auf einmal ab — die Einträge müssen da
  # sein, und die Zugriffsregel muss greifen.
  local sichtbar=0
  for versuch in $(seq 1 30); do
    docker exec "$NAME" ldapadd -x -H ldap://localhost \
      -D "$ADMIN_DN" -w "$ADMIN_PW" -c -f /tmp/seed.ldif >/dev/null 2>&1
    docker exec "$NAME" ldapmodify -Y EXTERNAL -H ldapi:/// -f /tmp/acl.ldif \
      >/dev/null 2>&1

    sichtbar=$(docker exec "$NAME" ldapsearch -x -LLL -H ldap://localhost \
                 -b "$BASE" -D "cn=ota-dienst,$BASE" -w dienst-geheim-2026 \
                 "(objectClass=inetOrgPerson)" dn 2>/dev/null | grep -c "^dn:")
    [ "${sichtbar:-0}" -ge 4 ] && break
    sleep 2
  done

  if [ "${sichtbar:-0}" -lt 4 ]; then
    echo "Das Verzeichnis liess sich nicht befüllen (sichtbar: ${sichtbar:-0})." >&2
    echo "Zum Nachsehen:  docker logs $NAME" >&2
    return 1
  fi

  echo "Bereit: $sichtbar Einträge unter $BASE, vom Dienstkonto lesbar"
  echo
  echo "  Adresse aus der API heraus : ldap://$NAME:389"
  echo "  Dienstkonto               : cn=ota-dienst,$BASE / dienst-geheim-2026"
  echo "  Basis                     : $BASE"
  echo "  Konten                    : lena.brandt, piet.holm, ruth.mayer"
  echo "  Absichtlich namensgleich  : bmetallica (darf nichts übernehmen)"
}

stop() {
  docker rm -f "$NAME" >/dev/null 2>&1 && echo "$NAME entfernt." \
    || echo "$NAME lief nicht."
}

show() {
  docker exec "$NAME" ldapsearch -x -LLL -H ldap://localhost -b "$BASE" \
    -D "$ADMIN_DN" -w "$ADMIN_PW" "(|(objectClass=inetOrgPerson)(objectClass=groupOfNames))" \
    dn cn uid mail member 2>/dev/null
}

case "${1:-start}" in
  start) start ;;
  stop)  stop ;;
  show)  show ;;
  *)     echo "start | stop | show"; exit 1 ;;
esac
