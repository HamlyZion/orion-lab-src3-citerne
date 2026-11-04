# Lab 3 — Tracing distribué OpenTelemetry, conventions GenAI et corrélation des trois signaux

- **Durée** : 62 minutes en séance (15, 20, 10 et 17 minutes pour les étapes 1 à 4)
- **Séance** : 5 (Tracing distribué, conventions sémantiques GenAI et corrélation)
- **Code de session console** : `PX5KG49K8T`
- **Checkpoint évalué** : Checkpoint 3 (`make check-lab3 PIN=<votre_pin> ETU=<votre_numero_etudiant>`)
- **Dépôt de travail** : votre dépôt de trinôme, créé une seule fois à la séance 1 (README, §1 : `git clone https://github.com/jassouline/orion-lab.git`, puis `upstream` et `origin`). `make start-lab3` remet l'état d'exécution à zéro sans toucher à vos fichiers.

## Objectifs

À l'issue de ce lab, vous saurez :

1. Activer l'auto-instrumentation OpenTelemetry sur `rag` et `worker` dans `compose/docker-compose.yml` sans modifier le code des services, et normaliser les attributs de ressource (`service.name`, `service.version`, `deployment.environment`).
2. Compléter le module de span métier `span-metier/span_metier.py` pour instrumenter la recherche vectorielle d'Orion avec les attributs métier RAG et les conventions sémantiques OpenTelemetry `gen_ai.*`.
3. Naviguer entre métriques (exemplars Prometheus), journaux (métadonnée `trace_id` dans Loki) et traces distribuées (Tempo) pour isoler l'étape responsable d'une dégradation de performance.

## Ce qui est fourni

- Le service `gateway`, déjà instrumenté en OpenTelemetry et exportant ses traces en OTLP vers Alloy (`http://alloy:4317`), qui les transmet à Tempo (`http://tempo:3200`).
- Le reverse-proxy `traefik`, configuré pour propager l'en-tête W3C `traceparent` et émettre le span d'entrée.
- Le fichier `compose/docker-compose.yml` avec les emplacements `# TODO(lab-3)` sur les services `rag` et `worker`.
- Le module à compléter `span-metier/span_metier.py`, monté dans le conteneur `rag` sous `/opt/orion/span-metier/span_metier.py` et rechargé à chaud à chaque requête `/ask`.
- Les sources de données Grafana pré-provisionnées avec les liens croisés :
  - **Prometheus -> Tempo** via les *exemplars* (`trace_id`) sur `gateway_request_duration_seconds_bucket` ;
  - **Tempo -> Loki** (*Traces to Logs*) via `{service=~".+"} | trace_id="${__trace.traceId}"` ;
  - **Loki -> Tempo** via le champ dérivé `trace_id`.

> **Repartir d'un fichier d'origine** : `make start-lab3` ne remplace aucun de vos fichiers. Pour restaurer la version d'origine d'un fichier depuis le dépôt modèle :
> ```bash
> git checkout upstream/main -- <chemin/du/fichier>
> ```

> **Questions** : chaque étape commence par des questions à préparer **avant** de manipuler. Notez vos réponses dans les notes de votre trinôme, puis vérifiez-les pendant l'étape (non relevées ; elles servent au débrief).

## Étapes à réaliser

### Étape 1 — Auto-instrumentation et contexte W3C sur `rag` et `worker` (15 min)

> **Questions avant de manipuler**
> - **Q1.** Au départ, seuls `traefik` et `gateway` produisent des spans. À quoi ressemblera la trace d'une requête `/ask`, et qu'y manquera-t-il ?
> - **Q2.** Comment `opentelemetry-instrument` peut-il produire des spans pour `rag` sans que l'on modifie son code ?
> - **Q3.** À quoi servent les attributs de ressource `service.version` et `deployment.environment`, et en quoi diffèrent-ils d'un attribut posé sur un seul span ?

1. Démarrez l'état d'exécution du lab 3 :
   ```bash
   make start-lab3
   ```
