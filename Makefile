.PHONY: help pull check load-offline up down maj \
        start-lab1a start-lab1b start-lab2a start-lab2b start-lab3 start-lab4a start-lab4b \
        check-lab1b check-lab2b check-lab3 check-lab4b rca

help:
	@echo "Commandes disponibles (Orion Lab) :"
	@echo "  make pull                                  Télécharge les images Docker et les modèles Ollama"
	@echo "  make check [LOW_MEM=1]                     Vérifie le poste, étalonne Ollama/RCA et génère .env"
	@echo "  make load-offline OFFLINE_DIR=...          Charge les images et modèles depuis une clé USB"
	@echo "  make up                                    Démarre la stack Orion"
	@echo "  make down                                  Arrête la stack Orion"
	@echo "  make maj                                   Récupère la dernière version du cours et ses images"
	@echo "  make start-lab1a .. make start-lab4b       Démarre un lab depuis son état de référence"
	@echo "  make check-lab1b PIN=... ETU=...           Produit le jeton chiffré du checkpoint (ETU = votre numéro étudiant)"
	@echo "  make rca                                   Exécute l'outil de RCA du lab 4b"

pull:
	@sh scripts/pull.sh

check:
	@python3 scripts/check.py

load-offline:
	@sh scripts/load-offline.sh "$(OFFLINE_DIR)"

up:
	@sh scripts/up.sh
	@sh scripts/maj.sh --verifier

down:
	@sh scripts/down.sh

maj:
	@sh scripts/maj.sh

start-lab1a start-lab1b start-lab2a start-lab2b start-lab3 start-lab4a start-lab4b:
	@sh scripts/start-lab.sh "$(subst start-,,$@)"
	@sh scripts/maj.sh --verifier

check-lab1b check-lab2b check-lab3 check-lab4b:
	@if [ -z "$(PIN)" ] || [ -z "$(ETU)" ]; then \
		echo "Erreur : précisez PIN=... et ETU=... (ex. make $@ PIN=ABCD ETU=20260001)" >&2; \
		exit 1; \
	fi
	@docker compose --env-file .env -f compose/docker-compose.yml exec -T tools orion-tools check "$(subst check-,,$@)" --pin "$(PIN)" --etu "$(ETU)" && \
		echo "" && \
		echo "Ajoutez ce jeton sur sa propre ligne à la fin de jetons/ckn.txt, puis poussez-le (README, § 6) :" && \
		echo "  git add jetons/ckn.txt && git commit -m \"Validation $(subst check-,,$@)\" && git push"

rca:
	@if [ -f .env ]; then set -a; . ./.env; set +a; fi; \
	if [ "$${LOW_MEM:-0}" = "1" ]; then \
		echo "Erreur : make rca ne peut pas s'exécuter en mode LOW_MEM=1 (sans Ollama). Exécutez le lab 4b sur la machine de 16 Go du trinôme." >&2; \
		exit 1; \
	fi; \
	mkdir -p rca exports/rca; \
	chmod -R 0777 exports rca 2>/dev/null || true; \
	COMPOSE_ARGS="-f compose/docker-compose.yml"; \
	if [ "$${ORION_USE_LINUX_COMPOSE:-0}" = "1" ]; then \
		COMPOSE_ARGS="$$COMPOSE_ARGS -f compose/linux.yml"; \
	fi; \
	docker compose --env-file .env $$COMPOSE_ARGS --profile rca run --rm rca
