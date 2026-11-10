# Observabilité « As Code » — Gabarit du livrable

Ce dossier fournit l'arborescence et les modèles de référence pour la remise de la composante « Observabilité as Code » du projet Orion.

---

## 1. Arborescence attendue

```text
as-code/
├── README.md                 # Vos justifications d'ingénierie et arbitrages
├── rules/                    # Règles d'enregistrement et d'alerte Prometheus
│   ├── recording-rules.yml   # Calculs des SLI et taux d'erreurs
│   └── alerting-rules.yml    # Alertes multi-fenêtres de burn rate
├── tests/                    # Tests unitaires promtool
│   └── test_rules.yml        # Scénarios de tests vérifiés par promtool test rules
├── dashboards/               # Tableaux de bord exportés en JSON
│   ├── red-overview.json     # Dashboard RED de la passerelle
│   └── logs-investigation.json
├── alloy/                    # Pipeline de télémétrie Grafana Alloy
│   └── config.alloy          # Configuration du masquage et de l'ingestion Loki
└── k8s/                      # Transposition Kubernetes (Prometheus Operator)
    ├── service-monitor.yaml  # Exemple commenté adapté à votre cible
    └── prometheus-rule.yaml  # Exemple commenté adapté à votre alerte
```

---

## 2. Commandes de validation locale

Vos règles doivent être rigoureusement syntaxées et testées avant remise :

```bash
# 1. Vérification syntaxique des règles
docker run --rm -v "$(pwd)/rules:/rules" prom/prometheus:v3.13.5 \
  promtool check rules /rules/recording-rules.yml /rules/alerting-rules.yml

# 2. Exécution des tests unitaires
docker run --rm -v "$(pwd)/rules:/rules" -v "$(pwd)/tests:/tests" prom/prometheus:v3.13.5 \
  promtool test rules /tests/test_rules.yml
```

---

## 3. Justifications d'ingénierie (Arbitrages sous contraintes)

*Remplissez les trois sections ci-dessous pour expliciter vos choix d'architecture.*

### Arbitrage 1 : Objectif de SLO recommandé pour Nordel
- **Objectif cible recommandé** : `[Ex. 99,5 % sur 30 jours mobiles]`
- **Justification économique et opérationnelle** : `[La platform est destinée a des services non critique ce qui implique qu'une dispo de 99,5% peut suffire]`
- **Choix des fenêtres d'alerte** : `[Comparez les fenêtres de salle de cours (8 min / 40 s) aux fenêtres recommandées en production (1 h / 5 min et 6 h / 30 min) selon le Google SRE Workbook]`

### Arbitrage 2 : Cardinalité des labels et flux Loki (Budget 1 000 flux)
- **Labels indexés retenus** : `[<service>, <team>, <level>]`
- **Champs relégués en structured metadata ou contenu** : `[<trace_id>, <span_id>, <version>]`
- **Démonstration du respect du budget** : `[Montrez comment le produit cartésien de vos labels reste très inférieur au plafond de 1 000 flux configuré sur Loki]`

### Arbitrage 3 : Politique de masquage et confidentialité (RGPD / RH)
- **Motifs masqués à la source dans Alloy** : `[Détaillez les expressions régulières pour les clés d'API sk-nordel-* et adresses e-mail]`
- **Arbitrage sur la conservation des prompts applicatifs** : `[Justifiez si vous capturez l'intégralité du texte des questions utilisateurs ou uniquement les métadonnées de taille/tokens, compte tenu des risques de fuite de données personnelles]`
