#!/bin/sh
# OTA: Geheimnisse beim Push erkennen (Handbuch Kapitel 27).
#
# ERZEUGT von OTA (agent/otaagent/git_dienst.py) und bei jedem Abgleich
# erneuert. Läuft in Forgejo als Pre-Receive-Hook jedes Repositorys, über
# hooks/pre-receive.d/ota-geheimnisse.
#
# Geprüft werden nur die **neuen** Commits eines Pushes, und davon nur die
# hinzugefügten Zeilen und die Dateinamen. Gezählt wird je Push: die Aktion
# und je Typ die Zahl der Treffer. **Kein** Geheimnis, kein Dateiname, kein
# Repository und keine Person landen im Spool. Den Fundort sieht nur, wer
# pusht, in der Ausgabe von git (remote: …).
#
# Ein eigener Fehler hält nie einen Push auf: Nur ein Fund im Modus
# „sperren“ gibt einen Exit-Code ungleich 0 zurück.

D=/data/ota/geheimnisse
[ -r "$D/konfig" ] || exit 0
AN=0; MODUS=warnen; UEBERGEHEN=1
. "$D/konfig"
[ "$AN" = 1 ] || exit 0

GRENZE_COMMITS=1000
GRENZE_BYTES=30000000

uebergehen=0
i=0
while [ "$i" -lt "${GIT_PUSH_OPTION_COUNT:-0}" ]; do
  eval "o=\${GIT_PUSH_OPTION_$i}"
  [ "$o" = "ota.geheimnis=falscher-alarm" ] && uebergehen=1
  i=$((i + 1))
done

tmp=$(mktemp -d 2>/dev/null) || exit 0
trap 'rm -rf "$tmp"' EXIT
: > "$tmp/diff"
gekuerzt=0
while read -r alt neu ref; do
  case "$neu" in *[!0]*) ;; *) continue ;; esac   # Zweig gelöscht
  n=$(git rev-list --count "$neu" --not --all 2>/dev/null || echo 0)
  [ "${n:-0}" -gt "$GRENZE_COMMITS" ] && gekuerzt=1
  timeout 30 git log -p --no-color --no-ext-diff --no-textconv -U0 \
      --max-count="$GRENZE_COMMITS" --format='commit %H' "$neu" --not --all \
      2>/dev/null >> "$tmp/diff"
  [ $? -eq 124 ] && gekuerzt=1
done
if [ "$(wc -c < "$tmp/diff")" -gt "$GRENZE_BYTES" ]; then
  head -c "$GRENZE_BYTES" "$tmp/diff" > "$tmp/diff.k" && mv "$tmp/diff.k" "$tmp/diff"
  gekuerzt=1
fi

