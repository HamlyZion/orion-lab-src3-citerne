# Consignes du Game Day — Séance 8

Ce document définit les règles, le barème et les livrables de la séance 8 (Game Day) du cours « Monitoring, Observabilité et AIOps ».

---

## 1. Organisation générale

Le Game Day est une simulation d'incident en direct sur la plateforme Orion.
L'exercice dure 1 h 30 et se déroule en quatre temps :
1. **Briefing et initialisation (10 min)** : saisie du code de session et attribution des rôles dans la console d'incident (`http://127.0.0.1:8088`).
2. **Incident en direct (60 min)** : détection, mitigation d'urgence, investigation et collecte des preuves.
3. **Clôture et export (5 min)** : déclaration finale de la cause racine et export de l'archive de preuves.
4. **Débriefing collectif (15 min)** : analyse collective des pannes et comparaison des diagnostics humains avec l'outil de diagnostic local.

---

## 2. Rôles au sein du trinôme

Chaque membre du trinôme assume un rôle opérationnel nominatif, enregistré dans la console d'incident :

- **Incident Commander (IC)** :
  - Pilote la réponse opérationnelle et anime la communication du groupe.
  - Déclare formellement l'incident dans la console dès que l'anomalie est avérée.
  - Tient la chronologie des décisions et des constats.
  - Enregistre la déclaration de la cause racine et prononce la clôture.
- **Mitigator** :
  - Surveille en priorité le respect des objectifs de niveau de service (SLO).
  - Propose et applique les actions de contournement pour rétablir la disponibilité ou la latence.
  - Justifie obligatoirement chaque action d'urgence par une observation préalable dans la console.
- **Investigator** :
  - Analyse les signaux d'observabilité (Prometheus, Loki, Tempo).
  - Isole le composant défaillant par corrélation métriques-logs-traces.
  - Exécute l'outil d'analyse assistée local (`make rca`) et compare ses hypothèses aux mesures.

*Cas d'un groupe de quatre étudiants* : le quatrième membre est enregistré nominativement comme second **Investigator**. La console accepte quatre rôles.
*Cas d'absence justifiée d'un membre* : les deux étudiants présents se répartissent les trois fonctions (l'un cumule IC et Investigator, l'autre assure Mitigator).

---

## 3. Règles du jeu

### Règle d'or : mitiger d'abord, investiguer ensuite
En production comme au Game Day, la priorité absolue est d'arrêter l'hémorragie sur le service utilisateur avant de chercher l'explication technique détaillée :
- Tant que le service est dégradé, l'équipe cherche à restaurer le SLO par les leviers d'exploitation disponibles.
- L'investigation fine de la cause racine s'approfondit dès que le service est stabilisé ou délesté.

### Déclaration d'incident et mesure du MTTD
- Le délai moyen de détection (MTTD) se mesure entre le déclenchement réel de la dégradation et l'horodatage de la déclaration formelle effectuée par l'Incident Commander dans la console.
- Une déclaration déclenchée sans anomalie réelle ou sur un événement bénin constitue un faux positif et impacte la note.

### Justification préalable des actions de mitigation
- Dans la console, le menu d'action d'urgence exige la saisie préalable d'une observation justificative :
  - un constat textuel synthétique ;
  - une requête de preuve (PromQL, LogQL, TraceQL ou SQL).
- Pour l'activation des leviers natifs de la passerelle (mode dégradé ou délestage), l'indication de l'alerte de SLO active suffit comme constat.

### Indices progressifs
Si votre groupe se trouve bloqué, trois niveaux d'indices progressifs peuvent être débloqués directement dans la console :
- Les indices deviennent accessibles uniquement après **25 minutes** d'exercice en direct.
- Chaque consultation déduit des points du total de l'épreuve :
  - Indice 1 (orientation générale du signal et composants) : **-1 point** ;
  - Indice 2 (ciblage des métriques et requêtes clés) : **-1,5 point** ;
  - Indice 3 (localisation précise du mécanisme) : **-2 points**.
