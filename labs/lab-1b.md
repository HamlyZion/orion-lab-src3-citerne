# Lab 1b — PromQL, recording rules et alertes sur burn rate

- **Durée** : 110 minutes
- **Séance** : 2 (Métriques, SLI/SLO et alerting par burn rate)
- **Code de session console** : `56UABWUT55`
- **Checkpoint évalué** : Checkpoint 1 (`make check-lab1b PIN=<votre_pin> ETU=<votre_numero_etudiant>`)
- **Dépôt de travail** : votre dépôt de trinôme, créé une seule fois à la séance 1 (README, §1 : `git clone https://github.com/jassouline/orion-lab.git`, puis `upstream` et `origin`). `make start-lab1b` remet l'état d'exécution à zéro sans toucher à vos fichiers.

## Objectifs

À l'issue de ce lab, vous saurez :

1. Écrire des requêtes PromQL exactes pour mesurer le trafic, le ratio d'erreurs hors rejets de quota (`HTTP 429`) et les centiles de latence par backend LLM.
2. Implémenter les *recording rules* et l'alerte multi-fenêtres de burn rate sur le SLO de disponibilité d'Orion dans `config/prometheus/rules.yml`.
3. Auditer et rectifier une règle d'alerte PromQL générée par un assistant avant sa mise en production.
4. Prédire le comportement de vos alertes avant une injection en direct, puis confronter votre prédiction aux signaux observés.

## Ce qui est fourni

- Le fichier `config/prometheus/rules.yml` contenant déjà :
  - la *recording rule* de débit `job:traefik_requests:rate5m` ;
  - les *recording rules* et l'alerte de référence du SLO de latence (`job:orion_gateway_latency_p95:5m`, `backend:orion_gateway_latency_p95:5m`, `OrionSLOLatencePage`) ;
  - le SLO de qualité (`job:orion_quality_good_ratio:rate15m`, `OrionSLOQualiteTicket`) ;
  - l'alerte de quota par équipe (`OrionQuotaEquipeRejetsTicket`) et l'alerte d'absence de trafic (`OrionAbsenceDeTraficPage`) ;
  - trois emplacements marqués `# TODO(lab-1b)` à compléter pour le SLO de disponibilité.
- La configuration d'Alertmanager dans `config/alertmanager/alertmanager.yml` (`http://127.0.0.1:9093`).
- Les tableaux de bord Grafana **Orion Gateway — RED** et **Orion — SLO Latence & Qualité** (`http://127.0.0.1:3000`).
- Un artefact généré par un assistant à auditer dans `labs/artefacts/lab-1b-slo-latence-ia.yml`.

> **Repartir d'un fichier d'origine** : `make start-lab1b` remet uniquement l'état d'exécution à plat sans écraser vos fichiers. Pour retrouver la version d'origine d'un fichier depuis le dépôt modèle :
> ```bash
> git checkout upstream/main -- config/prometheus/rules.yml
> ```

## Encadré de référence — Les valeurs de l'alerte burn rate

| Ce que vous écrivez | Valeur | À quoi ça sert |
|---|---|---|
| Seuil d'erreur | `14.4 * 0.005`, soit 7,2 % | 14,4 : la valeur que Google recommande pour réveiller l'astreinte. 0,005 : le budget d'erreur de 0,5 % (SLO de disponibilité de 99,5 %, hors `HTTP 429`). |
| Fenêtre longue | `8m` | Est-ce que ça dure ? Un pic de quelques secondes ne suffit pas à faire sonner l'alerte. |
| Fenêtre courte | `40s` | Est-ce que ça dure encore ? Dès la réparation, l'alerte se calme vite, sans attendre que les 8 minutes se vident. |
| Garde de volume | au moins `10` requêtes hors `429` sur `40s` | Pas d'alerte pour une seule erreur quand le trafic est faible. |
| Maintien | `keep_firing_for: 2m`, sans clause `for:` | L'alerte reste allumée 2 minutes après la réparation, pour ne pas clignoter. Une clause `for:` retarderait inutilement son déclenchement. |

En production, Google utilise des fenêtres de 1 h et 5 min. Nous les raccourcissons à 8 min et 40 s pour voir l'alerte sonner et s'éteindre pendant le lab.

