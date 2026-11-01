# Orion — Laboratoire d'observabilité et d'AIOps

Ce dépôt contient l'environnement de travaux pratiques du cours **AIOps et observabilité** (5A SRC). Vous y opérez **Orion**, l'assistant documentaire interne (RAG) de l'entreprise fictive *Nordel*, utilisé par trois équipes : `support`, `rh` et `dev`.

---

## 1. Créer le dépôt du trinôme et configurer `upstream`

N'utilisez **pas** le bouton *Use this template* (un dépôt créé depuis un modèle GitHub n'a pas d'historique commun avec `orion-lab`, ce qui bloque `git pull upstream main`). Un seul membre du trinôme initialise le dépôt du groupe :

1. Sur GitHub, créez un dépôt **privé vide** nommé `orion-lab-<votre-groupe>` (**sans** `README`, sans `.gitignore` et sans licence).
2. Dans *Settings → Collaborators*, invitez les deux autres membres du trinôme ainsi que `jassouline` en **lecture** (*Read*).
3. Clonez `orion-lab`, renommez le dépôt distant en `upstream`, ajoutez votre dépôt privé en `origin` et poussez `main` :

```bash
git clone https://github.com/jassouline/orion-lab.git orion-lab-<votre-groupe>
cd orion-lab-<votre-groupe>
git config pull.rebase false
git remote rename origin upstream
git remote add origin git@github.com:<votre-compte>/orion-lab-<votre-groupe>.git
git push -u origin main
```

4. Les deux autres membres du trinôme clonent ensuite ce dépôt privé et ajoutent `upstream` :

```bash
git clone git@github.com:<compte-createur>/orion-lab-<votre-groupe>.git
cd orion-lab-<votre-groupe>
git config pull.rebase false
git remote add upstream https://github.com/jassouline/orion-lab.git
```

Pour récupérer une mise à jour du cours (nouvelle version des fichiers et des images) :

```bash
make maj
```

`make maj` fait `git pull upstream main`, puis `make pull`. Enregistrez d'abord votre travail (`git add -A && git commit -m "…"`) : la commande refuse de s'exécuter s'il reste des modifications non enregistrées. À la fin de `make up` et de chaque `make start-labXX`, un message vous prévient quand une mise à jour est disponible.

---

## 2. Prérequis matériels et logiciels

- **Processeur** : 4 cœurs logiques au minimum.
- **Mémoire vive** :
  - **16 Go de RAM** : configuration complète avec exécution locale des modèles d'embeddings et de génération via Ollama `0.40.9`. Au moins un poste par trinôme doit disposer de 16 Go pour le lab 4b (`make rca`).
  - **8 Go de RAM** : mode **`LOW_MEM=1`** sans Ollama (`ORION_OLLAMA_RATIO=0`), utilisant le cache d'embeddings pré-calculé et le corpus déjà vectorisé (empreinte totale inférieure à 3 Go).
- **Disque libre** : 12 Go (images Docker, modèles Ollama et volumes de données).
- **Outils requis sur l'hôte** :
  - `git`, `make`, `curl`, `openssl` ;
  - **`python3`** (version 3.10+, bibliothèque standard uniquement — fourni avec les outils de ligne de commande Xcode sous macOS et installé par défaut sous Ubuntu / WSL2) ;
  - **Docker Engine** et **Docker Compose v2** (`docker compose version`) ;
  - **Ollama `0.40.9`** exactement (sauf en mode `LOW_MEM=1`).

> **Sécurité réseau** : tous les ports publiés par la stack sont attachés à `127.0.0.1` uniquement. Ne configurez **jamais** `OLLAMA_HOST=0.0.0.0` sur votre machine : Ollama doit écouter exclusivement en local (`127.0.0.1:11434`).

---

## 3. Installation par système d'exploitation

### 3.1 macOS (Apple Silicon M1–M5 ou Intel)

1. **Outils système** : vérifiez la présence de `git`, `make` et `python3` (`xcode-select --install` si nécessaire).
2. **Moteur Docker** :
   - **Avec Colima (recommandé pour sa légèreté)** : le réglage par défaut de Colima (2 Go) est insuffisant. Démarrez-le avec au moins 8 Go de RAM :
     ```bash
     colima start --cpu 4 --memory 8 --disk 40
     ```
   - **Avec Docker Desktop** : ouvrez *Settings → Resources* et allouez au moins **8 Go de RAM** et **4 CPU** à la machine virtuelle.
