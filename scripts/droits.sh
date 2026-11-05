#!/usr/bin/env sh
# Rend des dossiers du dépôt accessibles en écriture aux conteneurs : tools et rca tournent sous l'UID 10001.
#   sh scripts/droits.sh <dossier>...   (chemins relatifs à la racine du dépôt)
# Le chmod lancé depuis l'hôte échoue sans bruit quand le dossier appartient à root (dossier créé par Docker,
# dépôt cloné avec sudo), et ne s'applique pas quand Docker ne partage pas le dossier (Colima, dépôt hors du
# dossier personnel). Un conteneur root applique donc aussi les droits, tels que les conteneurs les voient.
set -u

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"

for dossier in "$@"; do
  mkdir -p "$REPO_ROOT/$dossier" 2>/dev/null || true
  chmod -R a+rwX "$REPO_ROOT/$dossier" 2>/dev/null || true
  docker run --rm -v "$REPO_ROOT/$dossier:/data" \
    pgvector/pgvector:0.8.7-pg17-bookworm \
    sh -c 'chmod 0777 /data && chmod -R a+rwX /data' >/dev/null 2>&1 || true
done
