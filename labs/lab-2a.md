# Lab 2a — Pipeline de logs Alloy vers Loki, budget de flux et masquage

- **Durée** : 50 minutes
- **Séance** : 3 (Journaux structurés, cardinalité et conformité)
- **Prérequis** : pile Orion démarrée (`make up`)
- **Dépôt de travail** : votre dépôt de trinôme, créé une seule fois à la séance 1 (README, §1 : `git clone https://github.com/jassouline/orion-lab.git`, puis `upstream` et `origin`). `make start-lab2a` remet l'état d'exécution à zéro sans toucher à vos fichiers.

## Objectifs

À l'issue de ce lab, vous saurez :

1. Configurer un pipeline `loki.process` dans Grafana Alloy (`config/alloy/config.alloy`) pour extraire les champs des journaux JSON d'Orion.
2. Arbitrer entre *labels* indexés (`stage.labels`) et métadonnées structurées (`stage.structured_metadata`) afin de respecter un **budget strict d'au plus 1 000 flux actifs** dans Loki (`max_global_streams_per_user: 1000`).
3. Identifier une fuite de données sensibles dans les journaux applicatifs, auditer un extrait de masquage généré par un assistant, et masquer ces données avant leur indexation sans corrompre le JSON.

## Ce qui est fourni

- La configuration de Loki dans `config/loki/loki.yaml`, qui impose `max_global_streams_per_user: 1000` et active `allow_structured_metadata: true`.
- La configuration d'Alloy à compléter dans `config/alloy/config.alloy`, avec les marqueurs `// # TODO(lab-2a)`.
- Un extrait généré par un assistant à auditer dans `labs/artefacts/lab-2a-alloy-replace-ia.alloy`.

> **Repartir d'un fichier d'origine** : `make start-lab2a` ne modifie aucun de vos fichiers de configuration. Pour revenir à la version initiale de `config/alloy/config.alloy` depuis le dépôt modèle :
> ```bash
> git fetch upstream && git checkout upstream/main -- config/alloy/config.alloy
> ```
>
> **Point d'étape à 40 minutes** : à 40 minutes, si vous êtes bloqués, l'enseignant vous remet une configuration de départ.

## Étapes à réaliser

