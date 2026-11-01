# Lab 1a — Anatomie de la stack Orion et premiers signaux

- **Durée** : 40 minutes (séance 1, 14 h 40 - 15 h 20)
- **Séance** : 1 (L'observabilité d'un système IA en production)
- **Code de session console** : `01-ANATOMIE-STACK`
- **Prérequis** : `make check` exécuté avec succès à la racine du dépôt `orion-lab`
- **Dépôt de travail** : votre dépôt de trinôme, créé une seule fois à la séance 1 (README, §1 : `git clone https://github.com/jassouline/orion-lab.git`, puis `upstream` et `origin`). Si ce n'est pas encore fait, commencez par ce §1. `make start-lab1a` remet l'état d'exécution à zéro sans toucher à vos fichiers.

## Objectifs

À l'issue de ce lab, vous saurez :

1. Démarrer la plateforme Orion et vérifier l'état de ses composants applicatifs et d'observabilité.
2. Identifier sur quelles cibles Prometheus collecte les métriques et comment le trafic synthétique `k6` sollicite l'assistant RAG.
3. Distinguer deux pannes aux symptômes opposés en croisant la sonde externe HTTPS, les métriques du reverse-proxy Traefik et celles de l'application.
4. Situer chaque composant d'Orion dans les grilles RED (Rate, Errors, Duration) et USE (Utilization, Saturation, Errors).

## Ce qui est fourni

- La stack Docker Compose complète dans `compose/docker-compose.yml`, accompagnée d'un profil mémoire réduit (`compose/low-mem.yml`) activable avec `LOW_MEM=1`.
- La configuration de collecte Prometheus dans `config/prometheus/prometheus.yml` et un jeu initial de règles dans `config/prometheus/rules.yml`.
- Le tableau de bord Grafana pré-provisionné **Orion Gateway — RED** (`http://localhost:3000`).
- Le générateur de trafic continu `k6` (`k6/load.js`), qui charge la pile avec 36 questions de référence (corpus de test de Nordel) rejouées en boucle selon un profil constant, simulant les requêtes des équipes `support`, `rh` et `dev`. Il ne produit pas les pannes, il maintient un flux régulier pour que les métriques soient observables.
- La documentation d'architecture dans `docs/architecture.md`.

> **Repartir d'un fichier d'origine** : vos fichiers de configuration constituent votre livrable « as code ». Les commandes `make start-lab*` ne les écrasent jamais. Si vous souhaitez repartir de la version d'origine d'un fichier telle que fournie dans `orion-lab`, exécutez :
> ```bash
> git fetch upstream
> git checkout upstream/main -- <chemin/du/fichier>
> ```

## Étapes à réaliser

### Étape 1 — Démarrage de la stack et vérification des cibles (10 min)

1. Démarrez l'environnement du lab 1a :
   ```bash
   make start-lab1a
   ```
   Sur une machine de 8 Go, vous avez lancé `make check LOW_MEM=1` à l'installation : `make start-lab1a` démarre alors la pile allégée.
2. Vérifiez que les conteneurs sont actifs :
   ```bash
   docker compose -f compose/docker-compose.yml ps
   ```
3. Ouvrez l'interface de Prometheus (`http://localhost:9090/targets`) et vérifiez que les dix cibles déclarées sont à l'état `UP` :
   - `prometheus` (auto-surveillance) ;
   - `traefik` (reverse-proxy HTTPS) ;
   - `gateway`, `rag`, `llm-sim` et `worker` (services applicatifs Orion) ;
   - `postgres`, `node` et `cadvisor` (infrastructure) ;
   - `blackbox` (sonde HTTPS externe vers `https://traefik/healthz`).