2. Dans Grafana Explore (`http://127.0.0.1:3000/explore`, source **Tempo**), observez les traces existantes :
   - choisissez l'onglet **Search** (sous *Query type*), laissez les filtres vides, puis cliquez sur **Run query** (bouton bleu en haut à droite) ;
   - dans la liste, les traces `POST` de `traefik` (de l'ordre d'une seconde) sont les requêtes `/ask` du générateur de trafic ; les `GET` d'une milliseconde sont les sondes de santé ; les traces `GET /metrics` de `gateway` viennent de Prometheus, qui collecte ses métriques ;
   - cliquez sur l'identifiant d'une trace `POST` : l'arbre des spans s'ouvre à droite.

   Constatez que seuls `traefik` et `gateway` apparaissent pour l'instant : les spans de `gateway` sont rattachés directement à Traefik, sans aucun span de `rag` entre les deux.
3. Ouvrez `compose/docker-compose.yml` et complétez les marqueurs `# TODO(lab-3)` sur les services `rag` et `worker` :
   - sur `rag` : surchargez `command` pour lancer `uvicorn` via `opentelemetry-instrument` :
     ```yaml
     command: ["opentelemetry-instrument", "uvicorn", "src.rag.app:app", "--host", "0.0.0.0", "--port", "8000"]
     ```
     et ajoutez la variable d'environnement `OTEL_RESOURCE_ATTRIBUTES` définissant `service.version=1.4.1,deployment.environment=lab` ;
   - sur `worker` : activez `OTEL_EXPORTER_OTLP_ENDPOINT: http://alloy:4317`, définissez `OTEL_RESOURCE_ATTRIBUTES: service.version=1.4.1,deployment.environment=lab`, et surchargez `command` avec `opentelemetry-instrument` :
     ```yaml
     command: ["opentelemetry-instrument", "python", "-m", "src.worker.app"]
     ```
4. Appliquez vos modifications Compose :
   ```bash
   make up
   ```
