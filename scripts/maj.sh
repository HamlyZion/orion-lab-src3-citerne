#!/usr/bin/env sh
# Mise à jour du cours : récupère la dernière version du dépôt modèle jassouline/orion-lab, puis ses images.
#   sh scripts/maj.sh             met à jour (make maj)
#   sh scripts/maj.sh --verifier  signale seulement qu'une mise à jour existe (fin de make up et de make start-labXX)
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# Le dépôt distant du cours : upstream dans le dépôt d'un trinôme, origin juste après le clone.
DISTANT=""
for nom in $(git remote 2>/dev/null); do
  if git config --get "remote.$nom.url" | grep -Eq 'github\.com[:/]jassouline/orion-lab(\.git)?/?$'; then
    DISTANT="$nom"
    break
  fi
done

# Récupération sans invite de mot de passe et abandonnée au bout de quelques secondes sans réseau.
recuperer() {
  GIT_TERMINAL_PROMPT=0 GIT_HTTP_LOW_SPEED_LIMIT=1000 GIT_HTTP_LOW_SPEED_TIME=5 \
    GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=5" \
    git fetch -q "$DISTANT" main
}

if [ "${1:-}" = "--verifier" ]; then
  [ -n "$DISTANT" ] || exit 0
  recuperer 2>/dev/null || exit 0
  RETARD="$(git rev-list --count "HEAD..$DISTANT/main" 2>/dev/null || echo 0)"
  if [ "$RETARD" -gt 0 ]; then
    echo ""
    echo "******************************************************************"
    echo "  Une mise à jour du cours est disponible : lancez  make maj"
    echo "  puis relancez la commande make start-labXX de votre lab."
    echo "******************************************************************"
  fi
  exit 0
fi

if [ -z "$DISTANT" ]; then
  echo "[ERREUR] Aucun dépôt distant ne pointe vers jassouline/orion-lab. Ajoutez-le, puis relancez make maj :" >&2
  echo "  git remote add upstream https://github.com/jassouline/orion-lab.git" >&2
  exit 1
fi

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "[ERREUR] Des fichiers modifiés ne sont pas enregistrés :" >&2
  git status --short --untracked-files=no >&2
  echo "Enregistrez-les, puis relancez make maj :" >&2
  echo '  git add -A && git commit -m "Travail en cours"' >&2
  exit 1
fi

echo "=== Récupération de la dernière version du cours ($DISTANT/main) ==="
if ! GIT_TERMINAL_PROMPT=0 git pull --no-rebase --no-edit "$DISTANT" main; then
  echo "[ERREUR] La mise à jour touche des lignes que vous avez modifiées." >&2
  echo "Les fichiers en conflit sont listés par git status : corrigez-les (ou appelez l'enseignant), puis git add et git commit." >&2
  exit 1
fi

echo "=== Téléchargement des images de cette version ==="
sh "$SCRIPT_DIR/pull.sh"

echo ""
echo "Mise à jour terminée. Relancez la commande make start-labXX de votre lab."
