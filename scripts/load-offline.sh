#!/usr/bin/env sh
set -eu

OFFLINE_DIR="${OFFLINE_DIR:-${1:-}}"

if [ -z "$OFFLINE_DIR" ] || [ ! -d "$OFFLINE_DIR" ]; then
  echo "Usage : make load-offline OFFLINE_DIR=/chemin/vers/cle-usb" >&2
  exit 1
fi

# Détection de l'architecture hôte (ou surcharge explicite via ARCH=arm64 / ARCH=amd64)
HOST_ARCH="$(uname -m)"
case "$HOST_ARCH" in
  arm64|aarch64) DETECTED_ARCH="arm64" ;;
  x86_64|amd64)  DETECTED_ARCH="amd64" ;;
  *)             DETECTED_ARCH="$HOST_ARCH" ;;
esac
TARGET_ARCH="${ARCH:-$DETECTED_ARCH}"

echo "=== Chargement des archives d'images Docker depuis $OFFLINE_DIR (architecture : $TARGET_ARCH) ==="

FOUND=0
# 1. Chercher d'abord les archives spécifiques à l'architecture cible (sans découpage de chemin avec espaces)
for archive in \
  "$OFFLINE_DIR"/images/*"${TARGET_ARCH}"*.tar \
  "$OFFLINE_DIR"/images/*"${TARGET_ARCH}"*.tar.gz \
  "$OFFLINE_DIR"/*"${TARGET_ARCH}"*.tar \
  "$OFFLINE_DIR"/*"${TARGET_ARCH}"*.tar.gz \
  "$OFFLINE_DIR"/"${TARGET_ARCH}"/images/*.tar \
  "$OFFLINE_DIR"/"${TARGET_ARCH}"/images/*.tar.gz \
  "$OFFLINE_DIR"/"${TARGET_ARCH}"/*.tar \
  "$OFFLINE_DIR"/"${TARGET_ARCH}"/*.tar.gz; do
  if [ -f "$archive" ]; then
    echo "  -> docker load -i $archive"
    docker load -i "$archive"
    FOUND=1
  fi
done

# 2. Si aucune archive spécifique n'a été trouvée, charger les archives présentes sans filtre
if [ "$FOUND" -eq 0 ]; then
  for archive in \
    "$OFFLINE_DIR"/images/*.tar \
    "$OFFLINE_DIR"/images/*.tar.gz \
    "$OFFLINE_DIR"/*.tar \
    "$OFFLINE_DIR"/*.tar.gz; do
    if [ -f "$archive" ]; then
      echo "  -> docker load -i $archive"
      docker load -i "$archive"
      FOUND=1
    fi
  done
fi

if [ "$FOUND" -eq 0 ]; then
  echo "[ERREUR] Aucune archive d'images Docker trouvée dans '$OFFLINE_DIR' (recherche pour architecture : $TARGET_ARCH)." >&2
  exit 1
fi

OLLAMA_DIR=""
if [ -d "$OFFLINE_DIR/ollama" ]; then
  OLLAMA_DIR="$OFFLINE_DIR/ollama"
elif [ -d "$OFFLINE_DIR/${TARGET_ARCH}/ollama" ]; then
  OLLAMA_DIR="$OFFLINE_DIR/${TARGET_ARCH}/ollama"
fi

if [ -n "$OLLAMA_DIR" ] && [ -d "$OLLAMA_DIR" ]; then
  OLLAMA_HOME="${OLLAMA_MODELS:-$HOME/.ollama/models}"
  echo "=== Copie des modèles Ollama vers $OLLAMA_HOME ==="
  mkdir -p "$OLLAMA_HOME"
  if ! cp -R "$OLLAMA_DIR"/* "$OLLAMA_HOME/"; then
    echo "[ERREUR] Échec de la copie des modèles Ollama depuis '$OLLAMA_DIR' vers '$OLLAMA_HOME' (vérifiez les permissions et l'espace disque)." >&2
    exit 1
  fi
fi

echo "Chargement hors-ligne terminé."