- Le retrait de points s'applique sur le total du Game Day, avec un plancher strict à 0.

### Clôture et archivage
- Avant la fin des 60 minutes, l'Incident Commander consigne la cause racine identifiée et la requête de preuve associée.
- L'équipe clique sur « Clôturer l'incident et générer l'archive » dans la console.
- Cette action génère une archive compressée `.tar.gz` (`timeline.md`, `journal.age` et les extraits de télémétrie). Téléchargez-la avec le bouton « Télécharger l'archive (.tar.gz) » ; elle est aussi conservée dans `.orion-state/exports/`.

---

## 4. Outils autorisés et interdits

### Outils autorisés
- Interfaces de la plateforme Orion : Grafana, Prometheus, alertes Alertmanager.
- Console d'incident (`http://127.0.0.1:8088`).
- Outil d'analyse assistée local (`make rca`).
- Tout moteur de recherche web et documentation technique officielle.
- Assistants d'IA conversationnels en mode chat **exclusivement dans le navigateur web**. Tout échange doit être mentionné dans le journal d'usage de l'IA.

### Outils interdits
- Tout agent d'IA autonome exécuté dans le terminal ou connecté directement aux fichiers du dépôt (par exemple Claude Code, Gemini CLI, Cursor en mode agent, Copilot Workspace ou équivalents).
- Tout plugin d'IDE ou pont MCP reliant un LLM directement aux outils de supervision (`mcp-grafana` ou similaire).
- Toute inspection directe de l'état interne des conteneurs par `docker inspect` ou contournement des accès réseau. Les preuves doivent provenir exclusivement des outils de télémétrie.

### Règle visuelle et contrôles
- Aucun assistant d'IA ne doit tourner dans le terminal ou l'IDE pendant l'épreuve.
- L'enseignant circule en salle pour observer le travail des équipes.
- La constatation d'un outil interdit entraîne la neutralisation immédiate du critère « Cause racine déclarée à chaud » (note ramenée à 0 sur ce critère) et un signalement selon le règlement des études.

### Postes d'entreprise
Si votre machine professionnelle dispose d'un assistant dans l'IDE impossible à désactiver, signalez-le avant le début de l'épreuve et utilisez la machine d'un autre membre de votre groupe.

---

## 5. Journal d'incident : rôle, format et conservation

Au fil de votre session, la console alimente automatiquement deux représentations de vos actions :
1. **`timeline.md` (en clair)** :
   - Fichier Markdown lisible dans votre espace de travail.
   - Contient les rôles, les déclarations d'alerte, les observations enregistrées, les mitigations tentées et l'heure de clôture.
   - Sert de base à la rédaction de votre post-mortem.
2. **`journal.age` (chiffré)** :
   - Fichier chiffré avec la clé publique de l'enseignant.
   - Chaque ligne correspond à un événement horodaté, numéroté de façon séquentielle (de 1 à N) et lié cryptographiquement au précédent par une chaîne de hachage SHA-256.
   - Garantit l'inviolabilité, l'authenticité et la non-répudiation des actions du groupe.
   - Toute altération ou suppression de ligne est automatiquement détectée lors de la correction.

Pendant le débriefing, l'enseignant relève le fichier `journal.age` de chaque trinôme et note son empreinte en présence du groupe. Ce fichier fait foi pour l'évaluation chiffrée.

---

## 6. Barème détaillé du Game Day (15 points)

Le Game Day compte pour **15 %** de la note finale du module. La notation s'appuie sur le journal chiffré et applique le barème ci-dessous :