4. Ouvrez Grafana (`http://localhost:3000`) et consultez le tableau de bord **Orion Gateway — RED**.
   Le générateur de trafic continu `k6` joue en continu les requêtes des équipes support, rh et dev. La légende des courbes se lit « équipe — backend » : l'équipe qui pose la question, le backend qui répond. `ollama` est le vrai modèle de langage (`qwen3:1.7b`) : il rédige une vraie réponse, mais il est lent. `simule` est un LLM simulé (le service `llm-sim`) : il ne rédige rien, il recopie le début du passage le plus proche, avec une latence artificielle calquée sur celle d'un vrai modèle. La Gateway répartit les requêtes entre les deux : la part d'Ollama (`ORION_OLLAMA_RATIO` dans `.env`) est mesurée par `make check` selon la machine, 25 % au plus, 0 % en mode allégé. Le simulé sert donc 75 à 100 % du trafic : il produit un volume réaliste sans saturer les ordinateurs et permet des pannes reproductibles.
5. Interrogez directement l'assistant Orion en HTTPS à l'aide d'une clé d'équipe générée dans votre fichier `.env` (les clés de chaque équipe ont été générées au `make check` et figurent dans `.env` sous `ORION_KEY_SUPPORT`, `ORION_KEY_RH` et `ORION_KEY_DEV` : ne les recréez pas) :
   ```bash
   set -a && . ./.env && set +a
   curl --cacert config/traefik/certs/ca.crt -sS \
     -H "Authorization: Bearer ${ORION_KEY_SUPPORT}" \
     -H "Content-Type: application/json" \
     -d '{"question": "Quelle est la procédure de réinitialisation MFA ?"}' \
     https://localhost:8443/ask | python3 -m json.tool
   ```
   Observez la réponse JSON reçue : elle contient les champs `answer` et `sources`. `sources` est la liste des passages retrouvés par la recherche vectorielle (5 passages, avec `doc_id`, `title` et `distance`). `distance` est la distance cosinus entre la question et le passage : plus elle est faible, plus le passage est proche sémantiquement. La gateway interroge la base vectorielle (top-k documents les plus proches de la question), puis envoie la question et les documents à Ollama (ou au modèle simulé) pour formuler la réponse. Si la base ne contient pas d'information pertinente, la réponse sera faible malgré un LLM fonctionnel. Quand le simulé répond, `answer` reprend le début du passage le plus proche.

### Étape 2 — Panne A : coupure franche d'un service (12 min)

La sonde externe `blackbox-exporter` interroge `https://traefik/healthz` comme le ferait un client, toutes les 10 s (depuis l'extérieur de la pile, comme un utilisateur ou un load balancer), et publie `probe_success` (1 ou 0) et `probe_http_status_code`.

1. Arrêtez le conteneur `rag` :
   ```bash
   docker compose -f compose/docker-compose.yml stop rag
   ```
2. Patientez 30 à 45 secondes pendant que `k6` continue d'envoyer du trafic, puis observez dans Prometheus (`http://localhost:9090/query` — tapez la requête dans le champ d'expression, puis Execute ; onglet Graph pour la courbe) :
   - la sonde externe : `probe_success{job="blackbox"}` et `probe_http_status_code{job="blackbox"}` ;
   - le taux de réponses HTTP par code sur Traefik :
     ```promql
     sum by (code) (rate(traefik_service_requests_total{service="rag@file"}[1m]))
     ```
   - l'état de la cible `rag` sur `http://localhost:9090/targets`.
3. Notez dans les notes de votre trinôme (vos notes sont personnelles, elles ne sont pas relevées mais vous serviront pour le rapport final) :
   - quel composant rapporte l'erreur en premier ;
   - quel code HTTP Traefik renvoie aux clients lorsque `rag` ne répond plus ;
   - pourquoi les compteurs applicatifs `rag_requests_total` cessent d'évoluer pendant la panne.
4. Redémarrez `rag` et vérifiez le retour à la normale :
   ```bash
   docker compose -f compose/docker-compose.yml start rag
   ```

### Étape 3 — Détecter une panne silencieuse : les signaux de qualité (8 min)

