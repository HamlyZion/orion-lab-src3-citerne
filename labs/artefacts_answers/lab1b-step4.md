# Audit critique d'un artefact généré par un assistant

## Erreur 1
```
- record: backend:orion_gateway_latency_p95:rate5m
  expr: |
    histogram_quantile(
      0.95,
      sum by (backend) (rate(gateway_request_duration_seconds_bucket[5m]))
    )
```
Erreur d'aggrégagtion, l'histogram_quantile doit se calculer avec la somme "(le,backend)"

## Erreur 2
```
backend:orion_gateway_latency_p95:rate3m > 2.5
and
backend:orion_gateway_latency_p95:rate5m > 2.5
```
Erreur de seuil par backend, on récupère les deux backend (ollama et simulé) et on applique le 
même seuil de SLO aux deux, (2,5s) ce qui générerait des alertes perpétuelles 

## Erreur 3
Erreur de garde de volume, aucune garde présente avant alerte, une seule requête échouée génère une alerte

## Erreur 4
Choix des fenêtres : 3m et 5m
Le temps choisi n'est pas pertinent, la règle sur 5 minutes existe déjà et 3 minutes est une fenêtre trop courte

## Erreur 5
Clause for:
La clause for est à 10 minutes avec des fenêtres à 3 et 5 minutes. L'actualisation se fait tout les 2 cycles minimum
donc on perd la pertinence de l'information