## Étapes à réaliser

### Étape 1 — Préparation et exploration PromQL (20 min)

1. Initialisez l'état d'exécution du lab 1b :
   ```bash
   make start-lab1b
   ```
2. Dans l'interface Prometheus (`http://127.0.0.1:9090/query` — tapez la requête dans le champ d'expression, puis Execute ; onglet Graph pour la courbe), écrivez et testez les requêtes permettant de calculer :
   - le débit de requêtes par seconde sur le service Traefik `rag@file` en excluant les rejets de quota (`code!="429"`) ;
   - le ratio d'erreurs `5xx` (`code=~"5.."`) rapporté au total des requêtes hors `429` sur `rag@file` ;
     > En marche normale, Traefik n'a encore servi aucune réponse `5xx` : la série `code=~"5.."` n'existe pas, et la requête renvoie un résultat vide, pas `0`. C'est attendu. Pour afficher `0`, ajoutez `or vector(0)` au numérateur : `(sum(rate(...{..., code=~"5.."}[5m])) or vector(0)) / sum(rate(...))`.
   - le 95e centile de latence de `gateway` agrégé par `backend` (`ollama` vs `simule`) à partir de `gateway_request_duration_seconds_bucket`.
3. Vérifiez dans le tableau de bord Grafana **Orion — SLO Latence & Qualité** l'écart de latence entre le centile global (`job:orion_gateway_latency_p95:5m`) et le centile ventilé par backend (`backend:orion_gateway_latency_p95:5m`).

### Étape 2 — Recording rules du SLO de disponibilité (25 min)

Ouvrez `config/prometheus/rules.yml` et complétez les deux premiers marqueurs `# TODO(lab-1b)` dans le groupe `orion_slo_recording` :

1. `job:traefik_errors:ratio_rate8m` : ratio des requêtes en erreur `5xx` (`code=~"5.."`) sur l'ensemble des requêtes hors `429` (`code!="429"`) pour `service="rag@file"`, calculé avec `rate(...[8m])`.
2. `job:traefik_errors:ratio_rate40s` : même ratio calculé sur une fenêtre de `40s` (`rate(...[40s])`).
3. Vérifiez la syntaxe de votre fichier avec `promtool` via le conteneur Prometheus, puis rechargez la configuration :
   ```bash
   docker compose -f compose/docker-compose.yml exec -T prometheus \
     promtool check rules /etc/prometheus/rules.yml
   curl -fsS -X POST http://127.0.0.1:9090/-/reload
   ```
4. Vérifiez sur `http://127.0.0.1:9090/rules` que `job:traefik_errors:ratio_rate8m` et `job:traefik_errors:ratio_rate40s` sont évaluées sans erreur.

### Étape 3 — Alerte multi-fenêtres sur burn rate (25 min)

Complétez le troisième marqueur `# TODO(lab-1b)` dans `config/prometheus/rules.yml` pour la règle `OrionSLODisponibiliteBurnRatePage` :

1. L'alerte doit déclencher lorsque **simultanément** :
   - `job:traefik_errors:ratio_rate8m > (14.4 * 0.005)` ;
   - `job:traefik_errors:ratio_rate40s > (14.4 * 0.005)` ;
   - le volume sur la fenêtre de `40s` hors `429` pour `service="rag@file"` est d'au moins `10` requêtes (`sum(increase(traefik_service_requests_total{service="rag@file", code!="429"}[40s])) >= 10`).
2. Configurez `keep_firing_for: 2m` et **n'ajoutez aucune clause `for:`**.
3. Conservez les labels `severity: page`, `slo: availability` et `service: orion-rag`.
4. Validez avec `promtool check rules` et rechargez Prometheus (`POST http://127.0.0.1:9090/-/reload`).

### Étape 4 — Audit critique d'un artefact généré par un assistant (15 min)

