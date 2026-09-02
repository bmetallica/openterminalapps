# OpenTerminalApps — Betriebsbefehle
#
# Alles läuft in Containern. Auf dem Host wird nur Docker gebraucht,
# kein Node, kein Python.

SHELL := /bin/bash
COMPOSE := docker compose -f deploy/docker-compose.yml --env-file deploy/.env

.PHONY: help
help:
	@echo "OpenTerminalApps"
	@echo
	@echo "  make setup     Zertifikat erzeugen und .env anlegen (einmalig)"
	@echo "  make up        Stack bauen und starten"
	@echo "  make down      Stack stoppen (Sessions laufen weiter)"
	@echo "  make restart   Dienste neu starten, Sessions bleiben verbunden"
	@echo "  make identity  Keycloak-Realm einrichten oder ergänzen"
	@echo "  make logs      Logs aller Dienste mitlesen"
	@echo "  make ps        Zustand aller Dienste"
	@echo "  make admin     Ersten Administrator anlegen (NAME=... setzen)"
	@echo "  make test      Autorisierungs- und Oberflächentests"
	@echo "  make backup    Datenbank und Profile von Hand sichern"
	@echo "  make cert      Serverzertifikat erneuern (CA bleibt)"
	@echo

.PHONY: setup
setup:
	@./scripts/setup-env.sh
	@./scripts/traefik-config.sh
	@./scripts/make-cert.sh
	@mkdir -p /srv/ota/profiles /srv/ota/skeletons /srv/ota/shared \
	          /srv/ota/backups /srv/ota/runtime /srv/ota/userfiles \
	          /srv/ota/groupfiles
	@echo
	@echo "Bereit. Weiter mit:  make up"

.PHONY: up
up:
	@# Traefiks statische Konfiguration haengt an einem Wert aus deploy/.env
	@# und wird deshalb vor jedem Start neu erzeugt. Siehe die Vorlage daneben.
	@./scripts/traefik-config.sh
	$(COMPOSE) up -d --build
	@# Der Realm wird nach dem Hochfahren eingerichtet, nicht bei `make setup`:
	@# Dort läuft Keycloak noch nicht. Idempotent — was da ist, bleibt.
	@#
	@# Und **mit Warten**. Keycloak braucht beim ersten Start rund eine halbe
	@# Minute, bis es antwortet; ohne diese Schleife scheiterte die Einrichtung
	@# beim ersten `make up` verlässlich, und der Realm entstand erst, wenn
	@# jemand die Zeile mit `make identity` von Hand nachholte. Ein
	@# Schnellstart, dessen zweiter Schritt stillschweigend nichts tut, ist
	@# keiner.
	@printf '  Warte auf Keycloak'
	@for i in $$(seq 1 60); do \
	  if [ "$$(docker inspect -f '{{.State.Health.Status}}' ota-keycloak 2>/dev/null)" = "healthy" ]; then \
	    printf ' — bereit\n'; break; \
	  fi; \
	  printf '.'; sleep 3; \
	  if [ $$i = 60 ]; then printf '\n  (kommt nicht hoch — später:  make identity)\n'; fi; \
	done
	@./scripts/keycloak-init.sh || \
	  echo "  (Realm nicht eingerichtet — später:  make identity)"
	@echo
	@$(COMPOSE) ps --format '  {{.Name}}\t{{.Status}}'

.PHONY: down
down:
	$(COMPOSE) down

.PHONY: identity
identity:
	@./scripts/keycloak-init.sh

.PHONY: restart
restart:
	$(COMPOSE) restart api web
	@echo "Laufende Sessions sind davon nicht betroffen."

.PHONY: logs
logs:
	$(COMPOSE) logs -f --tail=80

.PHONY: ps
ps:
	@$(COMPOSE) ps --format '  {{.Name}}\t{{.Status}}'

.PHONY: admin
admin:
	@test -n "$(NAME)" || { echo "Aufruf: make admin NAME=<benutzername>"; exit 1; }
	$(COMPOSE) exec -T api python -m ota.seed --admin "$(NAME)"

