# Lab 2b — LogQL avancé, fraîcheur d'indexation et détection d'échec silencieux

- **Durée** : 57 minutes pour les étapes 1 à 4 ; l'étape 5 et le checkpoint peuvent se terminer chez vous
- **Séance** : 4 (Exploitation des journaux et pannes silencieuses de pipelines de données)
- **Code de session console** : `7CZXUBBZ66`
- **Checkpoint évalué** : Checkpoint 2 (`make check-lab2b PIN=<code écrit au tableau> ETU=<votre_numero_etudiant>`)
- **Dépôt de travail** : votre dépôt de trinôme, créé une seule fois à la séance 1 (README, §1 : `git clone https://github.com/jassouline/orion-lab.git`, puis `upstream` et `origin`). `make start-lab2b` remet l'état d'exécution à zéro sans toucher à vos fichiers.

> **Ce qui est noté** : le checkpoint 2 compte pour 7,5 % de la note, au niveau du trinôme, validé ou non. Il vérifie votre pipeline Alloy du lab 2a (4 points) et l'alerte de fraîcheur que vous écrivez ici (étape 2), qui doit s'être déclenchée pendant l'incident (étape 4). La preuve de validation est un jeton chiffré que vous poussez dans votre dépôt (voir « Vérifier votre réussite »). Validé en séance ou chez vous avant le début de la journée de cours suivante, il compte entièrement.

## Objectifs

À l'issue de ce lab, vous saurez :

1. Écrire des requêtes LogQL d'extraction et d'agrégation (`| json`, `unwrap`, `sum_over_time`, `quantile_over_time`) sur les journaux structurés d'Orion.
2. Concevoir et justifier une alerte Prometheus (`OrionWorkerFraicheurIndexationTicket`) qui détecte l'arrêt de progression de l'indexation documentaire du `worker`.
3. Diagnostiquer, après prédiction, pourquoi une mise à jour documentaire publiée dans le corpus n'est pas servie par l'assistant alors qu'aucune erreur HTTP ni aucun log de niveau `ERROR` n'apparaît, puis rétablir le service.

## Ce qui est fourni

- Votre pipeline Alloy configuré au lab 2a dans `config/alloy/config.alloy`.
- Le fichier `config/prometheus/rules.yml` comportant un marqueur `# TODO(lab-2b)` à la fin du groupe `orion_slo_alerts`. La règle à écrire n'y figure pas encore.
- Le service `worker`, qui exécute périodiquement un cycle d'indexation documentaire et expose ses métriques sur `/metrics` (collectées par Prometheus sous `job="worker"`).

> **Repartir d'un fichier d'origine** : `make start-lab2b` conserve vos fichiers de configuration tels quels. Pour restaurer un fichier depuis le dépôt modèle si nécessaire :
> ```bash
> git checkout upstream/main -- <chemin/du/fichier>
> ```

> **Questions** : chaque étape commence par des questions à préparer **avant** de manipuler. Notez vos réponses dans les notes de votre trinôme, puis vérifiez-les pendant l'étape (non relevées ; elles servent à l'oral et au débrief).

## Étapes à réaliser

### Étape 1 — Requêtes LogQL d'analyse et d'agrégation (15 min)

> **Questions avant de manipuler**
> - **Q1.** Seul le service `rag` journalise le champ `latency_ms`. Que doit faire `unwrap latency_ms` d'une ligne qui n'a pas ce champ, ou dont la valeur n'est pas un nombre ? À quoi sert alors le filtre `| __error__=""` ?
> - **Q2.** Quels champs d'une ligne JSON du `worker` s'attend-on à trouver pour décrire le résultat d'un cycle d'indexation ?

1. Initialisez l'état d'exécution du lab 2b :
   ```bash
   make start-lab2b
   ```