3. **Ollama `0.40.9` natif** :
   - Installez Ollama `0.40.9` directement sur macOS (pas en conteneur Docker, afin d'utiliser l'accélération Metal).
   - Configurez les deux variables permettant de garder le modèle de génération et le modèle d'embedding chargés simultanément sans concurrence :
     ```bash
     launchctl setenv OLLAMA_MAX_LOADED_MODELS 2
     launchctl setenv OLLAMA_NUM_PARALLEL 1
     ```
   - Quittez puis relancez l'application `Ollama.app` pour appliquer ces variables.

### 3.2 Windows 11 (WSL2 — Ubuntu 24.04)

1. **Emplacement du clone (obligatoire)** :
   - Ouvrez votre terminal Ubuntu (WSL2) et clonez le dépôt **dans le système de fichiers Linux** (`~/orion-lab`), **jamais sous `/mnt/c/...`**.
   - Les volumes Docker montés depuis `/mnt/c` traversent le pont 9P de Windows : ils dégradent fortement les performances de PostgreSQL, Prometheus, Loki et Tempo.
2. **Configuration mémoire `.wslconfig`** :
   - Créez ou éditez le fichier `%USERPROFILE%\.wslconfig` sous Windows :
     ```ini
     [wsl2]
     # Sur un poste de 16 Go :
     memory=10GB
     # Sur un poste de 8 Go (mode LOW_MEM=1), utilisez : memory=5GB
     processors=4
     swap=2GB
     ```
   - Appliquez ce réglage depuis PowerShell avec `wsl --shutdown`, puis rouvrez Ubuntu.
3. **Moteur Docker selon votre RAM** :
   - **Poste de 16 Go** : utilisez Docker Desktop avec l'option *Use the WSL 2 based engine* activée (et l'intégration Ubuntu cochée dans *Settings → Resources → WSL Integration*), ou Docker Engine directement dans WSL2.
   - **Poste de 8 Go (`LOW_MEM=1`)** : n'utilisez **pas** Docker Desktop (son interface et ses services consomment 1,5 à 2 Go supplémentaires). Installez **Docker Engine (`docker-ce` et `docker-compose-plugin`) directement dans Ubuntu sous WSL2**.
4. **Ollama `0.40.9`** (poste de 16 Go) :
   - Définissez les variables d'environnement `OLLAMA_MAX_LOADED_MODELS=2` et `OLLAMA_NUM_PARALLEL=1`, puis redémarrez le service Ollama.

### 3.3 Linux natif (Ubuntu / Debian / Fedora)

1. Installez `docker.io` (ou `docker-ce`), `docker-compose-plugin`, `make`, `python3`, `curl` et `openssl`.
2. Vérifiez que votre utilisateur appartient au groupe `docker` (`sudo usermod -aG docker $USER`).
3. **Ollama `0.40.9`** :
   - **Option A — Ollama natif sur l'hôte** : configurez `OLLAMA_MAX_LOADED_MODELS=2` et `OLLAMA_NUM_PARALLEL=1` dans l'unité systemd `/etc/systemd/system/ollama.service.d/override.conf`, puis exécutez `sudo systemctl daemon-reload && sudo systemctl restart ollama`.
   - **Option B — Ollama en conteneur Docker** : ajoutez `ORION_USE_LINUX_COMPOSE=1` dans `.env` pour activer `compose/linux.yml`.

---

## 4. Préparation à J-7 et démarrage

Exécutez les trois commandes suivantes dans l'ordre :

```bash
# 1. Télécharger les images Docker (figées par digest) et les modèles Ollama
make pull

# 2. Vérifier la machine, étalonner Ollama / RCA et générer le fichier .env
make check

# 3. Démarrer la stack Orion
make up
```

### Sur une machine de 8 Go (`LOW_MEM=1`)

```bash
make pull LOW_MEM=1
make check LOW_MEM=1
make up
```

À la fin de `make check`, recopiez le bloc **Résumé à recopier dans le formulaire** (qui ne contient aucun identifiant de machine) dans le formulaire de vérification de pré-séance.

### Chargement hors-ligne depuis une clé USB (en séance)

Si le réseau de la salle est saturé, branchez la clé USB fournie par l'enseignant et exécutez :

```bash
make load-offline OFFLINE_DIR=/chemin/vers/cle-usb
make check
make up
```

---

## 5. Accès aux interfaces locales

Une fois `make up` terminé, toutes les interfaces sont joignables uniquement depuis votre poste (`127.0.0.1`) :

| Interface | URL locale | Rôle |
|---|---|---|
| **Point d'entrée HTTPS (Traefik → RAG)** | `https://127.0.0.1:8443/healthz` | Sonde de santé et route `POST /ask` |
| **Grafana** | `http://127.0.0.1:3000` | Dashboards RED, SLO, Explore (Prometheus, Loki, Tempo) |
| **Prometheus** | `http://127.0.0.1:9090` | Métriques, cibles (`/targets`) et règles (`/rules`) |
| **Alertmanager** | `http://127.0.0.1:9093` | Alertes actives (`page` et `ticket`) |
| **Console d'incident** | `http://127.0.0.1:8088` | Sessions des labs et du game day (mode d'emploi : docs/console.md) |

