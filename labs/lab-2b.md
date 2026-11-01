# Lab 2b — LogQL avancé, fraîcheur d'indexation et détection d'échec silencieux

- **Durée** : 85 minutes
- **Séance** : 4 (Exploitation des journaux et pannes silencieuses de pipelines de données)
- **Code de session console** : `7CZXUBBZ66`
- **Checkpoint évalué** : Checkpoint 2 (`make check-lab2b PIN=<votre_pin> ETU=<votre_numero_etudiant>`)
- **Dépôt de travail** : votre dépôt de trinôme, créé une seule fois à la séance 1 (README, §1 : `git clone https://github.com/jassouline/orion-lab.git`, puis `upstream` et `origin`). `make start-lab2b` remet l'état d'exécution à zéro sans toucher à vos fichiers.

## Objectifs

À l'issue de ce lab, vous saurez :

1. Écrire des requêtes LogQL d'extraction et d'agrégation (`| json`, `unwrap`, `sum_over_time`, `quantile_over_time`) sur les journaux structurés d'Orion.
2. Concevoir et justifier une alerte Prometheus (`OrionWorkerFraicheurIndexationTicket`) qui détecte l'arrêt de progression de l'indexation documentaire du `worker`.
3. Diagnostiquer, après prédiction, pourquoi une mise à jour documentaire publiée dans le corpus n'est pas servie par l'assistant alors qu'aucune erreur HTTP ni aucun log de niveau `ERROR` n'apparaît.

## Ce qui est fourni

- Votre pipeline Alloy configuré au lab 2a dans `config/alloy/config.alloy`.
- Le fichier `config/prometheus/rules.yml` comportant un marqueur `# TODO(lab-2b)` à la fin du groupe `orion_slo_alerts`.
- Le service `worker`, qui exécute périodiquement un cycle d'indexation documentaire et expose ses métriques sur `/metrics` (collectées par Prometheus sous `job="worker"`).

> **Repartir d'un fichier d'origine** : `make start-lab2b` conserve vos fichiers de configuration tels quels. Pour restaurer un fichier depuis le dépôt modèle si nécessaire :
> ```bash
> git checkout upstream/main -- <chemin/du/fichier>
> ```

## Étapes à réaliser

### Étape 1 — Requêtes LogQL d'analyse et d'agrégation (20 min)

1. Initialisez l'état d'exécution du lab 2b :
   ```bash
   make start-lab2b
   ```
