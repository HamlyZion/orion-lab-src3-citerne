# Journal d'Usage des Assistants IA — Livrable Projet (1 Page)

*Ce document consigne et analyse avec esprit critique l'usage des assistants IA au cours des labs et du Game Day. Déclarer un usage n'entraîne aucune pénalité : c'est la rigueur de l'évaluation critique qui est notée.*

---

## 1. Assistants utilisés et périmètre d'usage

| Outil / Modèle | Interface | Périmètre (Labs 1 à 4, Game Day, Rédaction) | Rôle confié |
|---|---|---|---|
| `[Ex. ChatGPT (GPT-4o)]` | Navigateur web | Game Day & Rédaction post-mortem | Relecture de formulations, aide sur syntaxe LogQL |
| `[Ex. Claude 3.5 Sonnet]` | Navigateur web | Labs 1b et 3 | Explication des concepts OpenTelemetry GenAI |
| `[Orion RCA (qwen3:1.7b)]` | CLI local (`make rca`) | Lab 4b & Game Day (incident en direct) | Génération d'hypothèses de cause racine assistée |

---

## 2. Tableau de bord des interactions et détection d'erreurs

| Contexte / Question posée | Apport réel de l'assistant | Erreur, hallucination ou limite constatée | Méthode de vérification humaine |
|---|---|---|---|
| *Aide sur syntaxe PromQL (Lab 1b)* | A proposé une structure pour `histogram_quantile` | A omis le label `le` dans l'agrégation `sum by (le)` | Validation par `promtool check rules` et doc officielle |
| *Compréhension alerte Game Day* | A synthétisé le rôle du code HTTP retourné | A supposé une défaillance externe alors qu'il s'agissait d'un composant interne | Vérification sur les métriques du service |
| *Masquage d'expressions Alloy (Lab 2a)* | A fourni une regex pour les adresses courriel | A oublié d'échapper certains caractères spéciaux | Test unitaire sur flux de logs dans Grafana Loki |

---

## 3. Analyse critique de l'outil de diagnostic local (`make rca`) au Game Day

*Évaluez objectivement les performances du modèle local compact (`qwen3:1.7b`) sur votre incident en direct.*

- **Hypothèses générées par le modèle local** :
  - *Hypothèse 1 (Rang 1)* : `[Composant, cause énoncée et niveau de confiance (high/medium/low)]`
  - *Hypothèse 2 (Rang 2)* : `[Composant, cause énoncée et niveau de confiance (high/medium/low)]`
- **Pertinence et exactitude** : `[L'une des hypothèses ciblait-elle la vraie cause racine ? Le composant identifié était-il exact ?]`
- **Qualité des requêtes de preuve suggérées** : `[La requête (PromQL/LogQL/TraceQL) issue du catalogue apportait-elle la preuve du problème ?]`
- **Observations sur les ressources et le temps de réponse** : `[Temps d'exécution de make rca mesuré en secondes, comportement du bail de suspension du routage]`

---

## 4. Bilan réflexif : forces et limites de l'IA en exploitation SRE

*Synthèse en 5 à 10 lignes : ce que les assistants accélèrent efficacement face à ce qui exige obligatoirement une expertise humaine outillée.*

```text
[Rédigez ici votre synthèse réflexive : l'assistant excelle dans la suggestion syntaxique ou l'explication
de concepts documentés, mais échoue sur le raisonnement causal en environnement complexe sans données
de télémétrie fraîches. En SRE, l'IA ne remplace pas l'enquête outillée : elle formule des hypothèses
qui doivent être impérativement prouvées par des requêtes métriques, logs ou traces horodatées.]
```
