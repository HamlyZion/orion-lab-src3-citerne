# Rapport de Post-Mortem Blameless — Incident Orion

_Ce document suit la méthodologie d'analyse post-incident sans recherche de coupable (blameless). Il analyse les défaillances systémiques, les signaux de télémétrie et les processus de décision opérationnelle._

---

## 1. Informations générales et Rôles

| Information                     | Valeur                                |
| ------------------------------- | ------------------------------------- |
| **Groupe / Trinôme**            | `[Groupe 6]`                          |
| **Date et heure de l'incident** | `[2026-11-05 11:34 UTC]`              |
| **Durée totale de l'incident**  | `[52 minutes]`                        |
| **Incident Commander (IC)**     | `[Théo Rufin]`                        |
| **Mitigator**                   | `[Erwan BRONSIN]`                     |
| **Investigator(s)**             | `[Gilles NABAJOTH (et Pierre Feret)]` |

---

## 2. Résumé exécutif

_Description synthétique de l'incident, de la dégradation perçue par les utilisateurs (équipes Support, RH, Dev) et du rétablissement._

- **Symptôme utilisateur** : `[Erreurs HTTP 429 intermittentes sur les requêtes de l'équipe Support]`
- **SLO impacté** : `[Latence p95 pool bdd ]`
- **Impact métier** : `[0.7 rq/s du groupe support rejetées sur 1.25rq/s / Pas d'impact majeur sur la disponibilité]`

> **Rédacteur / Signature de la section**:`[Théo Rufin - IC]`

---

## 3. Chronologie des événements (Timeline)

_Cette chronologie doit être rigoureusement cohérente avec les événements horodatés dans`timeline.md`et le journal chiffré de votre session._

| Heure (UTC) | Acteur / Rôle | Événement / Action                               | Justification ou Preuve                                                                                                                                                                                                                                                                                                                                                        |
| ----------- | ------------- | ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `11:34:33`  | Système       | Déclenchement de la dégradation                  | Début de la hausse des erreurs 429                                                                                                                                                                                                                                                                                                                                             |
| `11:40:30`  | IC            | Déclaration formelle de l'incident               | Dégradation du SLO de qualité sur les questions de référence (< 90 %)                                                                                                                                                                                                                                                                                                          |
| `11:50:00`  | IC            | Déclaration formelle de l'incident               | Augmentation de requetes de l'équipe support et saturation du pool de connexion à la DB. Usage intensif de token et saturation de queue                                                                                                                                                                                                                                        |
| `11:51:01`  | Sytème        | Alerte déclenchée : OrionQuotaEquipeRejetsTicket | Rejets de quota (HTTP 429) pour l'équipe support                                                                                                                                                                                                                                                                                                                               |
| `11:56:31`  | Investigator  | Observation horodatée                            | Le quota de l'équipe support sur le nombre de requetes a explosé et génère un goulot d'étranglement sur les connexions à la database, dégradant la p95 du pool (`histogram_quantile(0.95, sum by (le) (rate(rag_db_pool_wait_seconds_bucket[5m]))) et sum by (team, backend) (rate(gateway_requests_total{team="support"}[5m]))`)                                              |
| `12:09:09`  | Mitigator     | Observation horodatée                            | Une explosion de requetes avec le code 429 car le quota de l'équipe support est épuisé (`sum(rate(traefik_service_requests_total{service="rag@file", code!="429"}[5m]))`)                                                                                                                                                                                                      |
| `12:09:09`  | Mitigator     | Action de mitigation exécutée                    | L'équipe support envoyait trop de requetes et a épuisé son quota. En exercant un refus de requetes venant de leur côté on soulage la base de données qui voyait la p95 du pool de connexion augmenter. (`histogram_quantile(0.95, sum by (le) (rate(rag_db_pool_wait_seconds_bucket[5m]))) et sum(rate(traefik_service_requests_total{service="rag@file", code!="429"}[5m]))`) |
| `12:24:58`  | IC            | Cause racine déclarée                            | Stabilisation vérifiée du SLI sous 1 % d'erreurs                                                                                                                                                                                                                                                                                                                               |
| `12:26:37`  | IC            | Clôture de l'incident                            | Levier appliqué, retour à l'état normal. Le nombre de requetes initiées par l'équipe support reste élevé mais cela sort du scope d'actions que nous pouvons mener                                                                                                                                                                                                              |

> **Rédacteur / Signature de la section**:`[Théo Rufin - IC]`

---

## 4. Signaux d'observabilité et démarche d'investigation

_Explicitez les méthodes retenues (USE, RED, Golden Signals) pour isoler le composant défaillant._

