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
	@echo "  make logs      Logs aller Dienste mitlesen"
	@echo "  make ps        Zustand aller Dienste"
	@echo "  make admin     Ersten Administrator anlegen (NAME=... setzen)"
	@echo "  make test      Autorisierungs- und Oberflächentests"
	@echo "  make backup    Datenbank und Profile von Hand sichern"
	@echo "  make cert      Serverzertifikat erneuern (CA bleibt)"
	@echo

.PHONY: setup
setup:
	@test -f deploy/.env || { cp deploy/.env.example deploy/.env; \
	  echo "deploy/.env angelegt — bitte Geheimnisse eintragen:"; \
	  echo "  POSTGRES_PASSWORD=$$(openssl rand -base64 32)"; \
	  echo "  OTA_JWT_SECRET=$$(openssl rand -base64 48 | tr -d '\n=+/' | head -c 64)"; \
	  echo "  OTA_AGENT_TOKEN=$$(openssl rand -base64 36 | tr -d '\n=+/' | head -c 48)"; }
	@./scripts/make-cert.sh
	@mkdir -p /srv/ota/profiles

.PHONY: up
up:
	$(COMPOSE) up -d --build
	@echo
	@$(COMPOSE) ps --format '  {{.Name}}\t{{.Status}}'

.PHONY: down
down:
	$(COMPOSE) down

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
	@# Zuletzt, weil dieser Test Sessions beendet, um die Wiederherstellung
	@# überhaupt prüfen zu können.
	@./scripts/test-backup.sh

.PHONY: backup
backup:
	@mkdir -p backups
	@$(COMPOSE) exec -T db pg_dump -U $${POSTGRES_USER:-ota} $${POSTGRES_DB:-ota} \
	  | zstd -q -o backups/db-$$(date +%F-%H%M).sql.zst
	@tar --zstd -cf backups/profiles-$$(date +%F-%H%M).tar.zst \
	  --exclude='.cache' --exclude='core.*' --exclude='*.sock' \
	  --exclude='*/Cache*' -C / srv/ota/profiles 2>/dev/null || true
	@ls -la backups/ | tail -3
	@echo "Ein Backup, dessen Wiederherstellung nie getestet wurde, ist kein Backup."