2. Dans Grafana Explore (`http://127.0.0.1:3000/explore`, source **Loki**), écrivez et testez les requêtes suivantes. **Lancez chaque requête seule** (remplacez la précédente plutôt que d'en ajouter une) : elles n'ont pas la même unité, et sur un même graphique les petites valeurs sont écrasées contre l'axe.
   - **Requête modèle**, à recopier : le taux de lignes de journaux par service et par niveau sur 5 minutes.
     ```logql
     sum by (service, level) (rate({service=~".+"} | json [5m]))
     ```
     Résultat attendu : une série par couple (service, niveau), en lignes par seconde, d'environ 1 pour `gateway` à environ 0,02 pour le `worker`.
   - **À écrire** : le 95e centile de `latency_ms` par équipe, sur 5 minutes. Construisez la requête dans cet ordre :
     1. partez du flux de `rag` ;
     2. décodez le JSON avec `| json` ;
     3. transformez le champ en valeur numérique avec `| unwrap latency_ms` ;
     4. écartez les lignes en erreur avec `| __error__=""` ;
     5. appliquez `quantile_over_time(0.95, ... [5m])` ;
     6. avec cette fonction, placez la clause `by (team)` **après** la parenthèse fermante.

     Résultat attendu : une série par équipe (`support`, `rh`, `dev`), en millisecondes : de l'ordre de 1 000 à 2 000 sur un Mac ou en mode `LOW_MEM=1`, nettement plus si Ollama tourne sur le processeur.
   - **À écrire** : le nombre total de passages indexés par le `worker` sur 10 minutes, à partir de son champ `docs_processed`. Même principe, avec `sum_over_time(... [10m])` à la place de `quantile_over_time`, et le tout entouré de `sum(...)` pour obtenir un seul total. Résultat attendu : quelques dizaines de passages. Vous reprendrez cette requête à l'étape 4.
   - Affichez les lignes brutes du `worker` (`{service="worker"}`), dépliez-en une, et vérifiez votre réponse à Q2.

   > Tapez les requêtes dans l'éditeur en mode « Code », pas « Builder ». Un résultat vide (« No data ») n'est pas forcément une erreur : il peut simplement n'y avoir aucune ligne qui corresponde. Quand un champ JSON porte le même nom qu'un label (`service`, `team`), Loki l'affiche avec le suffixe `_extracted` : c'est normal.

### Étape 2 — Alerte de fraîcheur d'indexation du worker (20 min)

> **Questions avant de manipuler**
> - **Q3.** Le `worker` publie l'heure de son dernier cycle réussi. Comment transformer cette heure en « âge du dernier succès » ? À quoi ressemblera la courbe de cet âge en marche normale ?
> - **Q4.** Si le seuil de l'alerte valait exactement la période du `worker`, que se passerait-il en marche normale ?

1. Dans Prometheus (`http://127.0.0.1:9090/query`), étudiez les métriques du `worker`. Aucune requête n'est donnée : suivez cette démarche.
   1. Tapez `worker_` dans le champ d'expression : l'autocomplétion liste les métriques exposées par le `worker`, que décrit aussi `docs/architecture.md` (§ 1, étape 4 « Indexation périodique »). Exécutez-les une par une (**Execute**).
   2. Repérez celle qui donne l'heure du dernier cycle réussi : sa valeur est un horodatage Unix, en secondes.
   3. Transformez cet horodatage en âge du dernier succès, en secondes, avec `time()`. Affichez la courbe dans l'onglet **Graph**, sur 15 minutes.
   4. Lisez sur la courbe la période entre deux cycles réussis et l'âge maximal atteint en marche normale.
   5. Relevez dans `config/prometheus/prometheus.yml` l'intervalle de collecte (`scrape_interval`) et l'intervalle d'évaluation des règles (`evaluation_interval`) : chacun retarde l'alerte d'autant.
2. Dans `config/prometheus/rules.yml`, au niveau du marqueur `# TODO(lab-2b)`, écrivez une règle d'alerte répondant à l'objectif suivant :
   - **Objectif** : être alerté lorsque l'indexation documentaire du `worker` ne progresse plus.
   - **Cible** : en cas de blocage, l'alerte passe à `FIRING` **moins de 4 minutes** après le dernier cycle réussi, et ne se déclenche jamais en marche normale.
   - **Nom imposé de l'alerte** (requis par le checkpoint) : `OrionWorkerFraicheurIndexationTicket`.
   - **Labels requis par le checkpoint** : `severity: ticket` et `service: orion-worker`.
   - **Justification attendue**, en commentaire YAML (`# ...`) juste au-dessus de la règle :
     - la période et l'âge maximal mesurés ;
     - le nombre de cycles manqués que votre seuil tolère ;
     - votre durée de confirmation `for` ;
     - le calcul du pire délai (seuil + `for` + collecte + évaluation) comparé à la cible.
3. Vérifiez la syntaxe avec `promtool check rules` et rechargez Prometheus :
   ```bash
   docker compose -f compose/docker-compose.yml exec -T prometheus \
     promtool check rules /etc/prometheus/rules.yml
   curl -fsS -X POST http://127.0.0.1:9090/-/reload
   ```
   Si la règle n'apparaît pas après le rechargement, votre éditeur a sans doute remplacé le fichier au lieu de le modifier, et Prometheus lit encore l'ancien. Redémarrez-le : `docker compose -f compose/docker-compose.yml restart prometheus`.
4. Vérifiez sur `http://127.0.0.1:9090/rules` que la règle `OrionWorkerFraicheurIndexationTicket` est bien chargée (santé `OK`), puis sur `http://127.0.0.1:9090/alerts` qu'elle est à l'état `Inactive` en marche normale.

### Étape 3 — Prédiction et publication d'une mise à jour documentaire (10 min)

> **Ce qui se passe quand Nordel publie une procédure**
> - Les procédures sont des fichiers du corpus documentaire. Publier une nouvelle version revient à remplacer le fichier.
> - À chaque cycle, environ une fois par minute, le `worker` relit le corpus. Il calcule les embeddings des passages modifiés via la `gateway` et les écrit dans la base vectorielle (PostgreSQL avec `pgvector`). Voir `docs/architecture.md`, § 1, étape 4 « Indexation périodique ».
> - `rag` ne lit que cette base. Tant que le `worker` n'a pas réindexé un document, `/ask` répond avec l'ancienne version.
>
> **Ce que fait l'ouverture de la session `7CZXUBBZ66`**
> - Elle publie la version 2.0 de `DOC-SUP-003` : délai maximal de prise en charge ramené à **15 minutes**, escalade par le **poste interne 4800**.
> - Elle lance une sonde de qualité : toutes les 12 secondes, la sonde pose à Orion la question de référence sur `DOC-SUP-003` et compare la réponse à la version 2.0. Si Orion ne sert pas la version 2.0, cette sonde fait monter l'alerte `OrionSLOQualiteTicket`.

> **Question avant de manipuler**
> - **Q5.** Une fois la version 2.0 publiée, en combien de temps devrait-elle apparaître dans les réponses de `/ask`, et pourquoi ?

1. Avant toute ouverture de session, interrogez Orion sur la procédure `DOC-SUP-003` (« Procédure d'astreinte N2 et escalade d'un incident nocturne ») et notez les éléments factuels de la réponse (délai, poste) :
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
2. Ouvrez la console étudiante sur `http://127.0.0.1:8088` et démarrez la session du lab 2b avec le code :
   ```text
   7CZXUBBZ66
   ```
   Seul, saisissez votre prénom dans les trois rôles.
3. L'ouverture de la session publie immédiatement la version 2.0 de `DOC-SUP-003` ; il n'y a pas d'autre bouton. Juste après l'ouverture, avant d'interroger Orion ou d'ouvrir Grafana, enregistrez votre prédiction dans la partie 2 :
   - **Hypothèse et comportement attendu du SLI** : comment allez-vous vérifier qu'Orion sert bien la version 2.0, et quels signaux (métriques, alertes, journaux) surveillerez-vous si ce n'est pas le cas ?
   - **Requête ou métrique surveillée** : la requête que vous regarderez en premier.

   Cliquez ensuite sur **Enregistrer la prédiction**.

### Étape 4 — Vérification et diagnostic par les logs et les métriques (12 min)

> **Questions avant de manipuler**
> - **Q6.** Une recherche des lignes de niveau `ERROR` du `worker` suffit-elle à détecter toutes les pannes d'indexation ? Dans quel cas ne verrait-elle rien ?
> - **Q7.** Si la version 2.0 n'est pas servie, quelles métriques du `worker` vont changer de comportement, et comment ?

1. Patientez le pire délai calculé à l'étape 2 (4 minutes au plus si votre règle tient la cible). Interrogez ensuite à nouveau `https://127.0.0.1:8443/ask` avec la même commande pour vérifier si Orion sert la version 2.0 de `DOC-SUP-003` (15 minutes, poste 4800) :
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
2. Observez l'état de votre alerte `OrionWorkerFraicheurIndexationTicket` dans Prometheus (`http://127.0.0.1:9090/alerts`) et l'évolution des métriques du `worker` (vos requêtes de l'étape 2). L'alerte `OrionSLOQualiteTicket` s'allume également : c'est la sonde de qualité décrite à l'étape 3.
3. Explorez les journaux dans Loki (`http://127.0.0.1:3000/explore`) :
   - vérifiez si la recherche naïve `{service="worker"} | json | level="ERROR"` suffit à expliquer la situation (Q6) ;
   - reprenez la requête de l'étape 1.2 pour observer l'évolution du nombre de passages indexés :
     ```logql
     sum(sum_over_time({service="worker"} | json | unwrap docs_processed | __error__="" [10m]))
     ```
   - écrivez la requête LogQL qui isole le comportement anormal et identifie la cause exacte, c'est-à-dire le mécanisme observable (composant, comportement à chaque cycle et preuve dans les journaux), pas l'origine interne du lot ignoré. Notez-la : elle sert de preuve à l'étape 5.
4. Attendez que `OrionWorkerFraicheurIndexationTicket` soit à l'état `FIRING` sur `http://127.0.0.1:9090/alerts`. C'est ce déclenchement que vérifie le checkpoint : **n'appliquez aucun levier avant**. Si votre alerte reste `Inactive` alors que le `worker` ne progresse plus, revoyez votre règle (étape 2).

### Étape 5 — Rétablissement du service (8 min, à terminer chez vous si besoin)

> **Questions avant de manipuler**
> - **Q8.** Quel levier du catalogue de la console agit sur la cause trouvée à l'étape 4.3, et sur quel composant ?
> - **Q9.** À quoi verrez-vous que le service est rétabli : dans la réponse de `/ask`, dans vos métriques, dans vos alertes ?

1. Vérifiez que votre alerte est passée à `FIRING` (étape 4.4).
2. Dans la console (`http://127.0.0.1:8088`), partie 3 :
   - déclarez l'incident (symptôme observé, sévérité) ;
   - ajoutez une observation avec votre requête de preuve de l'étape 4.3.

   La console exige au moins une observation avant tout levier.
3. Partie 4 : choisissez la catégorie de levier et la cible qui corrigent la cause (Q8), puis cliquez sur **Exécuter le levier**.
4. Attendez un cycle du `worker`, environ une minute, puis vérifiez votre réponse à Q9 :
   - relancez la commande `/ask` de l'étape 4.1 : Orion doit maintenant citer la version 2.0 (15 minutes, poste 4800) ;
   - sur `http://127.0.0.1:9090/alerts`, votre alerte `OrionWorkerFraicheurIndexationTicket` doit être revenue à `Inactive`.

   Si rien ne change, le levier choisi ne corrigeait pas la cause : relisez votre diagnostic et essayez-en un autre.
5. Lancez le checkpoint (voir « Vérifier votre réussite ») si ce n'est pas déjà fait, puis cliquez sur **Clôturer l'incident et générer l'archive** (partie 6). La clôture remet Orion dans son état de départ : `DOC-SUP-003` repasse en version 1.4. C'est normal, la session simulait la publication.

## Vérifier votre réussite (Checkpoint 2)

**À quoi sert la commande** : `make check-lab2b` interroge votre pile (Loki et Prometheus) et vérifie automatiquement ce que vous avez construit aux labs 2a et 2b. Si tous les points sont `[OK]`, elle affiche un jeton chiffré `ORION-CK2-...` : c'est ce jeton, poussé dans votre dépôt, que l'enseignant relève pour valider le checkpoint.

**Quand la lancer** : après le passage de votre alerte à `FIRING` (étape 4.4), et au plus tard 2 heures après, car la commande cherche ce déclenchement dans l'historique des 2 dernières heures. Le rétablissement de l'étape 5 ne l'empêche pas.

Le paramètre `PIN` n'est pas choisi par votre groupe : c'est le code de présence à 4 caractères que l'enseignant écrit au tableau en fin de séance (le système de correction refuse tout autre code). Sans `PIN` ni `ETU`, la commande refuse de s'exécuter.

Exécutez la vérification avec ce code et votre numéro étudiant (celui de la personne qui lance la commande, un seul numéro ; chacun lance au moins un checkpoint sur les quatre — remplacez `ABCD` par le code écrit au tableau) :

```bash
make check-lab2b PIN=ABCD ETU=20260001
```

Ce qui n'est pas terminé en séance se termine chez vous, jusqu'au début de la journée de cours suivante. À la maison, rouvrez la session `7CZXUBBZ66` dans `http://127.0.0.1:8088`, attendez le passage à l'état `FIRING` de `OrionWorkerFraicheurIndexationTicket`, lancez `make check-lab2b`, puis faites l'étape 5.

La commande vérifie quatre points sur votre pipeline Alloy du lab 2a :
- le respect du budget d'au plus 1 000 flux dans Loki, vérifiable depuis le terminal :
  ```bash
  curl -sG http://127.0.0.1:3000/api/datasources/proxy/uid/loki/loki/api/v1/series --data-urlencode 'match[]={service=~".+"}' | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["data"]))'
  ```
- la validité JSON des journaux collectés ;
- le masquage effectif des données sensibles dans Loki ;
- la possibilité de retrouver une ligne de log à partir de son `trace_id`.

Et un point sur votre alerte du lab 2b :
- `OrionWorkerFraicheurIndexationTicket` est chargée avec ses deux labels, a déclenché (`firing`) au cours des 2 dernières heures, et ne se déclenche pas quand le `worker` fonctionne.

Si un point est `[KO]`, le message dit quoi corriger ; corrigez puis relancez. Si tout est `[OK]`, la commande affiche votre **jeton `ORION-CK2-...`** : il contient votre groupe, votre numéro étudiant, l'heure de validation et le résultat des vérifications, chiffrés pour l'enseignant. Ajoutez-le à la fin du fichier `jetons/ckn.txt`, puis enregistrez et poussez votre travail :
```bash
git add jetons/ckn.txt
git commit -m "Validation checkpoint 2"
git push
```

## Pour aller plus loin

- Ajoutez dans Grafana un panneau combinant sur le même axe temporel la métrique de fraîcheur du `worker` (Prometheus) et le décompte par minute des cycles du `worker` ventilés par issue dans Loki.
- Testez l'opérateur LogQL `| line_format` pour synthétiser en une ligne lisible l'identifiant de cycle, le document traité et la durée d'exécution.

Fin de séance : make down arrête la pile en conservant vos données ; make start-lab2b la relance.
