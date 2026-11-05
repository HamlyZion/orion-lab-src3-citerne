# Lab 4a — Détection d'anomalies, saisonnalité et prédiction linéaire

> **Lab facultatif, non noté.** La séance 6 n'a pas lieu : ce lab reste disponible pour qui veut approfondir la détection d'anomalies et `predict_linear`. La règle prédictive contrôlée au checkpoint 4 est fournie à l'étape 5 du lab 4b.

- **Durée** : 60 minutes
- **Séance** : aucune (lab facultatif, à faire en autonomie)
- **Code de session console** : `PF5HHRZQJ9`
- **Validation** : aucune. Le checkpoint 4 (séance 7) contrôle une règle prédictive fournie dans l'énoncé du lab 4b
- **Dépôt de travail** : votre dépôt de trinôme, créé une seule fois à la séance 1 (README, §1 : `git clone https://github.com/jassouline/orion-lab.git`, puis `upstream` et `origin`). `make start-lab4a` remet l'état d'exécution à zéro sans toucher à vos fichiers.

## Objectifs

À l'issue de ce lab, vous saurez :

1. Calculer un z-score en PromQL à l'aide des fonctions `avg_over_time()` et `stddev_over_time()`, et comprendre pourquoi les variations de charge cycliques provoquent des faux positifs massifs sur un signal brut.
2. Éliminer l'effet de la saisonnalité par comparaison différentielle à fenêtre glissante (`offset 1h`) et évaluer la réduction des fausses alertes par rapport à une série de vérité terrain.
3. Implémenter une règle d'alerte prédictive en PromQL à l'aide de `predict_linear()` pour anticiper l'épuisement d'une capacité déclarée avant la panne effective.
4. Enregistrer votre prédiction dans la console avant le déclenchement d'un événement annoncé, puis confronter les alertes observées à votre calcul théorique.

## Ce qui est fourni

