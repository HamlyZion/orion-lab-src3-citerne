# Règles pour les agents — dépôt `orion-lab` (étudiants)

*Ce fichier est visible des étudiants : il ne contient rien de confidentiel.*

Ce dépôt est celui que les étudiants clonent pour le cours « Monitoring, Observabilité et AIOps » (ESGI, 5ᵉ année SRC). Il contient la configuration de la plateforme fil rouge Orion, les énoncés des labs, les gabarits des livrables et les outils que les étudiants utilisent ou modifient.

## Ce que ce dépôt ne contient jamais

- Le code source des services d'Orion et des outils du cours (console d'incident, vérifications) : ils sont livrés en images Docker figées par digest.
- Les scénarios d'incident, leurs mécanismes et la liste des incidents du game day.
- Les solutions et les corrigés.

Si ta tâche semble exiger l'un de ces éléments, arrête-toi et signale-le dans ton rapport : il appartient au dépôt enseignant `orion-cours`.

## À lire avant toute tâche

1. `README.md` : installation et prérequis.
2. `docs/architecture.md` : la fiche « Architecture d'Orion ».
3. La fiche de ta tâche et le contrat d'interfaces, que Jordan te fournit, ou que tu lis dans `orion-cours` si tu y as accès.

## Règles de travail

- **Une branche par tâche** et une pull request. Ne pousse jamais sur `main` : chaque fusion dans `main` est publiée automatiquement dans le dépôt modèle des étudiants (`.github/workflows/publier.yml`), qui la récupèrent avec `make maj`.
- **Énoncés en français**, vouvoiement, phrases courtes. Chaque lab indique sa durée, ses objectifs, ce qui est fourni, ce qui est à faire, et comment vérifier que c'est réussi.
- **Ne donne jamais la réponse dans l'énoncé.** On donne la méthode, pas le résultat : délais de détection, cause d'un incident non annoncé, valeurs attendues.
- **Configurations à compléter** : marque les trous par `# TODO(lab-NN) : …` et garde une configuration qui démarre même non complétée, sauf quand l'énoncé dit le contraire.
- **Compatibilité** : tout doit fonctionner sur trois systèmes. Ports publiés sur `127.0.0.1` uniquement.
  - **macOS** : Docker Desktop, OrbStack ou colima ; Ollama installé sur le poste.
  - **Linux** : Docker Engine ; Ollama en conteneur.
  - **Windows** : tout se fait dans Ubuntu sous WSL2, comme sous Linux, avec Docker Desktop (backend WSL2) ou Docker Engine dans WSL2. `make check` choisit le mode, standard ou `LOW_MEM`.
- **Vérification sur plusieurs postes** : une commande de vérification est validée sur Linux amd64 (Ubuntu), puis sur macOS. Un test fait sur un seul Mac ne suffit pas.
- **Versions figées** : images par digest, outils par version exacte, modèles Ollama par tag exact.
- **Pas de SaaS, pas de clé d'API.** Les seuls accès réseau sortants ont lieu pendant `make pull`.
- **Style d'écriture** : pas d'emojis, pas de formules creuses, une idée par phrase.

## Définition de « terminé »

- La commande de vérification du lab ou du livrable passe depuis un clone propre du dépôt.
- `README.md` et les énoncés concernés sont à jour.
- La pull request indique comment vérifier.