1. Ouvrez `labs/artefacts/lab-1b-slo-latence-ia.yml` **sans l'ajouter tout de suite à Prometheus**.
2. En binôme, identifiez par écrit toutes les erreurs de conception et de syntaxe PromQL présentes dans ce fichier (agrégation d'histogramme classique, choix des fenêtres, seuils par backend, garde de volume, clause `for:`).
3. Comparez cet artefact à la règle de référence `OrionSLOLatencePage` déjà présente dans `config/prometheus/rules.yml`.

### Étape 5 — Prédiction et injection annoncée (15 min)

> **Changement annoncé** — ticket de l'équipe plateforme, appliqué à l'ouverture de la session `56UABWUT55` : pour libérer de la mémoire, la passerelle ne conserve plus le modèle de génération chargé entre deux requêtes ; il est rechargé à chaque appel. Aucun autre composant ne change. Avant de regarder Grafana, prédisez quels signaux et quelles alertes vont réagir, dans quel sens et au bout de combien de temps.

Pour le déroulé général d'une session dans la console d'incident (`http://127.0.0.1:8088`), reportez-vous à la section « Déroulé d'une session de lab » de `docs/console.md`. Suivez ici la séquence ci-dessous dans l'ordre :

1. **Partie `1. Code de session et rôles d'équipe` — Ouvrir la session (`IC`)** :
   - Dans le champ **`Code de session (10 caractères)`**, saisissez :
     ```text
     56UABWUT55
     ```
   - Renseignez les trois prénoms obligatoires dans **`IC (Incident Commander)`**, **`Mitigator`** et **`Investigator`** (le champ **`Second Investigator (groupe de quatre)`** est optionnel), puis cliquez sur **`Ouvrir la session`**.
   - **Ce qui se passe** : en séance de lab, cliquer sur **`Ouvrir la session`** réinitialise l'état de la console (toute prédiction saisie avant l'ouverture serait effacée) et **déclenche immédiatement la panne annoncée, sans délai**. Ne cliquez plus sur **`Ouvrir la session`** par la suite.
2. **Partie `2. Prédiction avant observation (Séance de Lab)` — Enregistrer la prédiction tout de suite (`Investigator`)** :
   - **Immédiatement après l'ouverture de la session, sans regarder Grafana ni Prometheus**, remplissez les deux champs de la partie 2 :
     - **`Hypothèse et comportement attendu du SLI`** *(obligatoire)* : indiquez quelle(s) alerte(s) et quelle(s) courbe(s) vont réagir lors de la dégradation annoncée (gabarit : `<signal> va <monter / baisser / rester stable> ; l'alerte <nom> va <passer en firing / rester inactive> au bout de <durée>`).
     - **`Requête ou métrique surveillée`** : la requête PromQL ou la *recording rule* que vous surveillez.
   - Cliquez sur **`Enregistrer la prédiction`**.
3. **Observer dans Prometheus (`http://127.0.0.1:9090`) et Grafana (`http://127.0.0.1:3000`) (`Investigator` + `IC`)** :
   - Les effets de `56UABWUT55` mettent 30 secondes à 2 minutes à apparaître sur les centiles glissants, et `OrionSLOLatencePage` comporte une temporisation `for: 2m`.
   - Dans Prometheus (`http://127.0.0.1:9090/query`) et dans les tableaux de bord Grafana **Orion Gateway — RED** et **Orion — SLO Latence & Qualité**, observez et comparez à votre prédiction :
     - les courbes de ratio d'erreurs `job:traefik_errors:ratio_rate8m` et `job:traefik_errors:ratio_rate40s`, la latence par backend `backend:orion_gateway_latency_p95:5m`, le TTFT p95 sur 2 minutes (`histogram_quantile(0.95, sum by (le) (rate(gateway_ttft_seconds_bucket[2m])))`) et la durée moyenne de chargement du modèle (`rate(gateway_load_duration_seconds_sum[1m]) / rate(gateway_load_duration_seconds_count[1m])`) ;
     - sur `http://127.0.0.1:9090/alerts`, l'état des deux alertes de SLO **`OrionSLOLatencePage`** et **`OrionSLODisponibiliteBurnRatePage`**.