# Funde: Typ<TAB>Datei<TAB>Commit, je Typ und Datei einmal.
awk '
function platzhalter(s) {
  return s ~ /example|beispiel|changeme|change_me|placeholder|your[_-]|<[a-z0-9_ -]+>|xxxx|\*\*\*|dummy|redacted|\$\{|\{\{|%\(/
}
function fund(t) {
  k = t SUBSEP f
  if (!(k in gesehen)) { gesehen[k] = 1; printf "%s\t%s\t%s\n", t, f, c }
}
function datei(p,   b) {
  f = p; b = p; sub(/^.*\//, "", b); b = tolower(b)
  if (b ~ /^\.env(\.[a-z0-9_-]+)?$/ && b !~ /\.(example|sample|template|dist|beispiel|vorlage)$/) fund("env-datei")
  if (b ~ /^id_(rsa|dsa|ecdsa|ed25519)$/ || b ~ /\.(key|p12|pfx|jks|keystore|kdbx|ppk)$/ \
      || b == ".git-credentials" || b == ".netrc" || b == ".pgpass") fund("schluesseldatei")
}
/^commit [0-9a-f]+$/ { c = substr($2, 1, 10); next }
/^\+\+\+ b\// { datei(substr($0, 7)); next }
/^\+\+\+ / { next }
/^Binary files .* and b\/.* differ$/ { s = $0; sub(/^Binary files .* and b\//, "", s); sub(/ differ$/, "", s); datei(s); next }
/^\+/ {
  z = substr($0, 2)
  if (z ~ /-----BEGIN ([A-Z0-9]+ )*PRIVATE KEY( BLOCK)?-----/) fund("privater-schluessel")
  if (z ~ /(^|[^A-Z0-9])(AKIA|ASIA)[A-Z0-9]{16}([^A-Z0-9]|$)/ || z ~ /AIza[0-9A-Za-z_-]{35}/) fund("cloud-schluessel")
  if (z ~ /gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{60,}|glpat-[A-Za-z0-9_-]{20}/) fund("git-token")
  if (z ~ /sk-(ant-|proj-)?[A-Za-z0-9_-]{32,}/) fund("ki-schluessel")
  if (z ~ /xox[abposr]-[A-Za-z0-9-]{10,}/) fund("chat-token")
  if (z ~ /eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/) fund("jwt")
  l = tolower(z)
  if (!platzhalter(l)) {
    if (l ~ /(password|passwd|passwort|kennwort|secret|api[_-]?key|access[_-]?key|auth[_-]?token|client[_-]?secret)["'"'"']?[[:space:]]*[:=][[:space:]]*["'"'"'][^"'"'"'[:space:]$<{%]{8,}["'"'"']/) fund("passwort-im-code")
    if (l ~ /[a-z][a-z0-9+.-]*:\/\/[^\/[:space:]:@"'"'"']+:[^\/[:space:]:@"'"'"'$]{3,}@[a-z0-9]/) fund("zugang-in-adresse")
  }
}
' "$tmp/diff" > "$tmp/funde" 2>/dev/null || : > "$tmp/funde"

if [ -s "$tmp/funde" ]; then
  case "$MODUS" in
    sperren) if [ "$uebergehen" = 1 ] && [ "$UEBERGEHEN" = 1 ]; then aktion=uebergangen; else aktion=gesperrt; fi ;;
    warnen) aktion=gewarnt ;;
    *) aktion=gezaehlt ;;
  esac
else
  aktion=geprueft
fi

# In den Spool: nur Zahlen. Atomar, damit der Agent nie eine halbe Zeile liest.
mkdir -p "$D/spool" 2>/dev/null
awk -v zeit="$(date +%s)" -v aktion="$aktion" -v gekuerzt="$gekuerzt" -F '\t' '
  { n[$1]++ }
  END {
    printf "{\"art\":\"git-geheimnis\",\"zeit\":%d,\"aktion\":\"%s\",\"gekuerzt\":%d,\"typen\":{", zeit, aktion, gekuerzt
    s = ""; for (t in n) { printf "%s\"%s\":%d", s, t, n[t]; s = "," }
    print "}}"
  }' "$tmp/funde" > "$D/spool/.$$.tmp" 2>/dev/null \
  && mv "$D/spool/.$$.tmp" "$D/spool/$(date +%s)-$$.jsonl" 2>/dev/null

[ "$aktion" = geprueft ] || [ "$aktion" = gezaehlt ] && exit 0

name() {
  case "$1" in
    privater-schluessel) echo "privater Schlüssel" ;;
    cloud-schluessel) echo "Cloud-Zugangsschlüssel" ;;
    git-token) echo "Git-Token" ;;
    ki-schluessel) echo "API-Schlüssel eines KI-Anbieters" ;;
    chat-token) echo "Chat-Token" ;;
    jwt) echo "JSON Web Token" ;;
    passwort-im-code) echo "Passwort im Code" ;;
    zugang-in-adresse) echo "Zugangsdaten in einer Adresse" ;;
    env-datei) echo ".env-Datei" ;;
    schluesseldatei) echo "Schlüsseldatei" ;;
    *) echo "$1" ;;
  esac
}

{
  echo ""
  if [ "$aktion" = gesperrt ]; then
    echo "OTA: Push abgewiesen — er enthält wahrscheinlich ein Geheimnis."
  elif [ "$aktion" = uebergangen ]; then
    echo "OTA: Mögliches Geheimnis, als Fehlalarm übergangen (ota.geheimnis=falscher-alarm)."
  else
    echo "OTA: Achtung — dieser Push enthält wahrscheinlich ein Geheimnis."
  fi
  echo ""
  head -n 20 "$tmp/funde" | while IFS="$(printf '\t')" read -r typ datei commit; do
    echo "  $(name "$typ"): $datei (Commit $commit)"
  done
  [ "$(wc -l < "$tmp/funde")" -gt 20 ] && echo "  … und weitere."
  echo ""
  echo "Ein Geheimnis in der Historie bleibt dort, auch wenn ein späterer Commit es"
  echo "löscht. Deshalb: den Schlüssel oder das Passwort ändern lassen (ungültig machen),"
  echo "dann den Commit umschreiben (git commit --amend oder git rebase -i) und neu pushen."
  echo "Geheimnisse gehören in eine Umgebungsvariable oder eine Datei, die in .gitignore steht."
  if [ "$aktion" = gesperrt ] && [ "$UEBERGEHEN" = 1 ]; then
    echo ""
    echo "Ist es ein Fehlalarm (Beispielwert, Testschlüssel), so pushen:"
    echo "  git push -o ota.geheimnis=falscher-alarm"
  fi
  echo "Handbuch Kapitel 27, Abschnitt „Geheimnisse beim Push“."
  echo ""
} >&2

[ "$aktion" = gesperrt ] && exit 1
exit 0
