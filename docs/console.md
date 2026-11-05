# Guide d'utilisation de la console d'incident Orion

La console d'incident Orion est accessible dans votre navigateur à l'adresse `http://127.0.0.1:8088` dès que la pile est démarrée (`make up`).

---

## Déroulé d'une session de lab

Dans toutes les séances de lab utilisant la console d'incident (Labs 1b, 2b, 3, 4a et 4b), suivez toujours les six parties de l'interface dans cet ordre :

1. **Partie `1. Code de session et rôles d'équipe` — Ouvrir la session (déclenche la panne sans délai)** :
   - Saisissez le code à 10 caractères indiqué dans l'énoncé du lab dans le champ **`Code de session (10 caractères)`**.
   - Renseignez les **trois prénoms obligatoires** : **`IC (Incident Commander)`**, **`Mitigator`** et **`Investigator`** (le 4e champ **`Second Investigator (groupe de quatre)`** est optionnel).
   - Cliquez sur **`Ouvrir la session`**.
   - **Important** :
     - En séance de lab, cliquer sur **`Ouvrir la session`** **déclenche immédiatement la panne annoncée, sans délai** (contrairement au Game Day où un délai aléatoire précède l'injection).
     - Ouvrir une session **réinitialise l'état de la console** : toute prédiction ou observation saisie *avant* de cliquer sur **`Ouvrir la session`** serait effacée. Ne cliquez donc qu'une seule fois sur **`Ouvrir la session`** au début du scénario (pour permuter les rôles en cours de séance, utilisez **`Mettre à jour les rôles`**).
2. **Partie `2. Prédiction avant observation (Séance de Lab)` — Enregistrer la prédiction juste après l'ouverture** :
   - **Immédiatement après avoir cliqué sur `Ouvrir la session`, et avant de regarder Grafana, Prometheus, Loki ou Tempo**, l'**Investigator** (avec le trinôme) remplit :
     - **`Hypothèse et comportement attendu du SLI`** *(obligatoire)* : quel SLI, quelle courbe ou quelle alerte va réagir, et dans quel sens ;
     - **`Requête ou métrique surveillée`** : la requête ou le nom du signal surveillé.
   - Cliquez sur **`Enregistrer la prédiction`**. Les fenêtres glissantes de Prometheus et les clauses `for:` (par exemple `for: 2m`) laissent le temps d'enregistrer cette prédiction avant que les alertes ne se déclenchent.
   - **Sous-panneau `Injection générique d'erreurs HTTP 500 (Lab 1b)`** : au Lab 1b (`make start-lab1b`), un encadré supplémentaire apparaît en bas de la partie 2 avec les champs **`Taux d'erreurs (%)`** (`0` à `100`, `20` par défaut) et **`Durée (s)`** (`10` à `600`, `240` par défaut), et les boutons **`Injecter les erreurs`** et **`Rétablir (0 %)`**. Ce sous-panneau **ne dépend pas de l'ouverture ou de la clôture de la session** ; l'injection s'arrête seule à la fin de la durée configurée ou dès que l'on clique sur **`Rétablir (0 %)`**.
3. **Observation des signaux et Partie `3. Déclaration d'incident et constats horodatés`** :
   - Observez les courbes et les alertes dans Grafana (`http://127.0.0.1:3000`), Prometheus (`http://127.0.0.1:9090`), Loki ou Tempo selon le lab.
   - **Déclarer l'incident (`IC`)** : dans le premier formulaire de la partie 3, l'**IC** remplit **`Déclaration initiale (symptôme utilisateur / SLI en écart)`**, choisit la **`Sévérité`** et l'**`Auteur`**, puis clique sur **`Déclarer l'incident`**.
   - **Ajouter une observation avec sa requête de preuve (`Investigator`)** : dans le second formulaire de la partie 3, l'**Investigator** remplit **`Constat d'observation (requis avant tout levier)`** et **`Requête de preuve (PromQL, LogQL, TraceQL ou SQL)`**, puis clique sur **`Ajouter l'observation au journal`**.
   - **Règle d'exploitation** : **aucun levier de la partie 4 ne peut être exécuté sans qu'au moins une observation ait été enregistrée depuis le dernier levier.**
4. **Partie `5. Indices progressifs et révélation` (si vous êtes bloqués)** :
   - Trois niveaux d'indices (**`Indice 1 (-1 pt)`**, **`Indice 2 (-1,5 pt)`**, **`Indice 3 (-2 pts)`**) et le bouton **`Révéler l'incident (Lab)`** sont utilisables sans attente en séance de lab.
   - **Les pénalités de points affichées sur les indices ne comptent qu'au Game Day évalué (séance 8)** : en séance de lab, servez-vous des indices si vous êtes bloqués après quelques minutes d'investigation (et de **`Révéler l'incident (Lab)`** uniquement en dernier recours).
5. **Partie `4. Mitiger — Catalogue d'actions` — Exécuter le levier et vérifier le retour à la normale** :
   - Une fois l'observation enregistrée en partie 3, le **Mitigator** sélectionne la **`Catégorie de levier`** et la **`Cible ou paramètre`**, puis clique sur **`Exécuter le levier`**.
   - Un levier pertinent corrige ou contourne la panne injectée dans la pile Orion.
   - **Vérification manuelle sur les courbes** : la chronologie `timeline.md` en bas de page enregistre automatiquement le déclenchement des alertes (`firing`), mais **ne génère pas d'événement automatique de retour à la normale**. Après chaque levier, vérifiez vous-mêmes sur vos courbes Grafana et Prometheus (pendant 2 à 5 minutes selon les fenêtres glissantes) que le SLI repasse sous son seuil nominal et que l'alerte s'éteint.
6. **Partie `6. Cause racine, clôture et export des preuves` — Cause racine, clôture et archive** :
   - Lorsque le retour à la normale est vérifié, remplissez **`Cause racine identifiée (mécanisme précis)`** et **`Preuve technique (requête ou extrait de log/trace)`**, puis cliquez sur **`Enregistrer la cause racine`**.
   - L'**IC** renseigne ensuite le **`Bilan de clôture (état du SLI après rétablissement)`** et clique sur **`Clôturer l'incident et générer l'archive`**.
   - **Faut-il envoyer la chronologie ou l'archive `.tar.gz` pendant les labs ? Non.** En séance de lab, l'archive générée (`Télécharger l'archive (.tar.gz)`) n'est pas à remettre : la console sert d'entraînement pour le Game Day de la séance 8 (où l'archive sera jointe à votre post-mortem).

---

## 1. Ouverture d'une session et attribution des rôles

Au début d'un lab ou d'une manche de Game Day :
1. Saisissez le **code de session** à 10 caractères communiqué par l'enseignant ou indiqué dans l'énoncé du lab.
2. Renseignez les prénoms des rôles (trinôme ou groupe de quatre) :
   - **IC (Incident Commander)** : coordonne la réponse, enregistre la déclaration initiale, la cause racine et prononce la clôture.
   - **Mitigator** : choisit et exécute les actions de mitigation après enregistrement d'une observation.
   - **Investigator** : explore les métriques, les journaux et les traces, et consigne les observations horodatées appuyées par une requête de preuve.
   - **Second Investigator (groupe de quatre)** : rôle optionnel d'investigation supplémentaire pour les groupes de quatre étudiants.
3. Cliquez sur **Ouvrir la session**. Vous pouvez permuter les rôles d'une manche à l'autre avec le bouton **Mettre à jour les rôles**.

---

## 2. Prédiction avant observation (séances de lab)

Lors des séances de lab guidées :
1. Juste après avoir cliqué sur **Ouvrir la session** et avant de consulter Grafana, enregistrez votre **prédiction** dans la partie **2. Prédiction avant observation (Séance de Lab)** (**Hypothèse et comportement attendu du SLI** et **Requête ou métrique surveillée**, bouton **Enregistrer la prédiction**) : quel SLI ou quelle métrique va bouger en premier, et dans quel sens.
2. Dans la séance du **Lab 1b**, le sous-panneau **Injection générique d'erreurs HTTP 500 (Lab 1b)** en bas de la partie 2 permet de déclencher une hausse temporaire du taux d'erreurs HTTP 500 (**Taux d'erreurs (%)** et **Durée (s)**, bouton **Injecter les erreurs**) afin de vérifier le déclenchement de votre règle d'alerte multi-fenêtres, puis de rétablir l'état nominal (**Rétablir (0 %)**).

---

## 3. Déclaration d'incident et observations horodatées

1. **Déclarer l'incident** : dès qu'une alerte retentit ou qu'un écart de SLI est constaté, l'IC enregistre la **Déclaration initiale (symptôme utilisateur / SLI en écart)** en précisant la **Sévérité** et l'**Auteur**, puis clique sur **Déclarer l'incident**.
2. **Enregistrer des observations** : chaque **Constat d'observation (requis avant tout levier)** doit être appuyé par la **Requête de preuve (PromQL, LogQL, TraceQL ou SQL)** exacte qui l'établit (bouton **Ajouter l'observation au journal**).
3. **Règle d'exploitation** : **aucun levier de mitigation ne peut être exécuté sans qu'au moins une observation horodatée (constat + requête de preuve) ait été enregistrée au préalable.**

---

## 4. Menu « Mitiger »

Le catalogue de leviers propose des actions d'exploitation standard :
- **Mode dégradé (extraits documentaires sans génération)** : renvoie les extraits documentaires pertinents sans appeler le modèle de génération (rétablit la disponibilité et la latence au prix de la qualité de synthèse).
- **Délestage du trafic (pourcentage ou équipe)** : par équipe (`support`, `rh`, `dev`) ou par pourcentage global (`25 %`, `50 %`).
- **Retour à la version précédente d'un service** (`gateway`, `rag`, `worker`).
- **Redémarrage d'un service** (`gateway`, `rag`, `worker`, `llm-sim`).
- **Ajustement d'un paramètre de configuration** (timeout, taille de pool, quota, rate limiting, durée de maintien du modèle en mémoire `keep-alive`, `top-k`, `max_tokens`, nombre de tentatives, concurrence du worker, niveau de log, modèle d'embeddings).
- **Relance de l'indexation documentaire** (incrémentale ou complète).
- **Opération de maintenance de la base de données** (purge selon la politique de rétention, reconstruction d'un index).
- **Aucune action d'urgence** (option **Maintenir le système en l'état (alerte bénigne ou bruit)**) : à retenir lorsque vous établissez qu'une alerte provient d'un bruit bénin ou d'un seuil mal calibré sans impact sur les SLO utilisateur.

Après chaque levier (**Exécuter le levier**), ne vous fiez pas au seul message de prise en compte : **vérifiez sur vos courbes Grafana si le SLI revient réellement sous son seuil nominal.** Une action non adaptée à la cause peut provoquer un transitoire de latence d'environ 45 secondes sans rétablir le service.

---

## 5. Indices progressifs, cause racine et clôture

1. **Indices progressifs** : trois niveaux d'indices sont proposés par session :
   - **Indice 1 (-1 pt)** : signaux et composants concernés.
   - **Indice 2 (-1,5 pt)** : métrique, champ de log ou span à examiner.
   - **Indice 3 (-2 pts)** : piste de vérification technique.
   En séance de Game Day, les indices se débloquent 25 minutes après l'ouverture de la session (en séance de lab, ils sont accessibles sans délai et sans pénalité, avec un bouton **Révéler l'incident (Lab)** en dernier recours).
2. **Cause racine** : avant de clôturer, renseignez la **Cause racine identifiée (mécanisme précis)** ainsi que la **Preuve technique (requête ou extrait de log/trace)** correspondante, puis cliquez sur **Enregistrer la cause racine**.
3. **Clôture et export** : renseignez le **Bilan de clôture (état du SLI après rétablissement)**, cliquez sur **Clôturer l'incident et générer l'archive**, puis téléchargez l'archive `.tar.gz` (**Télécharger l'archive (.tar.gz)**, ou récupérez-la dans `.orion-state/exports/`). Lors du Game Day, cette archive contient votre chronologie `timeline.md`, le journal chiffré `journal.age` et les instantanés de preuves nécessaires à votre post-mortem.