### Si une interface ne répond pas

Après chaque `make up` ou `make start-lab*`, un script vérifie automatiquement que chaque interface répond et provient bien de la pile Orion. Si une interface est signalée en échec :
1. **Port occupé sur la machine hôte** : un autre programme écoute déjà sur ce port (par exemple une autre instance de Grafana ou un serveur de développement sur le port 3000). Identifiez le programme responsable avec :
   ```bash
   lsof -nP -iTCP:<port> -sTCP:LISTEN
   ```
   puis arrêtez ce programme avant de relancer `make up`.
2. **Transfert de ports bloqué sous Colima (macOS)** : Colima peut cesser de transférer les ports vers l'hôte macOS alors même que `docker compose ps` affiche les conteneurs à l'état `Up`. Dans ce cas, redémarrez Colima puis relancez la pile :
   ```bash
   colima restart
   make up
   ```

Pour envoyer manuellement une question à Orion en utilisant la clé de l'équipe `support` générée dans `.env` :

```bash
set -a && . ./.env && set +a
curl --cacert config/traefik/certs/ca.crt \
  -H "Authorization: Bearer $ORION_KEY_SUPPORT" \
  -H "Content-Type: application/json" \
  -d '{"question": "[support] Quelle est la procédure exacte pour : Procédure de réinitialisation du VPN Nordel (DOC-SUP-001) ?"}' \
  https://localhost:8443/ask
```

---

## 6. Remettre vos travaux

### Jetons de checkpoint

À la fin de chaque checkpoint évalué (labs `1b`, `2b`, `3` et `4b`), la commande `make check-labX PIN=... ETU=...` (où `ETU` contient le numéro étudiant de la personne qui lance la commande, un seul numéro, par exemple `ETU=20260001` ; chacun lance au moins un checkpoint sur les quatre) affiche un jeton chiffré unique commençant par `ORION-CKn-...`.
Chaque jeton doit être ajouté, sur sa propre ligne, dans le fichier `jetons/ckn.txt` à la racine de votre dépôt privé, puis poussé sur GitHub :

```bash
git add jetons/ckn.txt
git commit -m "Remise jeton checkpoint X"
git push
```

L'heure de validation est chiffrée de manière inviolable à l'intérieur du jeton ; la date du commit Git ne compte pas.

### Projet

Le rendu final du projet est constitué par l'état de votre dépôt GitHub privé (initialisé depuis `orion-lab` selon le §1, avec `jassouline` invité en lecture) au niveau du tag annoté `rendu-projet`.

Pour poser ce tag annoté et le pousser sur GitHub :
```bash
git tag -a rendu-projet -m "Rendu final du projet Orion"
git push origin rendu-projet
```

Si vous effectuez une nouvelle remise avant l'échéance, déplacez le tag avec :
```bash
git tag -fa rendu-projet -m "Nouvelle remise du projet Orion"
git push -f origin rendu-projet
```

### Échéance

La date limite de remise du projet est fixée à **sept jours après la séance 8, à 23 h 59, heure de Paris**.
Aucun retard n'est accepté : seul compte le dernier tag `rendu-projet` posé avant l'heure limite ; un tag posé après l'échéance n'est pas lu.

---

## 7. Commandes `make` de référence

| Commande | Action |
|---|---|
| `make pull` | Télécharge les images Docker et les modèles Ollama (`LOW_MEM=1` possible) |
| `make check` | Vérifie le poste, mesure les débits d'Ollama, calibre la RCA et écrit `.env` |
| `make load-offline OFFLINE_DIR=...` | Charge les images et modèles depuis une clé USB |
| `make up` | Démarre la stack Orion et vérifie la disponibilité des interfaces |
| `make down` | Arrête la pile en conservant les données (à exécuter en fin de séance) |
| `make maj` | Récupère la dernière version du cours (`git pull upstream main`) et ses images (`make pull`) |
| `make start-lab1a` … `make start-lab4b` | Place l'environnement dans l'état de départ du lab demandé |
| `make check-lab1b PIN=... ETU=...` | Vérifie le checkpoint (labs `1b`, `2b`, `3`, `4b`) et affiche le jeton de validation (`ETU` = votre numéro étudiant, ex. `ETU=20260001`) |
| `make rca` | Lance l'outil d'analyse de cause racine du lab 4b (poste 16 Go uniquement) |

Consultez également la fiche `docs/architecture.md` pour le détail des composants, des métriques, de la chaîne de timeouts et du cycle de charge.