| Critère | Points | Modalités d'attribution |
|---|---|---|
| **Délai moyen de détection (MTTD)** | **3** | Calculé par le ratio r = MTTD du groupe / MTTD de référence :<br>- r ≤ 1,25 : **3 points**<br>- r ≤ 1,75 : **2 points**<br>- r ≤ 2,50 : **1 point**<br>- r > 2,50 ou incident non déclaré : **0 point**.<br>*Chaque faux positif retire 1 point de ce critère (plancher à 0).* |
| **Délai de rétablissement (MTTR) et mitigations** | **5** | **MTTR relatif (3 points)**, selon la même échelle de ratio r = MTTR du groupe / MTTR de référence :<br>- r ≤ 1,25 : **3 points**<br>- r ≤ 1,75 : **2 points**<br>- r ≤ 2,50 : **1 point**<br>- r > 2,50 ou indicateur non rétabli : **0 point**.<br>**Mitigations justifiées (2 points)** :<br>- 2 points si toutes les actions sont précédées d'une observation documentée.<br>- 1 point si une seule action manque de justification.<br>- 0 point si deux actions ou plus ne sont pas justifiées, ou si aucune mitigation n'a été saisie. |
| **Cause racine déclarée à chaud** | **4** | - Juste et prouvée par une requête de télémétrie : **4 points**.<br>- Juste mais sans preuve recevable : **2 points**.<br>- Bonne couche architecturale mais mauvais composant : **1 point**.<br>- Fausse ou absente : **0 point**.<br>*Incidents combinés* : l'identification documentée du second incident rapporte **1 point bonus** (dans la limite du plafond de 4 points sur ce critère).<br>*En cas d'usage d'un outil interdit constaté* : note ramenée à **0 point**. |
| **Tenue de la chronologie et export** | **3** | - Chronologie complète et cohérente dans la console (rôles, déclarations, observations, cause, clôture) : **2 points**.<br>- Archive d'export générée avant la fin de la séance : **1 point**. |
| **Total brut** | **15** | |

*Application des déductions d'indices* : déduction de 1, 1,5 ou 2 points selon le niveau débloqué, avec un plancher global de la note à 0 point.

---

## 7. Livrables et modalités de remise

Le projet complet issu du Game Day est à rendre en trinôme **une semaine après la séance 8**.

### Liste des livrables attendus
1. **Archive des preuves du Game Day** :
   - Fichier `.tar.gz` généré par la console d'incident, enrichi des captures d'écran Grafana prises pendant l'incident.
2. **Post-mortem blameless (`post-mortem.md`)** :
   - Rédigé selon le gabarit `gabarits/post-mortem.md`.
   - Comprend la chronologie, l'analyse des signaux, les limites de la mitigation, la preuve de la cause racine, l'impact sur l'error budget, les actions préventives et la transposition Kubernetes (5 lignes et court manifeste).
   - Chaque section doit comporter la signature nominative de son rédacteur principal.
3. **Observabilité « as code » (`as-code/`)** :
   - Dépôt ou dossier structuré selon `gabarits/as-code/`.
   - Contient vos règles Prometheus (SLO, burn rate validées par `promtool test rules`), dashboards JSON exportés, configuration Alloy avec masquage validé et manifestes Kubernetes commentés.
   - Accompagné d'un fichier `README.md` justifiant les arbitrages d'ingénierie retenus.
4. **Journal d'usage de l'IA (`journal-usage-ia.md`)** :
   - Document synthétique d'une page selon `gabarits/journal-usage-ia.md`.
   - Analyse critique des sorties de l'outil de diagnostic local sur l'incident du Game Day et bilan réflexif des échanges tenus avec des assistants conversationnels.

### Informations pratiques de remise
- **Canal de remise** : le dépôt GitHub privé du trinôme, au tag `rendu-projet` (voir la section « Remettre vos travaux » du `README.md`).
- **Date limite de remise** : sept jours après la séance 8.
- **Heure limite de remise** : 23 h 59, heure de Paris.
- **Pénalités de retard** : aucun retard accepté ; un tag posé après l'heure limite n'est pas lu.