5. Envoyez une requête du corpus sur `https://127.0.0.1:8443/ask` :
   ```bash
   set -a && . ./.env && set +a
   curl --cacert config/traefik/certs/ca.crt -sS \
     -w '%{stderr}HTTP %{http_code}\n' \
     -H "Authorization: Bearer ${ORION_KEY_SUPPORT}" \
     -H "Content-Type: application/json" \
     -d '{"question": "Quel port UDP et quelle adresse de passerelle sont utilisés par le concentrateur VPN WireGuard de Lyon ?"}' \
     https://127.0.0.1:8443/ask | python3 -m json.tool --no-ensure-ascii
   ```
   Un code `429` signale le quota de l'équipe `support` : attendez la fenêtre suivante (5 min au plus) puis relancez la commande.
   Relevez la valeur du champ `"trace_id"`, à la fin de l'objet JSON retourné par `/ask` (après `"answer"` et `"sources"`), puis inspectez cette trace dans Grafana Explore (`http://127.0.0.1:3000/explore`, source **Tempo**) : onglet **TraceQL**, collez l'identifiant seul dans le champ de requête, puis **Run query**. L'arbre peut mettre plusieurs secondes à s'afficher. Les spans de `rag` arrivent dans Tempo 5 à 10 s après la requête ; si la trace paraît incomplète, attendez quelques secondes et relancez **Run query** :
   - dans Tempo, `rag` apparaît sous le nom de service `orion-rag`, `gateway` sous `gateway`, `worker` sous `worker` (et `traefik` sous `traefik`) ;
   - vérifiez la continuité de l'arbre de spans de `traefik` à `orion-rag`, de `orion-rag` à `gateway` (`POST /v1/embeddings` et `POST /v1/chat/completions`) et jusqu'aux requêtes SQL vers PostgreSQL ;
   - vérifiez la présence des attributs de ressource `service.name` et `service.version`, ainsi que `deployment.environment` (qui n'est posé que sur `rag` / `orion-rag` et `worker`) : cliquez sur un span de `orion-rag`, puis dépliez la section **Resource attributes** ;
   - pour le `worker`, revenez à l'onglet **Search**, choisissez `worker` dans **Service Name**, puis **Run query** : une trace `worker.index_cycle` arrive environ une fois par minute. Le `worker` produit aussi des traces SQL courtes (`SELECT`, `CREATE`) : ignorez-les.

### Étape 2 — Span métier RAG et conventions sémantiques `gen_ai.*` (20 min)

> **Questions avant de manipuler**
> - **Q4.** Que voit l'auto-instrumentation de la recherche de passages, et que ne sait-elle pas en dire ?
> - **Q5.** Une fois votre span `rag.retrieval` ouvert, la requête SQL de la recherche deviendra son enfant dans la trace. Pourquoi ?
> - **Q6.** Pourquoi utiliser des noms imposés comme `gen_ai.request.model`, plutôt que des noms choisis par chaque équipe ?

**Pourquoi cette étape.** L'auto-instrumentation de l'étape 1 voit la plomberie : la requête HTTP reçue par `rag`, ses appels à la gateway, sa requête SQL. Elle ne sait rien du métier d'Orion : pour quelle équipe on cherche, combien de passages on demande et on trouve, à quelle distance est le meilleur, avec quel modèle d'embedding. `rag` connaît ces informations, mais il lui faut un span où les écrire : c'est le span métier `rag.retrieval`, que vous allez créer.

1. **Avant de modifier : constatez ce qui manque.** Ouvrez dans Tempo la trace de l'étape 1.5 (ou envoyez une nouvelle requête `/ask` et ouvrez sa trace) :
   - sous `orion-rag` › `POST /ask`, repérez le span `SELECT` : il est rattaché directement à `POST /ask`, sans aucune étape « recherche » autour de lui ;
   - cliquez sur ce span et lisez ses attributs : ils ne parlent que de SQL (`db.system`, `db.statement`, `db.user`…). Rien ne dit pour quelle équipe la recherche a été faite, combien de passages ont été trouvés, ni à quelle distance.

   Notez ce que vous voyez : vous le comparerez à l'étape 2.5.
2. Ouvrez `span-metier/span_metier.py`. Ce module est appelé par `rag` à chaque requête `/ask` sous la forme :
   ```python
   with span_mod.retrieval_span(team=team, top_k=top_k) as custom_span:
       ...
   ```
   Pour l'instant, `retrieval_span` ne crée aucun span : elle cède `None` (`yield None`), et `rag` n'a nulle part où écrire ses informations. Lorsque `retrieval_span` cédera un span OpenTelemetry actif (`yield span`), `rag` y attachera automatiquement :
   - `orion.team` ;
   - `rag.top_k` ;
   - `rag.docs_found` ;
   - `rag.top_distance`.
3. Réécrivez le corps de `retrieval_span(team: str, top_k: int)` :
   - **supprimez d'abord les lignes actuelles du corps** : le commentaire `# TODO(lab-3)`, puis `_ = (trace, team, top_k)` et `yield None`. Elles ne servent qu'à rendre le fichier valide en attendant votre code. Gardez le décorateur `@contextmanager`, la ligne `def` et la docstring ;
   - ouvrez un span nommé `"rag.retrieval"` avec `trace.get_tracer("orion.rag.metier").start_as_current_span("rag.retrieval")`, utilisé comme gestionnaire de contexte (`with ... as span:`) pour que le span se ferme à la fin du bloc appelant ;
   - positionnez sur ce span, avec `span.set_attribute(<clé>, <valeur>)`, les attributs des conventions sémantiques OpenTelemetry GenAI :
     - `gen_ai.operation.name = "retrieval"` ;
     - `gen_ai.provider.name = "orion"` ;
     - `gen_ai.request.model = "nomic-embed-text:v1.5"` ;
   - cédez le span (`yield span`) au bloc appelant, **à l'intérieur** du bloc `with` : en dehors, le span serait déjà fermé quand `rag` y écrit.

   Une fois réécrite, la fonction a cette forme (complétez les deux attributs manquants) :
   ```python
   @contextmanager
   def retrieval_span(team: str, top_k: int) -> Iterator[Any]:
       """...la docstring d'origine..."""
       with trace.get_tracer("orion.rag.metier").start_as_current_span("rag.retrieval") as span:
           span.set_attribute("gen_ai.operation.name", "retrieval")
           # ... les deux autres attributs gen_ai.* ...
           yield span
   ```
   > Comme `span_metier.py` est rechargé dynamiquement à chaque requête `/ask`, vous n'avez même pas besoin de redémarrer le conteneur `rag` après avoir enregistré le fichier.
   >
   > **Si le span n'apparaît pas ou si `/ask` répond `HTTP 500`** :
   > - un module qui ne se charge pas (erreur de syntaxe, par exemple) est ignoré en silence par `rag` : `/ask` répond normalement, mais aucun span `rag.retrieval` n'est créé. Vérifiez la syntaxe du fichier :
   >   ```bash
   >   python3 -m py_compile span-metier/span_metier.py && echo "syntaxe correcte"
   >   ```
   > - un module qui lève une exception pendant la requête fait échouer **toutes** les requêtes `/ask` en `HTTP 500`. C'est le cas si `yield None` est resté dans la fonction à côté de votre `yield span` : les journaux disent alors `generator didn't stop`. Le message d'erreur, qui cite `span_metier.py` et la ligne fautive, se lit dans les journaux de `rag` :
   >   ```bash
   >   docker compose -f compose/docker-compose.yml logs --since 2m rag | grep -B 8 Error
   >   ```
   >
   > En cas de doute, repartez du fichier d'origine avec `git checkout upstream/main -- span-metier/span_metier.py`.
4. Envoyez une nouvelle requête sur `https://127.0.0.1:8443/ask` :
   ```bash
   set -a && . ./.env && set +a
   curl --cacert config/traefik/certs/ca.crt -sS \
     -w '%{stderr}HTTP %{http_code}\n' \
     -H "Authorization: Bearer ${ORION_KEY_SUPPORT}" \
     -H "Content-Type: application/json" \
     -d '{"question": "Quel port UDP et quelle adresse de passerelle sont utilisés par le concentrateur VPN WireGuard de Lyon ?"}' \
     https://127.0.0.1:8443/ask | python3 -m json.tool --no-ensure-ascii
   ```
   Relevez la valeur du champ `"trace_id"` à la fin de l'objet JSON de la réponse et inspectez la trace correspondante dans Tempo (`http://127.0.0.1:3000/explore`, onglet **TraceQL**, identifiant collé seul, puis **Run query**). Les spans de `rag` arrivent dans Tempo 5 à 10 s après la requête ; si la trace paraît incomplète, attendez quelques secondes et relancez **Run query** :
   - vérifiez que le span `rag.retrieval` (sous `orion-rag`) apparaît bien autour de la requête SQL vers PostgreSQL, avec les attributs `rag.top_k`, `rag.docs_found`, `rag.top_distance`, `orion.team`, `gen_ai.operation.name`, `gen_ai.provider.name` et `gen_ai.request.model` (notez sa durée en régime nominal) ;
   - inspectez également le span `inference` émis par `gateway` dans la même trace et repérez les attributs `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.usage.input_tokens` et `gen_ai.usage.output_tokens`.
5. **Comparez avec ce que vous aviez noté à l'étape 2.1** : quelles informations la trace donne-t-elle maintenant, qu'elle ne donnait pas ? Où se trouve désormais le span `SELECT`, et que mesure la durée de `rag.retrieval` ?

### Étape 3 — Corrélation Prometheus <-> Tempo <-> Loki (10 min)

> **Questions avant de manipuler**
> - **Q7.** Qu'est-ce qu'un *exemplar* sur une courbe Prometheus, et que permet-il de faire ?
> - **Q8.** Sur quel identifiant reposent les liens entre une métrique, une trace et des lignes de log ?
> - **Q9.** Pourquoi le passage de Tempo vers Loki dépend-il de votre travail du lab 2a ?

1. Dans Grafana Explore (`http://127.0.0.1:3000/explore`), sélectionnez la source de données **Prometheus** et exécutez la requête :
   ```promql
   histogram_quantile(0.95, sum by (le) (rate(gateway_request_duration_seconds_bucket[5m])))
   ```
   Dépliez d'un clic la barre **Options** située juste sous le champ de requête PromQL, activez l'interrupteur **Exemplars**, puis relancez **Run query** : des points apparaissent autour de la courbe. Survolez un point : l'infobulle affiche son `trace_id` et le bouton **Query with Tempo**, qui ouvre la trace correspondante dans **Tempo**. Les points les plus hauts (environ 2,4 s sur `/v1/embeddings`) viennent des cycles du `worker` ; préférez un point de `/v1/chat/completions` pour retrouver une requête `/ask`.
2. Depuis un span de cette trace dans **Tempo**, utilisez le lien **Logs for this span** (*Traces to Logs*) pour basculer dans **Loki** sur les lignes de journaux partageant le même `trace_id`.
   > Ce lien lance `{service=~".+"} | trace_id="<trace_id>"` : il suppose votre pipeline Alloy du lab 2a (label `service`, `trace_id` en métadonnée structurée). Si Loki ne renvoie aucune ligne, vérifiez `config/alloy/config.alloy` ; en attendant, cherchez le texte de l'identifiant avec `{service=~".+"} |= "<trace_id>"`.
3. Inversement, depuis une ligne de log dans **Loki**, utilisez le lien dérivé **Voir la trace dans Tempo** pour revenir à l'arbre de spans.

### Étape 4 — Prédiction, diagnostic et rétablissement d'une dégradation par les traces (17 min)

> **Question avant de manipuler**
> - **Q10.** Quand une requête ralentit, pourquoi ne suffit-il pas de chercher le span le plus long de sa trace ? À quoi faut-il la comparer ?

1. Ouvrez la console étudiante sur `http://127.0.0.1:8088`. Dans la partie **1. Code de session et rôles d'équipe**, saisissez le code :
   ```text
   PX5KG49K8T
   ```
   ainsi que les prénoms des trois rôles obligatoires (**IC**, **Mitigator**, **Investigator** — seul, saisissez votre prénom dans les trois rôles) **avant** de cliquer sur **« Ouvrir la session »**.
2. L'ouverture de la session déclenche immédiatement la dégradation de performance ; il n'y a pas d'autre bouton. Juste après l'ouverture, avant d'interroger Orion ou d'ouvrir Grafana, enregistrez votre prédiction dans la partie 2 : comment distinguerez-vous dans une trace distribuée un ralentissement provenant de la génération LLM (`gateway` / backend LLM) d'un ralentissement provenant d'une autre étape du pipeline RAG ? Écrivez votre réponse dans le champ **Hypothèse et comportement attendu du SLI**, et dans **Requête ou métrique surveillée** le span ou la requête (TraceQL ou PromQL) que vous comptez regarder, puis cliquez sur **Enregistrer la prédiction**. Une requête TraceQL décrit entre accolades les spans recherchés, par exemple `{ name = "<nom du span>" && duration > 100ms }`.
3. Une fois l'injection active, envoyez une requête sur `https://127.0.0.1:8443/ask` :
   ```bash
   set -a && . ./.env && set +a
   curl --cacert config/traefik/certs/ca.crt -sS \
     -w '%{stderr}HTTP %{http_code}\n' \
     -H "Authorization: Bearer ${ORION_KEY_SUPPORT}" \
     -H "Content-Type: application/json" \
     -d '{"question": "Quel port UDP et quelle adresse de passerelle sont utilisés par le concentrateur VPN WireGuard de Lyon ?"}' \
     https://127.0.0.1:8443/ask | python3 -m json.tool --no-ensure-ascii
   ```
   Relevez la valeur du champ `"trace_id"` à la racine de la réponse JSON, ouvrez cette trace dans Tempo (`http://127.0.0.1:3000/explore`) et comparez votre prédiction aux durées observées sur chaque span :
   - même sous l'incident, la génération LLM reste plus longue que la recherche documentaire : identifiez quel span (et sur quel service) voit sa durée multipliée par rapport à la trace de l'étape 2.3 ;
   - croisez cette observation dans Prometheus (`http://127.0.0.1:9090` ou Grafana Explore) avec `rag_stage_duration_seconds` (par `stage`) et les compteurs `pg_stat_user_tables_*` de `postgres_exporter` pour confirmer votre diagnostic. Affichez chaque requête en courbe sur les 15 dernières minutes, pour comparer avant et après l'ouverture de la session :
     ```promql
     # Latence p95 de chaque étape du pipeline RAG
     histogram_quantile(0.95, sum by (le, stage) (rate(rag_stage_duration_seconds_bucket[2m])))
     # Parcours séquentiels et lignes lues séquentiellement, par table
     sum by (relname) (rate(pg_stat_user_tables_seq_scan[2m]))
     sum by (relname) (rate(pg_stat_user_tables_seq_tup_read[2m]))
     ```
4. **Rétablissez le service, comme au game day.** Dans la console (`http://127.0.0.1:8088`), partie 3 :
   - déclarez l'incident (symptôme observé, sévérité) ;
   - ajoutez une observation qui décrit ce que vous avez trouvé, avec sa requête de preuve (TraceQL ou PromQL, par exemple l'une de l'étape 4.3).

   La console exige au moins une observation avant tout levier. Partie 4 : choisissez la catégorie de levier et la cible qui corrigent la cause trouvée, puis cliquez sur **Exécuter le levier**.
5. **Vérifiez le rétablissement par les traces.** Renvoyez la requête `/ask` de l'étape 4.3 et ouvrez sa trace : le span que vous avez mis en cause doit retrouver sa durée de l'étape 2. Si rien ne change, le levier choisi ne corrigeait pas la cause : relisez votre diagnostic et essayez-en un autre.
6. Cliquez sur **« Clôturer l'incident et générer l'archive »** (partie 6) avant de lancer la vérification finale du Checkpoint 3. La clôture remet aussi Orion dans son état de départ.

## Vérifier votre réussite (Checkpoint 3)

Le paramètre `PIN` n'est pas choisi par votre groupe : c'est le code de présence à 4 caractères que l'enseignant écrit au tableau en fin de séance (le système de correction refuse tout autre code).

Exécutez la vérification automatique du Checkpoint 3 avec ce code PIN et votre numéro étudiant (celui de la personne qui lance la commande, un seul numéro ; chacun lance au moins un checkpoint sur les quatre — remplacez `ABCD` par le code écrit au tableau) :

```bash
make check-lab3 PIN=ABCD ETU=20260001
```

Ce qui n'est pas terminé en séance se termine chez vous : le checkpoint se valide jusqu'au début de la journée de cours suivante.

La commande envoie une requête de test à travers Traefik et vérifie dans Tempo, **sur la trace de cette requête uniquement** (une trace correcte plus ancienne ne compte pas) :
- la présence des trois services de la requête dans la même trace (`traefik`, `orion-rag` pour `rag`, et `gateway`) et la continuité parent-enfant des spans ;
- la présence des attributs de ressource `service.name` et `service.version`, ainsi que `deployment.environment` (posé uniquement sur `rag` / `orion-rag` et `worker`, pas sur `traefik` ni `gateway`), et une trace `worker` de moins de 3 minutes portant ces mêmes attributs (le `worker` émet une trace `worker.index_cycle` par minute environ : juste après un `make up`, ce critère peut attendre jusqu'à 70 s) ;
- la présence du span métier `rag.retrieval` et de ses attributs `rag.top_k`, `rag.docs_found`, `rag.top_distance` ;
- la présence des attributs `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.usage.input_tokens` et `gen_ai.usage.output_tokens` sur la trace ;

puis affiche votre **jeton `ORION-CK3-...`**.
Ajoutez ce jeton à la fin du fichier `jetons/ckn.txt`, puis enregistrez et poussez votre travail :
```bash
git add jetons/ckn.txt
git commit -m "Validation checkpoint 3"
git push
```

## Pour aller plus loin

- Utilisez TraceQL dans Grafana Explore (`http://127.0.0.1:3000/explore`, source **Tempo**) pour rechercher uniquement les traces vérifiant un critère en marche normale, par exemple `{ span.rag.top_distance > 0.25 }` ou `{ span.gen_ai.usage.output_tokens > 20 }`.
- Observez dans Tempo les traces périodiques `worker.index_cycle` émises par le `worker` et suivez la propagation de `traceparent` entre `worker` et `POST /v1/embeddings` sur `gateway`.

Fin de séance : make down arrête la pile en conservant vos données ; make start-lab3 la relance.