- **Méthode appliquée** : `[Aucune pure déduction logique]`
- **Signaux explorés** :
    1. _Métriques (Prometheus)_ : `sum by (team, backend) (rate(gateway_requests_total{team="support"}[5m])))` et `(sum(rate(traefik_service_requests_total{service="rag@file", code!="429"}[5m])))` ainsi que (`histogram_quantile(0.95, sum by (le) rate(rag_db_pool_wait_seconds_bucket[5m])))
    2. _Journaux (Loki)_ : `[Aucun trace_id avec un taux d'erreur révélateur d'une autre cause]`
    3. _Traces distribuées (Tempo)_ : `[Aucun span critique détécté]`

> **Rédacteur / Signature de la section**:`[Gilles NABAJOTH (et Pierre Feret) - Investigator]`

---

## 5. Actions de mitigation d'urgence et limites

_Décrivez les actions prises pour restaurer le service aux utilisateurs et leurs contreparties opérationnelles._

- **Action de mitigation appliquée** : `[Délestage de l'équipe support pour soulager la DB]`
- **Délai d'efficacité constaté** : `[Retour du SLI sous le seuil acceptable au bout de 2 minutes]`
- **Limites et effets de bord de cette mitigation** : `[Compromis dans l'utilisation du RAG pour l'équipe support, elle a du voir un nombre de requêtes tombés retourner une erreur avant même d'atteindre le RAG car l'api gateway gère le délestage]`

> **Rédacteur / Signature de la section**:`[Erwan BRONSIN - Mitigator]`

---

## 6. Cause racine prouvée par la télémétrie

_Formulez la cause racine exacte. Toute affirmation doit être étayée par une requête et un extrait probant issu de l'archive d'export._

- **Composant défaillant** : `[Service RAG et son pool de connexion à la DB trop solicité par l'afflux de rq depuis la gateway]`
- **Mécanisme de la panne** : `[Trop de requêtes en erreur 429 sont arrivées sur la gateway ce qui a provoqué une surcharge et a saturé la file d'attente de la DB. Cela a donc provoqué une hausse de latence de la DB]`
- **Requête de preuve irréfutable** :
    
    ```
   histogram_quantile(0.95, sum by (le) (rate(rag_db_pool_wait_seconds_bucket[5m])))
   sum by (team, backend) (rate(gateway_requests_total{team="support"}[5m]))
   sum(rate(traefik_service_requests_total{service="rag@file", code!="429"}[5m]))
    ```
    
- **Résultat observé / Extrait** :
    
    ```
    Voir le graph de débit de requetes Gateway par équipe / backend.
    Voir le graph cache embedding
    Voir le graph Erreur 5.. et rejets
    ```
    

> **Rédacteur / Signature de la section**:`[Gilles NABAJOTH (et Pierre Feret) - Investigator]`

---

## 7. Impact sur l'Error Budget

_Calculez l'impact réel de l'incident sur le budget d'erreurs mensuel de la plateforme._

- **SLO de référence** : `[> 90% de disponibilité sur 30 jours]`
- **Budget d'erreurs total sur 30 jours** : `10 % du volume total mensuel (~4320 minutes d'indisponibilité à 100 %)]`
- **Budget d'erreurs consommé par l'incident** : `[Aucune idée]`
- **Conséquence pour le cycle de déploiement** : `[Décision SRE : Augmentation de la latence des réponses du RAG sur la durée de l'incident, aucun impact majeur]`

> **Rédacteur / Signature de la section**:`[Théo Rufin- IC]`

---

## 8. Plan d'actions correctives et préventives (Blameless)

_Actions concrètes pour éviter la récurrence de la panne ou accélérer sa résolution._

| Action                                                                                                                       | Type (Prévention / Détection / Mitigation) | Priorité | Responsable proposé |
| ---------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ | -------- | ------------------- |
| `[Alerting dès le dépassement d'un seuil de requêtes défini pour les équipes]`                                               | Détection                                  | P1       | Équipe SRE          |
| `[Mise en place d'un circuit-breaker automatique sur la gateway pour éviter l'accumulation de requêtes en attente de la DB]` | Mitigation                                 | P2       | Équipe Dev Orion    |
| `[Rédaction d'un runbook d'intervention d'urgence]`                                                                          | Documentation                              | P3       | Équipe Support      |

> **Rédacteur / Signature de la section**:`[Erwan BRONSIN - Mitigator]`

---

## 9. Transposition sur Kubernetes

_Expliquez en 5 lignes comment cet incident serait détecté et traité dans un environnement Kubernetes managé par des Operators._

```
Pas vu en cours, le cours de kub est prévu pour le trimestre suivant. Nous n'avons pas les compétences pour répondre à cette question.
```

- **Manifeste associé** : adapter l'un des modèles fournis dans `as-code/k8s/` (`service-monitor.yaml` ou `prometheus-rule.yaml`) à la cible ou à la règle spécifique de votre incident, et le référencer ici.

> **Rédacteur / Signature de la section**:`[Tout le monde]`