- L'historique synthétique de 3 heures injecté dans Prometheus par `make start-lab4a` :
  - reproduit le profil de trafic cyclique nominal de 60 minutes ;
  - contient des anomalies de charge à des instants connus ;
  - expose la série de vérité terrain `orion_lab4a_ground_truth_anomaly` (valeur 1 aux instants d'anomalie réelle, 0 le reste du temps).
- Le fichier `config/prometheus/rules.yml` pour ajouter votre nouvelle règle d'alerte.
- Les métriques de stockage PostgreSQL exposées par `postgres_exporter`, en particulier `pg_database_size_bytes` qui mesure la taille de chaque base, notamment la base dédiée `orion_audit` (taille nominale initiale d'environ 7,7 Mo, pour une capacité maximale déclarée de 50 Mo).
- La console d'incident sur `http://127.0.0.1:8088`.

> **Repartir d'un fichier d'origine** : `make start-lab4a` réinitialise le volume Prometheus et injecte un historique neuf de 3 heures sans écraser vos fichiers de configuration. Pour retrouver la version d'origine d'un fichier depuis le dépôt modèle :
> ```bash
> git checkout upstream/main -- <chemin/du/fichier>
> ```

## Encadré de référence — Détection statistique et prédiction en PromQL

### Le z-score et le piège de la saisonnalité

Le z-score mesure l'écart absolu d'une valeur instantanée $x_t$ par rapport à sa moyenne glissante $\mu$, normalisé par son écart-type $\sigma$ (auquel on ajoute un terme $\varepsilon = 10^{-6}$ pour éviter toute division par zéro sur un palier plat) :

$$|z_t| = \frac{|x_t - \mu|}{\sigma + 10^{-6}} = \frac{|x_t - \text{avg\_over\_time}(x[w])|}{\text{stddev\_over\_time}(x[w]) + 10^{-6}}$$

Sur un système soumis à un cycle régulier (par exemple le cycle de charge d'Orion d'une période de 60 minutes), une fenêtre glissante courte ou moyenne ($w = 15\text{ min}$) interprète chaque montée ou descente régulière comme un écart anormal : le dénominateur $\sigma$ diminue pendant les phases stables, provoquant des explosions de $|z_t|$ lors des transitions attendues.

### La comparaison saisonnière (`offset`)

Pour s'affranchir du cycle régulier de 60 minutes, on compare le signal actuel à sa valeur observée un cycle plus tôt :

$$\Delta_t = x_t - (x_t \text{ offset 1h})$$

Le résidu $\Delta_t$ élimine la composante déterministe de la charge : un seuillage direct de $|\Delta_t|$ ou un z-score calculé sur ce résidu (en PromQL, appliquer `avg_over_time` ou `stddev_over_time` à une expression composée comme ce résidu impose une sous-requête de la forme `(job:traefik_requests:rate5m - (job:traefik_requests:rate5m offset 1h))[15m:1m]`) ne réagit plus aux alternances normales de charge et cible exclusivement les ruptures imprévues.

### La projection linéaire avec `predict_linear()`

Prometheus fournit la fonction `predict_linear(v[range], t)` qui ajuste une droite par la méthode des moindres carrés sur la fenêtre d'observation `range` et extrapole la valeur estimée de la série dans `t` secondes :

$$\hat{y}(t) = y_0 + \text{pente} \times t$$

Pour une ressource à capacité finie déclarée $C_{\text{max}}$ (par exemple une base de données avec une limite d'exploitation de 50 Mo), une alerte prédictive compare l'estimation à l'horizon cible $t = 4\text{ h}$ ($14\,400\text{ s}$) :

$$\text{predict\_linear}(x[10\text{m}], 14400) > C_{\text{max}}$$

Cette alerte prévient l'exploitant plusieurs heures avant la saturation, transformant une urgence critique en une tâche planifiée (« aucune action d'urgence immédiate », ouverture d'un ticket de maintenance).

---

## Étapes à réaliser

### Étape 1 — Détection par z-score et piège de la saisonnalité (15 min)

1. Démarrez l'environnement du lab 4a :
   ```bash
   make start-lab4a
   ```
   > **Note** : `make start-lab4a` recrée le stockage Prometheus et injecte 3 heures d'historique continu (au pas de `10s`) se terminant juste avant l'heure courante.
2. Ouvrez Prometheus (`http://127.0.0.1:9090/query` — onglet **Graph**) ou Grafana Explore (`http://127.0.0.1:3000/explore`) et **réglez la plage temporelle du graphe sur `3h`** (`Last 3 hours`, pas de résolution `10s`).
3. Interrogez le débit global de requêtes sur le service `rag@file` :
   ```promql
   job:traefik_requests:rate5m
   ```
   Observez le cycle périodique de charge d'Orion sur les 3 heures d'historique.
4. Calculez la valeur absolue du z-score avec une fenêtre glissante de 15 minutes :
   ```promql
   abs(
     job:traefik_requests:rate5m
     -
     avg_over_time(job:traefik_requests:rate5m[15m])
   )
   /
   (stddev_over_time(job:traefik_requests:rate5m[15m]) + 1e-6)
   ```
5. Filtrez les instants où ce z-score franchit le seuil statique `2.5` :
   ```promql
   abs(
     job:traefik_requests:rate5m
     -
     avg_over_time(job:traefik_requests:rate5m[15m])
   )
   /
   (stddev_over_time(job:traefik_requests:rate5m[15m]) + 1e-6) > 2.5
   ```
   - Constatez sur la plage `3h` le nombre important de déclenchements qui coïncident simplement avec les pentes de montée ou de descente après les sommets et les creux du trafic régulier.

### Étape 2 — Désaisonnalisation avec `offset 1h` et vérité terrain (15 min)

1. Toujours sur une plage de **`3h`** (pas `10s`), affichez sur le même graphe la série actuelle et la série décalée d'un cycle complet :
   ```promql
   job:traefik_requests:rate5m
   ```
   et
   ```promql
   job:traefik_requests:rate5m offset 1h
   ```
2. Calculez l'écart absolu désaisonnalisé et appliquez le seuil de `0.15` req/s :
   ```promql
   abs(job:traefik_requests:rate5m - (job:traefik_requests:rate5m offset 1h)) > 0.15
   ```
3. Affichez en superposition la série de vérité terrain fournie dans l'historique :
   ```promql
   orion_lab4a_ground_truth_anomaly
   ```
4. Comparez les deux méthodes **en comptant les faux positifs en nombre d'échantillons au pas de `10s`** sur la plage `3h` pendant les périodes normales (`orion_lab4a_ground_truth_anomaly == 0`) :
   - Combien d'échantillons faux positifs (au pas de `10s`) générait le z-score `> 2.5` en dehors des vraies anomalies (vous pouvez le mesurer directement via `count_over_time(((abs(job:traefik_requests:rate5m - avg_over_time(job:traefik_requests:rate5m[15m])) / (stddev_over_time(job:traefik_requests:rate5m[15m]) + 1e-6) > 2.5) and on() (orion_lab4a_ground_truth_anomaly == 0))[3h:10s])`) ?
   - Combien d'échantillons faux positifs subsistent avec `abs(job:traefik_requests:rate5m - (job:traefik_requests:rate5m offset 1h)) > 0.15`, et comment ce seuil capte-t-il l'intégralité des deux anomalies de débit (hausse brutale et chute de trafic) sans déclencher sur la sinusoïde ?
   - Remarquez qu'une des trois fenêtres où `orion_lab4a_ground_truth_anomaly == 1` est une anomalie pure de latence à trafic normal (visible sur `job:orion_gateway_latency_p95:5m`, mais invisible sur le débit `job:traefik_requests:rate5m`).

### Étape 3 — Règle d'alerte prédictive avec `predict_linear()` (15 min)

Dans ce système, la base de données d'audit `orion_audit` dispose d'une capacité déclarée d'exploitation fixée à **50 Mo** ($50 \times 10^6$ octets).

1. Dans Prometheus (`http://127.0.0.1:9090/query`, onglet **Graph**, plage `3h`), visualisez la métrique de taille de cette base :
   ```promql
   pg_database_size_bytes{datname="orion_audit"}
   ```
2. Testez l'extrapolation linéaire de cette taille à un horizon de 4 heures ($4 \times 3600 = 14\,400\text{ s}$) sur une fenêtre glissante de 10 minutes :
   ```promql
   predict_linear(pg_database_size_bytes{datname="orion_audit"}[10m], 4 * 3600)
   ```
3. Ouvrez `config/prometheus/rules.yml` et ajoutez dans le groupe `orion_slo_alerts` votre règle d'alerte prédictive :
   - **Nom de l'alerte** : `OrionAuditDatabaseSaturationPredite`
   - **Expression PromQL** : compare la projection à 4 heures de `pg_database_size_bytes{datname="orion_audit"}` sur une fenêtre de 10 minutes au seuil de $50 \times 10^6$ octets, et s'assure que la taille actuelle est encore strictement inférieure à ce seuil (l'alerte est prédictive, pas un constat de panne déjà survenue).
   - **Clause `for:`** : `2m` (pour filtrer d'éventuelles variations ponctuelles de calcul).
   - **Labels** : `severity: ticket`, `service: postgres-db`.
   - **Annotations** : `summary` et `description` expliquant que la base `orion_audit` risque de dépasser sa capacité de 50 Mo dans les 4 prochaines heures.
4. Validez la syntaxe avec `promtool` via le conteneur Prometheus et rechargez la configuration en vérifiant le code HTTP `200` :
   ```bash
   docker compose -f compose/docker-compose.yml exec -T prometheus \
     promtool check rules /etc/prometheus/rules.yml
   curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:9090/-/reload
   ```
5. Vérifiez sur `http://127.0.0.1:9090/rules` que l'alerte `OrionAuditDatabaseSaturationPredite` apparaît et est évaluée sans erreur.

### Étape 4 — Prédiction dans la console et observation sous événement annoncé (15 min)

1. Ouvrez la console d'incident sur `http://127.0.0.1:8088`.
2. Saisissez le code de session `PF5HHRZQJ9` et renseignez les **trois rôles obligatoires** (**Incident Commander**, **Mitigator**, **Investigator** ; si vous travaillez seul, saisissez votre prénom dans les trois champs).
3. Cliquez sur **« Ouvrir la session »** : l'ouverture déclenche aussitôt l'événement sur la stack.
4. Immédiatement après l'ouverture, avant d'aller consulter Prometheus ou Grafana, rédigez votre prédiction (quel indicateur va évoluer, selon quelle tendance, et quelle alerte passera à l'état `firing`), puis cliquez sur **« Enregistrer la prédiction »**.
5. Observez dans Prometheus (`http://127.0.0.1:9090/alerts`) et Grafana (`http://127.0.0.1:3000/explore`) l'évolution de `pg_database_size_bytes{datname="orion_audit"}` et de `predict_linear(pg_database_size_bytes{datname="orion_audit"}[10m], 4 * 3600)` :
   - Constatez le passage en `pending` puis en `firing` de `OrionAuditDatabaseSaturationPredite` en quelques minutes, alors même que la taille réelle de `orion_audit` demeure nettement sous le plafond de 50 Mo.
   - Confrontez le comportement observé à votre prédiction initiale.
6. Pour rétablir l'état nominal, renseignez la synthèse de clôture dans la console puis cliquez sur **« Clôturer l'incident et générer l'archive »**.

---

## Vérifier votre réussite

Avant de quitter la séance, vérifiez les quatre points suivants :

1. `curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:9090/-/reload` affiche `200`.
2. Sur `http://127.0.0.1:9090/rules`, la règle `OrionAuditDatabaseSaturationPredite` est présente dans le groupe `orion_slo_alerts` avec l'état `health: ok`.
3. Sous la session `PF5HHRZQJ9`, l'alerte `OrionAuditDatabaseSaturationPredite` est bien passée à l'état **`firing`** sur `http://127.0.0.1:9090/alerts` pendant que `pg_database_size_bytes{datname="orion_audit"}` restait sous `50000000` octets.
4. La session a été refermée via **« Clôturer l'incident et générer l'archive »** sur `http://127.0.0.1:8088`.

> [!IMPORTANT]
> **Pour le lab 4b** : si vous gardez votre règle `OrionAuditDatabaseSaturationPredite` dans `config/prometheus/rules.yml`, le checkpoint 4 (`make check-lab4b`) la contrôlera à la place de la règle fournie à l'étape 5 du lab 4b.

Fin de séance : `make down` arrête la pile en conservant vos données ; `make start-lab4a` la relance.