> Notez vos réponses aux questions 1.3, 1.4, 3.1 et 3.2 dans les notes de votre trinôme (non relevées ; elles servent à l'oral et au débrief).

### Étape 1 — Inspection des journaux bruts et du pipeline Alloy (10 min)

1. Démarrez l'état d'exécution du lab 2a :
   ```bash
   make start-lab2a
   ```
2. Dans Grafana (`http://127.0.0.1:3000/explore`), sélectionnez la source de données **Loki** et exécutez la requête :
   ```logql
   {service=~".+"}
   ```
3. Inspectez la structure JSON des lignes produites par les différents services d'Orion et recensez les champs présents (`ts`, `level`, `service`, `msg`, `trace_id`, `span_id`, `team`, `version`, ainsi que les champs métiers propres à chaque service). Grafana Alloy collecte tous les conteneurs Docker de la pile (`container`, `compose_service`) ; seuls `rag`, `gateway`, `worker` et `llm-sim` écrivent du JSON avec le champ `service`.

   > Dans Explore, chaque ligne porte aussi deux étiquettes posées par Loki lui-même, pas par Alloy : `service_name` (copie de `service`, ou nom du conteneur pour les autres) et `detected_level` (le niveau que Loki devine dans la ligne). Elles n'ajoutent aucun flux : laissez-les de côté dans votre arbitrage.
4. Pour chacun des champs `service`, `level`, `team`, `version` et `trace_id` (`ts` et `msg` sont exclus : une valeur par ligne), dites s'il ne prend que quelques valeurs, ou une valeur nouvelle à chaque requête. Lesquels pourraient devenir des *labels* Loki sans ouvrir un nouveau flux à chaque requête ?

   Pour lister les valeurs d'un champ vues depuis une heure, exécutez dans Explore (source **Loki**, éditeur en mode « Code ») :
   ```logql
   sum by (level) (count_over_time({service=~".+"} | json [5m]))
   ```
   La légende sous le graphique nomme une courbe par valeur, même quand la courbe est trop basse pour se voir ; `{team=""}` désigne les lignes où le champ est vide. Remplacez `level` par `team` ou `version`. Une valeur rare peut ne pas apparaître en une heure : comptez aussi les valeurs possibles, pas seulement celles que vous voyez. Pour `trace_id`, comparez deux lignes successives.

### Étape 2 — Arbitrage labels vs métadonnées structurées sous budget (20 min)

1. Ouvrez `config/alloy/config.alloy` et complétez le bloc `stage.json` de `loki.process "orion_logs"` pour extraire les champs utiles au tri et à la corrélation.
2. Choisissez quels champs à faible cardinalité doivent figurer dans `stage.labels` (pour le filtrage rapide de flux) et quels identifiants à forte cardinalité doivent être attachés dans `stage.structured_metadata` (notamment `trace_id`, pour suivre une requête d'un service à l'autre).
   - **Attention au piège de cardinalité** : si vous placez un identifiant unique par requête (`trace_id`, `span_id`, etc.) dans `stage.labels`, chaque requête ouvre un nouveau flux dans Loki. Un flux reste actif jusqu'à ce qu'il ne reçoive plus de ligne pendant la durée `chunk_idle_period` de `config/loki/loki.yaml`, soit 30 minutes dans Orion : le budget de 1 000 flux actifs fond à vue d'œil. Une fois le plafond atteint, Loki refuse tout nouveau flux en `HTTP 429` ; Alloy réessaie sans fin d'envoyer le même lot, et **plus aucune ligne d'aucun service n'arrive dans Loki**. Le message `maximum active stream limit exceeded...` se lit dans les journaux de Loki, pas dans ceux d'Alloy :
     ```bash
     docker compose -f compose/docker-compose.yml logs --since 5m loki | grep 429
     ```

   > **Syntaxe Alloy à respecter dans `config/alloy/config.alloy`** :
   > - `stage.structured_metadata` s'écrit comme `stage.labels` (`values = { trace_id = "" }`, avec une virgule à la fin de chaque ligne dans un bloc multi-lignes) ;
   > - chaque champ référencé doit d'abord être extrait plus haut par `stage.json` ;
   > - les commentaires s'écrivent en `//` (le caractère `#` seul provoque `illegal character`) ;
   > - tout antislash doit être doublé dans une chaîne entre guillemets doubles (par exemple `"\\."`, sinon Alloy échoue avec `unknown escape sequence`).

3. Appliquez votre configuration en redémarrant Alloy :
   ```bash
   docker compose -f compose/docker-compose.yml restart alloy
   ```
   > **Si vous avez saturé les 1 000 flux de Loki lors d'un essai** : redémarrer `loki` seul ne libère pas les flux actifs : son journal d'écriture anticipée (*WAL*) les recrée en mémoire au démarrage, et ils restent actifs pendant la durée `chunk_idle_period` (30 minutes). Corrigez d'abord `config/alloy/config.alloy`, redémarrez `alloy`, puis repartez d'un Loki vide en supprimant le volume `orion_orion-lokidata` (**attention : les journaux déjà stockés dans Loki sont perdus**) :
   > ```bash
   > docker compose -f compose/docker-compose.yml rm -sf loki
   > docker volume rm orion_orion-lokidata
   > make up
   > ```
4. Depuis votre terminal, vérifiez le nombre de flux indexés dans Loki :
   ```bash
   curl -sG http://127.0.0.1:3000/api/datasources/proxy/uid/loki/loki/api/v1/series --data-urlencode 'match[]={service=~".+"}' | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["data"]))'
   ```
   La commande compte les flux vus depuis une heure (environ 4 avec `service` seul ; quelques dizaines au plus avec des labels bien bornés, loin du budget de 1 000). Les flux d'avant votre redémarrage restent comptés pendant une heure.

   Vérifiez ensuite dans Grafana Explore (`http://127.0.0.1:3000/explore`, source **Loki**) qu'Alloy décode toujours chaque ligne JSON. Une ligne qu'Alloy n'arrive pas à décoder garde son texte, mais perd le label `service` et ses métadonnées. La requête suivante affiche les lignes JSON des quatre services qui n'ont pas de label `service` ; un résultat vide (« No data ») signifie qu'il n'y en a aucune. Gardez-la, c'est votre **requête de contrôle** pour l'étape 3 :
   ```logql
   {compose_service=~"rag|gateway|worker|llm-sim", service=""} |= `"msg"`
   ```
   > `{service=~".+"} | json | __error__="JSONParserErr"` ne suffit pas : à la lecture, Loki décode les lignes avec tolérance et ne signale pas forcément une ligne cassée.

### Étape 3 — Détection et masquage des données sensibles (20 min)

1. Explorez les journaux dans Loki (`http://127.0.0.1:3000/explore`) : **trouvez quelles données sensibles fuient dans les logs, et de quel service**.
2. Ouvrez l'extrait proposé par un assistant dans `labs/artefacts/lab-2a-alloy-replace-ia.alloy` :
   - analysez l'effet de chacune des deux expressions régulières sur une ligne de log JSON réelle ;
   - identifiez pourquoi cet extrait ne protège pas correctement les données sensibles et pourquoi il casse la validité JSON des lignes stockées dans Loki.

   Pour observer cet effet, vous pouvez coller l'extrait au marqueur `// # TODO(lab-2a)`, redémarrer `alloy`, attendre une minute, puis lancer la requête de contrôle de l'étape 2 et déplier une des lignes qu'elle affiche. Retirez ensuite l'extrait et redémarrez `alloy`.
3. Ajoutez dans `config/alloy/config.alloy`, au niveau du marqueur `// # TODO(lab-2a)` placé avant `stage.json`, les étapes `stage.replace` permettant de masquer toutes les données sensibles repérées **tout en conservant une ligne JSON syntaxiquement valide** :
   - `stage.replace` sans paramètre `source` ne modifie que la ligne brute (et seuls les groupes capturants `(...)` de `expression` sont remplacés) ;
   - ne mettez en *label* (`stage.labels`) ni en métadonnée structurée (`stage.structured_metadata`) aucun champ qui contient une donnée sensible ;
   - supprimez toutes les lignes `// # TODO(lab-2a)` traitées (sinon `make start-lab2b` affiche un avertissement).
4. Redémarrez `alloy`, puis envoyez une requête sur `https://127.0.0.1:8443/ask` avec la clé de l'équipe `support` générée dans `.env` :
   ```bash
   docker compose -f compose/docker-compose.yml restart alloy
   set -a && . ./.env && set +a
   curl --cacert config/traefik/certs/ca.crt \
     -H "Authorization: Bearer $ORION_KEY_SUPPORT" \
     -H "Content-Type: application/json" \
     -d '{"question": "[support] Quelle est la procédure exacte pour : Procédure de réinitialisation du VPN Nordel (DOC-SUP-001) ?"}' \
     https://127.0.0.1:8443/ask | python3 -m json.tool
   ```
   La réponse se termine par `"trace_id": "…"`, l'identifiant de votre requête : copiez cette valeur. Dans Grafana Explore (`http://127.0.0.1:3000/explore`, source **Loki**), la requête `{service="rag"} | trace_id="<valeur copiée>"` affiche la ligne de log de votre requête, émise après le redémarrage d'`alloy` ; dépliez-la pour lire ses champs. Avec `{service=~".+"} | trace_id="<valeur copiée>"`, vous voyez tout son trajet entre les services.

   > Les lignes stockées avant le redémarrage ne sont pas réécrites : ne vous fiez qu'aux lignes émises après. Pour n'afficher qu'elles, attendez une minute après le redémarrage, ouvrez le sélecteur de période en haut à droite d'Explore, saisissez `now-1m` dans « From », puis cliquez sur « Apply time range ». Si une ligne JSON s'affiche d'un seul tenant, cliquez sur l'icône « Set line wrap » de la barre verticale à droite des logs jusqu'à l'état « Wrap JSON ».

   Vérifiez ensuite, sur cette période, que :
   - ces nouvelles lignes de log ne contiennent plus aucune donnée sensible en clair : cherchez le début de chaque valeur repérée à la question 3.1 avec un filtre de texte, `{service=~".+"} |= "<début de la valeur>"` ; un résultat vide (« No data ») confirme le masquage ;
   - la requête de contrôle de l'étape 2 ne renvoie toujours aucune ligne.

   Si `{service="rag"} | trace_id="<valeur copiée>"` ne renvoie rien, Alloy n'a pas pu décoder la ligne de votre requête : retrouvez-la avec `{compose_service="rag"} |= "<valeur copiée>"` et regardez ce que votre masquage en a fait.

## Vérifier votre réussite

Votre pipeline sera validé conjointement avec le lab 2b lors du **Checkpoint 2** (`make check-lab2b`) en séance 4. À la fin du lab 2a, vérifiez que :

- `alloy` est à l'état `Up` (`docker compose -f compose/docker-compose.yml ps alloy`) et ne présente aucune ligne `level=error` dans ses journaux récents juste après le redémarrage (`docker compose -f compose/docker-compose.yml logs --since 1m alloy`). Les lignes `level=warn msg="could not transfer logs"` (`context canceled` ou `use of closed network connection`) sont normales : l'ancien processus les écrit en s'arrêtant ;
- le nombre de flux indexés dans Loki vus depuis une heure reste très inférieur à 1 000 (environ 4 avec `service` seul ; quelques dizaines au plus avec des labels bien bornés, loin du budget de 1 000) :
  ```bash
  curl -sG http://127.0.0.1:3000/api/datasources/proxy/uid/loki/loki/api/v1/series --data-urlencode 'match[]={service=~".+"}' | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["data"]))'
  ```
- les lignes émises après votre dernier redémarrage d'`alloy` sont toutes décodées par Alloy (la requête de contrôle de l'étape 2 ne renvoie rien), sans donnée sensible en clair, et permettent de retrouver une requête par son `trace_id` (`{service=~".+"} | trace_id="..."`).

## Pour aller plus loin

- Comparez le temps d'exécution dans Loki entre un filtre de label (`{service="..."}`) et un filtre de métadonnée structurée (`{service=~".+"} | trace_id="..."`).
- Lisez dans `config/alloy/config.alloy` l'enchaînement complet des composants du pipeline de collecte (le port HTTP interne `12345` d'Alloy n'est pas publié sur l'hôte) : `discovery.docker` → `discovery.relabel` → `loki.source.docker` → `loki.process` → `loki.write`.

Fin de séance : make down arrête la pile en conservant vos données ; make start-lab2a la relance.