.PHONY: cert
cert:
	@./scripts/make-cert.sh
	@echo "Traefik lädt das Zertifikat von selbst neu — kein Neustart nötig."

.PHONY: test
# Die Zugangsdaten der Pruefung stehen in deploy/.env, nicht im Repository.
# `export` weil die Skripte und der Browsertest sie als Umgebungsvariable
# erwarten; `-include` damit ein fehlendes .env eine verstaendliche Meldung
# ergibt statt eines Make-Fehlers.
-include deploy/.env
export OTA_TEST_ADMIN_PW

test:
	@./scripts/test-authz.sh
	@echo
	@./scripts/test-clipboard-bridge.sh || \
	  echo "  (übersprungen — dafür muss ein Arbeitsplatz mit zwei Apps laufen)"
	@echo
	@cd tests && npm install --silent --no-audit --no-fund && node e2e.mjs
	@echo
	@# Startet ein Wegwerf-Verzeichnis, richtet die Anbindung ein und nimmt
	@# beides danach wieder zurück. Läuft vor der Sicherung, damit die
	@# angelegten Verzeichniskonten nicht in einem Sicherungsstand landen.
	@./scripts/test-ldap.sh
	@echo
	@# Zuletzt, weil dieser Test Sessions beendet, um die Wiederherstellung
	@# überhaupt prüfen zu können.
	@./scripts/test-backup.sh

.PHONY: sbom
# Stückliste je Image — nötig, sobald ein Image das Haus verlässt.
sbom:
	@./scripts/sbom.sh

.PHONY: backup
backup:
	@mkdir -p backups
	@$(COMPOSE) exec -T db pg_dump -U $${POSTGRES_USER:-ota} $${POSTGRES_DB:-ota} \
	  | zstd -q -o backups/db-$$(date +%F-%H%M).sql.zst
	@# Keycloak liegt in einer eigenen Datenbank. Ohne sie käme OTA aus einer
	@# Wiederherstellung mit Nutzern zurück, die auf Identitäten ohne
	@# Gegenstück zeigen — Sessions, Profile und Kontingente hängen an
	@# `external_id`. Fehlt die Datenbank (fremdes Keycloak), wird es
	@# übersprungen; dann sichert sie jemand anders.
	@$(COMPOSE) exec -T db psql -U $${POSTGRES_USER:-ota} -tAc \
	  "SELECT 1 FROM pg_database WHERE datname='keycloak'" 2>/dev/null | grep -q 1 \
	  && $(COMPOSE) exec -T db pg_dump -U $${POSTGRES_USER:-ota} keycloak \
	     | zstd -q -o backups/keycloak-$$(date +%F-%H%M).sql.zst \
	  || echo "  (keine eigene Keycloak-Datenbank — übersprungen)"
	@tar --zstd -cf backups/profiles-$$(date +%F-%H%M).tar.zst \
	  --exclude='.cache' --exclude='core.*' --exclude='*.sock' \
	  --exclude='*/Cache*' -C / srv/ota/profiles 2>/dev/null || true
	@# Alles, was jemand von Hand angelegt hat und was sich nicht aus Code
	@# oder Image wiederherstellen laesst. Bis zum 2026-08-28 fehlten diese
	@# drei: Gesichert wurden nur die Zuhause der Nutzer, und ein
	@# zurueckgespielter Stand kam ohne Skeleton-Profile, ohne die gemeinsame
	@# Ablage und ohne die eigenen Ablagen zurueck.
	@tar --zstd -cf backups/inhalte-$$(date +%F-%H%M).tar.zst \
	  --exclude='*.sock' -C / \
	  $$(cd / && ls -d srv/ota/skeletons srv/ota/shared srv/ota/userfiles \
	     srv/ota/groupfiles \
	     2>/dev/null) 2>/dev/null || true
	@ls -la backups/ | tail -5
	@echo "Ein Backup, dessen Wiederherstellung nie getestet wurde, ist kein Backup."