4. **Partie `3. Déclaration d'incident et constats horodatés` — Déclarer l'incident (`IC`) puis ajouter une observation (`Investigator`)** :
   - **Déclarer l'incident (`IC`)** : dans le premier formulaire de la partie 3, renseignez **`Déclaration initiale (symptôme utilisateur / SLI en écart)`** (gabarit : `<symptôme> sur <backend> depuis <heure>`), choisissez la **`Sévérité`** et l'**`Auteur`** `IC`, puis cliquez sur **`Déclarer l'incident`**.
   - **Ajouter une observation avec sa requête de preuve (`Investigator`)** : dans le second formulaire de la partie 3, renseignez :
     - **`Constat d'observation (requis avant tout levier)`** *(obligatoire)* : gabarit `<métrique> passe de <a> à <b> sur <backend>` ;
     - **`Requête de preuve (PromQL, LogQL, TraceQL ou SQL)`** *(obligatoire)* : la requête PromQL exacte qui établit votre constat.
   - Cliquez sur **`Ajouter l'observation au journal`**. **Un levier de la partie 4 ne peut être exécuté que si au moins une observation a été enregistrée au préalable.**
5. **Partie `5. Indices progressifs et révélation` (uniquement si vous êtes bloqués)** :
   - Trois niveaux d'indices (**`Indice 1 (-1 pt)`**, **`Indice 2 (-1,5 pt)`** et **`Indice 3 (-2 pts)`**) sont disponibles pour vous débloquer progressivement.
   - **Les pénalités de points affichées ne comptent qu'au Game Day évalué de la séance 6** : en séance de lab, servez-vous des indices si vous êtes bloqués (le bouton **`Révéler l'incident (Lab)`** affiche la panne en dernier recours).
6. **Partie `4. Mitiger — Catalogue d'actions` — Appliquer le levier pertinent (`Mitigator`) et vérifier le retour à la normale** :
   - Sélectionnez :
     - **`Catégorie de levier`** : **`Ajustement d'un paramètre de configuration`**
     - **`Cible ou paramètre`** : **`Durée de maintien du modèle en mémoire (keep-alive)`**
     *(Alternative également acceptée : **`Redémarrage d'un service`** → **`Service gateway`**).*
   - Cliquez sur **`Exécuter le levier`**.
   - **Ce que fait ce levier** : il rétablit le maintien du modèle en mémoire (`keep-alive`) sur la passerelle pour éviter de recharger le modèle à froid après chaque requête.
   - **Vérifier le retour à la normale sur les courbes** : vérifiez dans Prometheus (`http://127.0.0.1:9090/query`) et Grafana qu'en environ **2 minutes** le TTFT p95 sur 2 minutes du backend `simule` repasse sous `1,5 s` et que la durée moyenne de chargement modèle retombe près de `0 s`, puis qu'en environ **5 minutes** `backend:orion_gateway_latency_p95:5m{backend="simule"}` repasse sous `2,5 s` et `OrionSLOLatencePage` redevient `inactive`.
     > Ne concluez pas trop vite que le levier est sans effet : la durée de chargement tombe en moins d'une minute, mais un centile calculé sur une fenêtre de 5 minutes garde les requêtes lentes tant qu'elles restent dans la fenêtre. Il redescend progressivement et ne passe sous le seuil qu'au bout de 4 à 5 minutes.
7. **Partie `6. Cause racine, clôture et export des preuves` — Quand renseigner la cause racine et clôturer (`Investigator` + `IC`)** :
   - Dès que le retour à la normale est constaté (à la fin de l'étape 5, ou à la fin de l'étape 6), renseignez **`Cause racine identifiée (mécanisme précis)`** (gabarit : `<composant et paramètre en cause> provoquant <effet mesuré sur chaque requête>`) et **`Preuve technique (requête ou extrait de log/trace)`** (gabarit : `<requête PromQL établissant la cause racine>`), puis cliquez sur **`Enregistrer la cause racine`**.
   - Renseignez ensuite **`Bilan de clôture (état du SLI après rétablissement)`** (gabarit : `<levier appliqué> ; <SLI> revenu à <valeur nominale> et alerte <nom> repassée inactive`) et cliquez sur **`Clôturer l'incident et générer l'archive`**.
   - **Important** :
     - **L'archive `.tar.gz` et la chronologie `timeline.md` ne sont pas à remettre au lab** : c'est uniquement l'entraînement pour le Game Day de la séance 6.
     - **L'injection générique de l'étape 6 est située en partie 2 et ne dépend pas de l'ouverture ou de la clôture de la session** : vous pouvez aussi bien clôturer l'incident à la fin de l'étape 5 que garder la session ouverte pendant l'étape 6. *(Si le sous-panneau d'injection générique n'est pas visible en bas de la partie 2, lancez `make start-lab1b` dans votre terminal et rafraîchissez la page `http://127.0.0.1:8088`.)*