2. Dans Grafana Explore (`http://127.0.0.1:3000/explore`, source **Loki**), écrivez et testez des requêtes LogQL permettant de :
   - compter le taux de lignes de journaux par service et par niveau sur 5 minutes :
     ```logql
     sum by (service, level) (rate({service=~".+"} | json [5m]))
     ```
   - extraire la latence numérique `latency_ms` (journalisée uniquement par `rag`) et calculer son 95e centile par équipe, avec la clause `by (team)` placée après la parenthèse fermante :
     ```logql
     quantile_over_time(0.95, {service="rag"} | json | unwrap latency_ms | __error__="" [5m]) by (team)
     ```
   - totaliser les passages indexés par le `worker` sur 10 minutes (requête à reprendre à l'étape 4) :
     ```logql
     sum(sum_over_time({service="worker"} | json | unwrap docs_processed | __error__="" [10m]))
     ```
   - observer les cycles du service `worker` dans Loki et identifier quels champs JSON décrivent le résultat de chaque cycle d'indexation.

### Étape 2 — Alerte de fraîcheur d'indexation du worker (25 min)

1. Dans Prometheus (`http://127.0.0.1:9090/query` — tapez la requête dans le champ d'expression, puis Execute ; onglet Graph pour la courbe), inspectez les métriques exposées par le `worker` (préfixe `worker_`) et mesurez la période normale entre deux cycles d'indexation réussis.
2. Dans `config/prometheus/rules.yml`, au niveau du marqueur `# TODO(lab-2b)`, écrivez une règle d'alerte répondant à l'objectif suivant :
   - **Objectif** : être alerté lorsque l'indexation documentaire du `worker` ne progresse plus.
   - **Nom imposé de l'alerte** (requis par le checkpoint) : `OrionWorkerFraicheurIndexationTicket`.
   - **Labels requis** : `severity: ticket` et `service: orion-worker`.
   - **Justification attendue** : choisissez votre seuil et votre éventuelle durée de confirmation en les justifiant à partir de la période nominale du `worker`, afin d'éviter les faux positifs entre deux cycles normaux tout en détectant rapidement un blocage. Écrivez cette justification en commentaire YAML (`# ...`) juste au-dessus de la règle dans `config/prometheus/rules.yml`.
3. Vérifiez la syntaxe avec `promtool check rules` et rechargez Prometheus :
   ```bash
   docker compose -f compose/docker-compose.yml exec -T prometheus \
     promtool check rules /etc/prometheus/rules.yml
   curl -fsS -X POST http://127.0.0.1:9090/-/reload
   ```
4. Vérifiez sur `http://127.0.0.1:9090/rules` que la règle `OrionWorkerFraicheurIndexationTicket` est bien chargée (santé `OK`), puis sur `http://127.0.0.1:9090/alerts` qu'elle est à l'état `Inactive` en marche normale.

### Étape 3 — Prédiction et publication d'une mise à jour documentaire (20 min)

1. Avant toute ouverture de session, interrogez Orion sur la procédure `DOC-SUP-003` (« Procédure d'astreinte N2 et escalade d'un incident nocturne ») et notez les éléments factuels de la réponse :
   ```bash
   set -a && . ./.env && set +a
   curl --cacert config/traefik/certs/ca.crt -sS \
     -w '%{stderr}HTTP %{http_code}\n' \
     -H "Authorization: Bearer ${ORION_KEY_SUPPORT}" \
     -H "Content-Type: application/json" \
     -d "{\"question\": \"Quel est le délai de prise en charge d'une alerte critique par l'ingénieur d'astreinte N2 et quel poste téléphonique permet l'escalade ?\"}" \
     https://127.0.0.1:8443/ask | python3 -m json.tool
   ```
   Un code `429` signale le quota de l'équipe `support` : attendez la fenêtre suivante (5 min au plus) puis relancez la commande.
2. La version 2.0 de « Procédure d'astreinte N2 et escalade d'un incident nocturne » (`DOC-SUP-003`) ramène le délai maximal de prise en charge à **15 minutes** et remplace le numéro d'escalade par le **poste interne 4800**. Ouvrez la console étudiante sur `http://127.0.0.1:8088` et démarrez la session du lab 2b avec le code :
   ```text
   7CZXUBBZ66
   ```
   Seul, saisissez votre prénom dans les trois rôles.
3. L'ouverture de la session publie immédiatement la version 2.0 de `DOC-SUP-003` ; il n'y a pas d'autre bouton. Juste après l'ouverture, avant d'interroger Orion ou d'ouvrir Grafana, enregistrez votre prédiction dans la partie 2 : comment allez-vous vérifier qu'Orion sert bien la version 2.0 et quels signaux (métriques, alertes, journaux) surveillerez-vous si ce n'est pas le cas ?

### Étape 4 — Vérification et diagnostic par les logs et les métriques (20 min)

1. Patientez l'équivalent de `seuil + for + une période` du `worker` (soit **4 à 5 minutes**). Interrogez ensuite à nouveau `https://127.0.0.1:8443/ask` avec la même commande pour vérifier si Orion sert la version 2.0 de `DOC-SUP-003` (15 minutes, poste 4800) :
   ```bash
   set -a && . ./.env && set +a
   curl --cacert config/traefik/certs/ca.crt -sS \
     -w '%{stderr}HTTP %{http_code}\n' \
     -H "Authorization: Bearer ${ORION_KEY_SUPPORT}" \
     -H "Content-Type: application/json" \
     -d "{\"question\": \"Quel est le délai de prise en charge d'une alerte critique par l'ingénieur d'astreinte N2 et quel poste téléphonique permet l'escalade ?\"}" \
     https://127.0.0.1:8443/ask | python3 -m json.tool
   ```
   Un code `429` signale le quota de l'équipe `support` : attendez la fenêtre suivante (5 min au plus) puis relancez la commande.
2. Observez l'état de votre alerte `OrionWorkerFraicheurIndexationTicket` dans Prometheus (`http://127.0.0.1:9090/alerts`) et l'évolution des métriques du `worker`. L'alerte `OrionSLOQualiteTicket` s'allume également pendant l'incident : c'est attendu.
3. Explorez les journaux dans Loki (`http://127.0.0.1:3000/explore`) :
   - vérifiez si la recherche naïve `{service="worker"} | json | level="ERROR"` suffit à expliquer la situation ;
   - reprenez la requête `sum(sum_over_time({service="worker"} | json | unwrap docs_processed | __error__="" [10m]))` de l'étape 1.2 pour observer l'évolution du nombre de passages indexés ;
   - écrivez la requête LogQL qui isole le comportement anormal et identifie la cause exacte, c'est-à-dire le mécanisme observable (composant, comportement à chaque cycle et preuve dans les journaux), pas l'origine interne du lot ignoré.
4. **N'appliquez aucun levier de mitigation et ne clôturez pas l'incident dans la console avant d'avoir lancé `make check-lab2b`** : votre alerte `OrionWorkerFraicheurIndexationTicket` doit rester chargée et avoir déclenché (`firing`) au cours des 2 dernières heures.

## Vérifier votre réussite (Checkpoint 2)

Le paramètre `PIN` n'est pas choisi par votre groupe : c'est le code de présence à 4 caractères que l'enseignant écrit au tableau en fin de séance (le système de correction refuse tout autre code).

Exécutez la vérification automatique du Checkpoint 2 avec ce code PIN et votre numéro étudiant (celui de la personne qui lance la commande, un seul numéro ; chacun lance au moins un checkpoint sur les quatre — remplacez `ABCD` par le code écrit au tableau) :

```bash
make check-lab2b PIN=ABCD ETU=20260001
```

Ce qui n'est pas terminé en séance se termine chez vous : le checkpoint se valide jusqu'au début de la journée de cours suivante. À la maison, rouvrez la session `7CZXUBBZ66` dans `http://127.0.0.1:8088` et attendez le passage à l'état `firing` de `OrionWorkerFraicheurIndexationTicket` avant d'exécuter `make check-lab2b` (sans appliquer de levier ni clôturer avant le check).

La commande vérifie :
- le respect du budget d'au plus 1 000 flux dans Loki, vérifiable depuis le terminal :
  ```bash
  curl -sG http://127.0.0.1:3000/api/datasources/proxy/uid/loki/loki/api/v1/series --data-urlencode 'match[]={service=~".+"}' | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["data"]))'
  ```
- la validité JSON des journaux collectés ;
- le masquage effectif des données sensibles dans Loki ;
- la possibilité de retrouver une ligne de log à partir de son `trace_id` ;
- la présence et le déclenchement (`firing`) de votre alerte `OrionWorkerFraicheurIndexationTicket` pendant la session du lab 2b ;

puis affiche votre **jeton `ORION-CK2-...`**.
Ajoutez ce jeton à la fin du fichier `jetons/ckn.txt`, puis enregistrez et poussez votre travail :
```bash
git add jetons/ckn.txt
git commit -m "Validation checkpoint 2"
git push
```

## Pour aller plus loin

- Ajoutez dans Grafana un panneau combinant sur le même axe temporel la métrique de fraîcheur du `worker` (Prometheus) et le décompte par minute des cycles du `worker` ventilés par issue dans Loki.
- Testez l'opérateur LogQL `| line_format` pour synthétiser en une ligne lisible l'identifiant de cycle, le document traité et la durée d'exécution.

Fin de séance : make down arrête la pile en conservant vos données ; make start-lab2b la relance.
