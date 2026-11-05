# Journal d'Usage des Assistants IA — Livrable Projet (1 Page)

*Ce document consigne et analyse avec esprit critique l'usage des assistants IA au cours des labs et du Game Day. Déclarer un usage n'entraîne aucune pénalité : c'est la rigueur de l'évaluation critique qui est notée.*

---

## 1. Assistants utilisés et périmètre d'usage

| Outil / Modèle | Interface | Périmètre (Labs 1 à 4, Game Day, Rédaction) | Rôle confié |
|---|---|---|---|
| Claude Opus 5.5 | Interface Web | Lab3 et 4b |   |
| `[Orion RCA (qwen3:1.7b)]` | CLI local (`make rca`) | Lab 4b & Game Day (incident en direct) | Génération d'hypothèses de cause racine assistée |

---

## 2. Tableau de bord des interactions et détection d'erreurs

| Contexte / Question posée | Apport réel de l'assistant | Erreur, hallucination ou limite constatée | Méthode de vérification humaine |
|---|---|---|---|
| formatage du code dans span_metier.py et aide à la reformulation des summary de rca | Aide mesurée sur la deuxième partie | limite car trop verbeux | réécriture synthétique |
| `make rca` effectué pour confirmer les premières intuitions et récupérer les commandes de preuve | Confirmation avec commande jointe | Pas d'erreur  | La cause réelle était en confiance medium, une erreur en high  | 

---

## 3. Analyse critique de l'outil de diagnostic local (`make rca`) au Game Day

*Évaluez objectivement les performances du modèle local compact (`qwen3:1.7b`) sur votre incident en direct.*

- **Hypothèses générées par le modèle local** :
  - *Hypothèse 1 (Rang 1)* : `postgres-link,duree requetes gateway par backend et route s'allonge,high`
  - *Hypothèse 2 (Rang 2)* : `postgres-link,attente pool de connexions SQL rag s'allonge,medium`
- **Pertinence et exactitude** : `L'hypothèse 2 ciblait le bon problème et le bon composant`
- **Qualité des requêtes de preuve suggérées** : `La requête PromQL issue du catalogue apportait la preuve du problème`
- **Observations sur les ressources et le temps de réponse** : `20.902s d'execution, prompt_eval_count: 1166  eval_count: 78`

---

## 4. Bilan réflexif : forces et limites de l'IA en exploitation SRE

*Synthèse en 5 à 10 lignes : ce que les assistants accélèrent efficacement face à ce qui exige obligatoirement une expertise humaine outillée.*

```text
Les outils IA utilisés ont surtout servis à des tâches de formatage, syntaxe et de test de diagnostic dans le cadre du cours avec RCA. Les tâches relevant de l'écriture de code / formatage 
de requêtes sont parfaitement adaptées aux outils car ils sont plus rapides qu'un humain sur un sujet qui n'a pas besoin d'une grande expertise métier dans sa rédaction. Cependant, 
concernant la qualité des diagnostics par RCA, le besoin de contexte et de cadrage est encore très important et n'a pas pu être mis en place de manière satisfaisante dans un temps restreint.
L'expertise humaine est encore aujourd'hui exigée pour le paramétrage de ces outils mais aussi pour la conception des systemes d'alerte et de monitoring bien que l'IA soit en mesure de
soulever des points d'étude pertinents
```