### Étape 6 — Observer l'alerte pendant une injection d'erreurs (10 min)

1. **Où déclencher l'injection** : dans la console (`http://127.0.0.1:8088`), en bas de la **partie `2. Prédiction avant observation (Séance de Lab)`**, dans l'encadré **`Injection générique d'erreurs HTTP 500 (Lab 1b)`**. L'injection s'arrête seule au terme de la durée choisie, ou immédiatement avec le bouton **`Rétablir (0 %)`**.
2. **Préparer l'observation** :
   - dans Prometheus (`http://127.0.0.1:9090/query`, onglet Graph), affichez les deux fenêtres sur un même graphique :
     ```promql
     {__name__=~"job:traefik_errors:ratio_rate.*"}
     ```
     Les courbes apparaissent avec les premières erreurs. Le seuil de l'alerte vaut `0.072` sur l'axe vertical.
   - ouvrez dans un autre onglet `http://127.0.0.1:9090/alerts`.
3. **Injecter (`Mitigator`)** : réglez **`Taux d'erreurs (%)`** sur `100` et **`Durée (s)`** sur `120`, puis cliquez sur **`Injecter les erreurs`**.
4. **Observer pendant environ 5 minutes (`Investigator` + `IC`)** : rafraîchissez le graphique et la page des alertes, et notez dans les notes du trinôme :
   - laquelle des deux courbes monte en premier ;
   - au bout de combien de temps environ `OrionSLODisponibiliteBurnRatePage` passe à l'état **`FIRING`** (vérifiez aussi qu'elle apparaît dans Alertmanager, `http://127.0.0.1:9093`) ;
   - après la fin de l'injection, laquelle des deux courbes redescend en premier, et quand l'alerte redevient `inactive`.
5. **Avant de lancer `make check-lab1b`** : assurez-vous qu'aucune injection n'est active (bouton **`Rétablir (0 %)`**), car `make check-lab1b` déclenche lui-même sa propre injection d'erreurs pour vérifier votre alerte.

## Vérifier votre réussite (Checkpoint 1)

Le paramètre `PIN` n'est pas choisi par votre groupe : c'est le code de présence à 4 caractères que l'enseignant écrit au tableau en fin de séance (le système de correction refuse tout autre code).

Exécutez la vérification automatique du Checkpoint 1 avec ce code PIN et votre numéro étudiant (celui de la personne qui lance la commande, un seul numéro ; chacun lance au moins un checkpoint sur les quatre — remplacez `ABCD` par le code écrit au tableau) :

```bash
make check-lab1b PIN=ABCD ETU=20260001
```

Ce qui n'est pas terminé en séance se termine chez vous : le checkpoint se valide jusqu'au début de la journée de cours suivante.

La commande vérifie vos *recording rules*, les propriétés de votre alerte `OrionSLODisponibiliteBurnRatePage` et son déclenchement réel sous injection d'erreurs, puis affiche votre **jeton `ORION-CK1-...`**.
Ajoutez ce jeton à la fin du fichier `jetons/ckn.txt`, puis enregistrez et poussez votre travail :
```bash
git add jetons/ckn.txt
git commit -m "Validation checkpoint 1"
git push
```

## Pour aller plus loin

- Ajoutez une seconde alerte de disponibilité de niveau `ticket` (`burn rate` de facteur 3 sur une fenêtre plus longue) et vérifiez dans Alertmanager comment les labels `severity: page` et `severity: ticket` peuvent être routés vers des récepteurs distincts.
- Testez l'effet de `clamp_min(..., 1e-9)` au dénominateur de vos ratios d'erreurs lorsque le trafic tombe à zéro (`docker compose -f compose/docker-compose.yml stop k6`), et observez comment `OrionAbsenceDeTraficPage` prend le relais.

Fin de séance : make down arrête la pile en conservant vos données ; make start-lab1b la relance.
