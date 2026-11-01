#!/usr/bin/env sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"

if [ -f "$REPO_ROOT/.env" ]; then
  set -a
  . "$REPO_ROOT/.env"
  set +a
fi

LOW_MEM="${LOW_MEM:-0}"

echo "=== Téléchargement des images Docker de la stack Orion ==="
docker compose -f "$REPO_ROOT/compose/docker-compose.yml" pull --ignore-buildable

if [ "$LOW_MEM" = "1" ]; then
  echo "Mode LOW_MEM=1 : téléchargement des modèles Ollama ignoré."
  exit 0
fi

if command -v ollama >/dev/null 2>&1; then
  echo "=== Téléchargement des modèles Ollama (qwen3:1.7b et nomic-embed-text:v1.5) ==="
  ollama pull qwen3:1.7b
  ollama pull nomic-embed-text:v1.5
else
  echo "[INFO] Binaire ollama non trouvé sur l'hôte (si vous êtes sous Linux avec Ollama en conteneur, les modèles seront tirés dans ollama-svc)."
fi
