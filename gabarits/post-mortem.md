# Rapport de Post-Mortem Blameless — Incident Orion

*Ce document suit la méthodologie d'analyse post-incident sans recherche de coupable (blameless). Il analyse les défaillances systémiques, les signaux de télémétrie et les processus de décision opérationnelle.*

---

## 1. Informations générales et Rôles

| Information | Valeur |
|---|---|
| **Groupe / Trinôme** | `[Ex. Groupe 4]` |
| **Date et heure de l'incident** | `[YYYY-MM-DD HH:MM UTC]` |
| **Durée totale de l'incident** | `[Ex. 32 minutes]` |
| **Incident Commander (IC)** | `[Prénom NOM]` |
| **Mitigator** | `[Prénom NOM]` |
| **Investigator(s)** | `[Prénom NOM (et Prénom NOM si 4 étudiants)]` |

---

## 2. Résumé exécutif
*Description synthétique de l'incident, de la dégradation perçue par les utilisateurs (équipes Support, RH, Dev) et du rétablissement.*

- **Symptôme utilisateur** : `[Ex. Erreurs HTTP 500 intermittentes sur les requêtes de l'équipe Support]`
- **SLO impacté** : `[Disponibilité / Latence p95 / Fraîcheur / Qualité]`
- **Impact métier** : `[Volume de requêtes en échec, durée de violation du seuil critique]`

> **Rédacteur / Signature de la section** : `[Prénom NOM - Rôle]`

---

## 3. Chronologie des événements (Timeline)
*Cette chronologie doit être rigoureusement cohérente avec les événements horodatés dans `timeline.md` et le journal chiffré de votre session.*

| Heure (UTC) | Acteur / Rôle | Événement / Action | Justification ou Preuve |
|---|---|---|---|
| `14:02:10` | Système | Déclenchement de la dégradation | Début de la hausse des erreurs 5xx |
| `14:04:30` | IC | Déclaration formelle de l'incident | Alerte active sur la disponibilité |
| `14:08:15` | Investigator | Première observation horodatée | `sum(rate(rag_requests_total{code=~"5.."}[1m])) > 0` |
| `14:11:00` | Mitigator | Application de la mitigation d'urgence | Activation du mode dégradé |
| `14:15:20` | Investigator | Diagnostic et corrélation de traces | Corrélation par trace_id sur le composant dégradé |
| `14:26:45` | IC | Déclaration de la cause racine | Requête SQL / LogQL confirmant la panne |
| `14:31:00` | IC | Clôture de l'incident et export | Stabilisation vérifiée du SLI sous 1 % d'erreurs |

> **Rédacteur / Signature de la section** : `[Prénom NOM - Rôle]`

---

## 4. Signaux d'observabilité et démarche d'investigation
*Explicitez les méthodes retenues (USE, RED, Golden Signals) pour isoler le composant défaillant.*

- **Méthode appliquée** : `[Expliquez pourquoi vous avez suivi RED sur les services et USE sur les ressources]`
- **Signaux explorés** :
  1. *Métriques (Prometheus)* : `[Requêtes PromQL exécutées et analyse des courbes]`
  2. *Journaux (Loki)* : `[Requêtes LogQL, corrélation avec trace_id et niveau d'erreur]`
  3. *Traces distribuées (Tempo)* : `[Spans critiques, analyse des latences par étape ou des codes de statut]`

> **Rédacteur / Signature de la section** : `[Prénom NOM - Rôle]`

---

## 5. Actions de mitigation d'urgence et limites
*Décrivez les actions prises pour restaurer le service aux utilisateurs et leurs contreparties opérationnelles.*

- **Action de mitigation appliquée** : `[Ex. Activation du mode dégradé, délestage d'une équipe, ajustement de paramètre]`
- **Délai d'efficacité constaté** : `[Délai entre l'exécution et le retour du SLI sous le seuil acceptable]`
- **Limites et effets de bord de cette mitigation** : `[Ex. En mode dégradé, les documents sont servis sans génération LLM finale ; compromis qualité vs disponibilité]`

> **Rédacteur / Signature de la section** : `[Prénom NOM - Rôle]`

---

## 6. Cause racine prouvée par la télémétrie
*Formulez la cause racine exacte. Toute affirmation doit être étayée par une requête et un extrait probant issu de l'archive d'export.*

- **Composant défaillant** : `[Nom exact du composant architectural]`
- **Mécanisme de la panne** : `[Explication technique détaillée du dysfonctionnement]`
- **Requête de preuve irréfutable** :
  ```promql
  [Collez ici la requête exacte PromQL, LogQL, TraceQL ou SQL ayant permis de prouver la cause]
  ```
- **Résultat observé / Extrait** :
  ```text
  [Collez l'extrait textuel ou la métrique chiffrée issue de votre export confirmant la preuve]
  ```

> **Rédacteur / Signature de la section** : `[Prénom NOM - Rôle]`

---

## 7. Impact sur l'Error Budget
*Calculez l'impact réel de l'incident sur le budget d'erreurs mensuel de la plateforme.*

- **SLO de référence** : `[Ex. 99,5 % de disponibilité sur 30 jours]`
- **Budget d'erreurs total sur 30 jours** : `[Ex. 0,5 % du volume total mensuel (~216 minutes d'indisponibilité à 100 %)]`
- **Budget d'erreurs consommé par l'incident** : `[Détail du calcul : taux d'erreurs moyen pendant l'incident × durée]`
- **Conséquence pour le cycle de déploiement** : `[Décision SRE : gel des déploiements non critiques, priorisation de la résilience, ou maintien du rythme]`

> **Rédacteur / Signature de la section** : `[Prénom NOM - Rôle]`

---

## 8. Plan d'actions correctives et préventives (Blameless)
*Actions concrètes pour éviter la récurrence de la panne ou accélérer sa résolution.*

| Action | Type (Prévention / Détection / Mitigation) | Priorité | Responsable proposé |
|---|---|---|---|
| `[Ex. Ajout d'une sonde de disponibilité sur le service]` | Détection | P1 | Équipe SRE |
| `[Ex. Mise en place d'un circuit-breaker automatique]` | Mitigation | P2 | Équipe Dev Orion |
| `[Ex. Rédaction d'un runbook d'intervention d'urgence]` | Documentation | P3 | Équipe Support |

> **Rédacteur / Signature de la section** : `[Prénom NOM - Rôle]`

---

## 9. Transposition sur Kubernetes
*Expliquez en 5 lignes comment cet incident serait détecté et traité dans un environnement Kubernetes managé par des Operators.*

```text
[Rédigez ici vos 5 lignes d'analyse : déploiement sous forme de Pods/Deployments, découverte dynamique
via ServiceMonitor du Prometheus Operator, corrélation par les métadonnées Kubernetes (namespace, pod),
et mitigation automatisée par probes de liveness/readiness ou HPA.]
```

- **Manifeste associé** : adapter l'un des modèles fournis dans `as-code/k8s/` (`service-monitor.yaml` ou `prometheus-rule.yaml`) à la cible ou à la règle spécifique de votre incident, et le référencer ici.

> **Rédacteur / Signature de la section** : `[Prénom NOM - Rôle]`