En marche normale, aucun incident n'est injecté : tous les conteneurs sont actifs et répondent en `HTTP 200`. Retrouvez les signaux qui ont permis de révéler la panne lors de la démonstration de l'enseignant (situation où la recherche vectorielle ne renvoyait plus aucun document pertinent, alors qu'Orion continuait à renvoyer des codes `200 OK`) :

1. **Compteurs de qualité de référence** :
   Dans Prometheus (`http://localhost:9090/query` — tapez la requête dans le champ d'expression, puis Execute ; onglet Graph pour la courbe), observez :
   ```promql
   sum by (result) (rate(quality_reference_checks_total[5m]))
   ```
   Le générateur `k6` pose périodiquement des questions de référence dont le passage documentaire attendu est connu à l'avance. Le service `rag` incrémente `good` si ce passage figure parmi les sources retrouvées et que la réponse n'est ni un refus ni un mode dégradé, et `bad` sinon.
   Un résultat `bad` isolé ne suffit pas à caractériser une panne : des requêtes utilisateur ponctuelles peuvent légitimement être imprécises. C'est pourquoi l'alerte de qualité s'appuie sur le ratio calculé sur 15 minutes par la recording rule `job:orion_quality_good_ratio:rate15m` et son seuil critique (90 %).

2. **Signaux de qualité dans les journaux Loki** :
   Dans Grafana Explore (`http://localhost:3000/explore`, source **Loki**), exécutez la requête LogQL sur les journaux de `rag` :
   ```logql
   {service="rag"} | json | route = "/ask"
   ```
   Inspectez les champs extraits de chaque requête : `docs_found` (nombre de passages retrouvés) et `top_score` (score de similarité valant 1 − distance du meilleur passage). En marche normale, `docs_found` vaut 5 et `top_score` reste élevé (supérieur à 0,65). Lors d'une panne silencieuse de la recherche vectorielle, `docs_found` tombe à 0 ou `top_score` s'effondre sans qu'aucun code d'erreur HTTP ne soit émis.

3. **Limites des sondes de disponibilité** :
   Constatez pourquoi ni `probe_success{job="blackbox"}` (qui sonde `/healthz` à l'entrée de Traefik) ni le taux d'erreurs 5xx sur Traefik n'ont permis de voir la panne de la démonstration : le service `rag` était en cours d'exécution et renvoyait des réponses HTTP 200 syntaxiquement valides, masquant la défaillance de pertinence métier.

### Étape 4 — Cartographie RED vs USE de la stack Orion (10 min)

À l'aide de `docs/architecture.md` et de l'explorateur de métriques Prometheus (`http://localhost:9090/query` — tapez la requête dans le champ d'expression, puis Execute ; onglet Graph pour la courbe), complétez pour votre groupe un tableau associant à chaque composant :
- la méthode principale adaptée (**RED** pour un service orienté requêtes, **USE** pour une ressource d'infrastructure) ;
- une métrique précise présente dans Prometheus pour chaque lettre de l'acronyme retenu :
  - `traefik` ;
  - `rag` ;
  - `gateway` ;
  - `worker` ;
  - `postgres-db` / pool de connexions (`rag_db_pool_wait_seconds`, `pg_stat_activity_count`) ;
  - conteneurs Docker (`container_memory_working_set_bytes`, `container_cpu_usage_seconds_total`).

## Vérifier votre réussite

Avant de passer à la suite, assurez-vous que :

- tous les conteneurs de la stack sont à l'état `Up` (`docker compose -f compose/docker-compose.yml ps`) ;
- toutes les cibles Prometheus sur `http://localhost:9090/targets` sont `UP` ;
- une requête `POST https://localhost:8443/ask` renvoie un code `200` et une réponse JSON contenant des `sources` ;
- votre tableau RED / USE associe des noms de métriques réellement exposés par la stack.

## Pour aller plus loin

- Inspectez dans `config/blackbox/blackbox.yml` et `config/prometheus/prometheus.yml` comment Prometheus utilise le *relabeling* (`__param_target`, `__address__`) pour faire sonder `https://traefik/healthz` par `blackbox-exporter`.
- Comparez `rate(traefik_service_requests_total[1m])` et `irate(traefik_service_requests_total[1m])` sur un graphique Grafana : observez la différence de sensibilité aux variations brèves du trafic `k6`.

Fin de séance : make down arrête la pile en conservant vos données ; make start-lab1a la relance.
