"""Point d'entrée de l'outil de RCA Orion (ADR-004, §12 bis).

Lancé par `make rca` via le profil Compose `rca` :
`docker compose --profile rca run --rm rca`
"""

from __future__ import annotations

import argparse
import datetime
import logging
import os
import sys
from pathlib import Path
from typing import Any

import yaml

try:
    from .collect import DeterministicCollector
    from .lease import GatewayLease
    from .models import RCAHypothesis, RCAOutputReport
    from .ollama_client import OllamaClientError, OllamaRCAClient
    from .prompt import (
        build_dynamic_catalogue,
        build_evidence_packet,
        build_prompt,
        rehydrate_report,
    )
except (ImportError, ValueError):
    from collect import DeterministicCollector
    from lease import GatewayLease
    from models import RCAHypothesis, RCAOutputReport
    from ollama_client import OllamaClientError, OllamaRCAClient
    from prompt import (
        build_dynamic_catalogue,
        build_evidence_packet,
        build_prompt,
        rehydrate_report,
    )

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("orion.rca")


def determine_output_path(cli_path: str | None = None) -> Path:
    """Détermine le chemin où écrire rca.yaml."""
    if cli_path:
        return Path(cli_path)
    env_path = os.environ.get("ORION_RCA_OUTPUT_PATH")
    if env_path:
        return Path(env_path)
    # Dans le conteneur rca, /exports est monté vers ../exports/rca
    if Path("/exports").is_dir():
        return Path("/exports/rca.yaml")
    # Sur l'hôte, exports/rca/rca.yaml ou ./rca.yaml
    if Path("exports/rca").is_dir():
        return Path("exports/rca/rca.yaml")
    return Path("rca.yaml")


def host_path(path: Path) -> str:
    """Chemin à afficher : /exports du conteneur correspond à exports/rca/ dans le dépôt."""
    try:
        return str(Path("exports/rca") / path.relative_to("/exports"))
    except ValueError:
        return str(path)


def format_report_yaml(report: RCAOutputReport) -> str:
    """Formate le rapport en YAML propre et lisible avec commentaires pour l'étudiant."""
    data = {
        "generated_at": report.generated_at,
        "mode": report.mode,
        "model": report.model,
        "actual_duration_s": report.actual_duration_s,
        "token_usage": {
            "prompt_eval_count": report.metadata.get("prompt_eval_count", 0),
            "eval_count": report.metadata.get("eval_count", 0),
        },
        "hypotheses": [],
    }

    for hyp in report.hypotheses:
        comp_val = hyp.component.value if hasattr(hyp.component, "value") else str(hyp.component)
        conf_val = hyp.confidence.value if hasattr(hyp.confidence, "value") else str(hyp.confidence)
        hyp_dict = {
            "rank": hyp.rank,
            "component": comp_val,
            "cause": hyp.cause,
            "query_id": hyp.query_id,
            "signal_type": hyp.signal_type or "",
            "proof_query": hyp.proof_query or "",
            "confidence": conf_val,
            "verdict": hyp.verdict or "",  # À remplir par l'étudiant : juste | fausse | hallucinee
        }
        data["hypotheses"].append(hyp_dict)

    header = (
        "# Rapport d'analyse de cause racine (RCA) Orion - Lab 4b\n"
        "#\n"
        "# INSTRUCTIONS POUR L'ÉTUDIANT :\n"
        "# 1. Examinez les hypothèses proposées ci-dessous et rejouez les requêtes de preuve\n"
        "#    (proof_query) dans Grafana Explore (Prometheus, Loki ou Tempo).\n"
        "# 2. Après révélation de l'incident, renseignez le champ 'verdict' pour chaque hypothèse :\n"
        "#    - 'juste'       : composant et cause corrects étayés par la télémétrie\n"
        "#    - 'fausse'      : hypothèse erronée ou non pertinente\n"
        "#    - 'hallucinee'  : cause inventée, non étayée par les métriques ou signal absent\n"
        "# 3. Ce fichier sera vérifié par 'make check-lab4b PIN=ABCD ETU=20260001' (ETU = votre numéro étudiant).\n\n"
    )

    yaml_str = yaml.dump(data, sort_keys=False, allow_unicode=True, width=120)
    return header + yaml_str


def run() -> int:
    parser = argparse.ArgumentParser(description="Outil de RCA Orion (Lab 4b)")
    parser.add_argument(
        "--mode",
        choices=["raw", "pre_aggregated"],
        default=os.environ.get("ORION_RCA_MODE", "raw"),
        help="Mode de paquet de preuves (raw ou pre_aggregated)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Chemin du fichier rca.yaml de sortie",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=os.environ.get("ORION_RCA_MODEL", "qwen3:1.7b"),
        help="Nom du modèle Ollama",
    )
    parser.add_argument(
        "--skip-lease",
        action="store_true",
        help="Ignorer le bail de suspension (développement hors stack complète)",
    )

    args = parser.parse_args()

    mode = args.mode
    output_path = determine_output_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print(f"🚀 Démarrage de l'analyse RCA Orion (Mode: {mode}, Modèle: {args.model})")
    print("=" * 70)

    # 1. Collecte déterministe
    print("\n[1/5] 📡 Collecte déterministe de la télémétrie (Prometheus, Loki, Tempo)...")
    collector = DeterministicCollector()
    telemetry_data = collector.collect_all()

    # 2. Construction du catalogue de requêtes Q1..Q8
    print("\n[2/5] 📋 Construction du catalogue dynamique de preuves Q1..Q8...")
    catalogue = build_dynamic_catalogue(telemetry_data)
    print(f"       -> {len(catalogue)} requêtes de preuve cataloguées.")

    # 3. Construction du paquet de preuves et du prompt
    print(f"\n[3/5] 📝 Formatage du paquet de preuves ({mode})...")
    evidence = build_evidence_packet(telemetry_data, mode=mode)
    system_prompt, user_prompt = build_prompt(
        evidence_packet=evidence,
        mode=mode,
        dynamic_catalogue=catalogue,
    )
    evidence_tokens_est = len(evidence) // 4
    prompt_tokens_est = (len(system_prompt) + len(user_prompt)) // 4
    print(f"       -> Taille estimée prompt : ~{prompt_tokens_est} tokens (preuves : ~{evidence_tokens_est} tokens)")

    # 4. Prise de bail de suspension et appel Ollama
    print("\n[4/5] 🔒 Gestion du bail de suspension de la gateway et inférence Ollama...")
    client = OllamaRCAClient(model=args.model)

    gateway_url = os.environ.get("GATEWAY_INTERNAL_URL", "http://gateway:8090")
    lease_cm = GatewayLease(gateway_internal_url=gateway_url)

    parsed_output = None
    meta: dict[str, Any] = {}

    start_time = datetime.datetime.now(datetime.timezone.utc)

    # Bloc try / finally strict pour garantir la libération du bail (§4 bis)
    try:
        if not args.skip_lease:
            print("       -> Prise du bail de suspension sur la gateway...")
            lease_cm.__enter__()
            print(f"       -> Bail acquis (ID: {lease_cm.lease_id}). Routage réel suspendu.")

        print("       -> Appel direct Ollama (think: false, format contraint)...")
        parsed_output, meta = client.call_rca(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_name=args.model,
        )
        print("       -> Réponse reçue et validée par le schéma Pydantic.")

    finally:
        if not args.skip_lease and lease_cm.active:
            print("       -> Libération du bail de suspension...")
            lease_cm.__exit__(None, None, None)
            print("       -> Bail libéré. Routage réel repris.")

    duration_s = meta.get("total_duration_seconds", (datetime.datetime.now(datetime.timezone.utc) - start_time).total_seconds())

    # 5. Réhydratation et génération de rca.yaml
    print(f"\n[5/5] 💾 Réhydratation des requêtes de preuve et écriture de {host_path(output_path)}...")
    rehydrated_hypotheses = rehydrate_report(parsed_output, catalogue)

    report = RCAOutputReport(
        generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        mode=mode,
        model=args.model,
        actual_duration_s=duration_s,
        hypotheses=rehydrated_hypotheses,
        metadata=meta,
    )

    yaml_content = format_report_yaml(report)
    try:
        output_path.write_text(yaml_content, encoding="utf-8")
    except PermissionError:
        output_path.unlink(missing_ok=True)
        output_path.write_text(yaml_content, encoding="utf-8")
    try:
        os.chmod(output_path, 0o666)
    except OSError:
        pass
    print(f"       -> Rapport généré avec succès dans {host_path(output_path)} ({duration_s}s)")

    # Affichage du résumé pour les étudiants
    print("\n" + "=" * 70)
    print("🎯 RÉSULTATS DE L'ANALYSE RCA :")
    for hyp in rehydrated_hypotheses:
        comp_str = hyp.component.value if hasattr(hyp.component, "value") else str(hyp.component)
        conf_str = hyp.confidence.value if hasattr(hyp.confidence, "value") else str(hyp.confidence)
        print(f"\n  [Hypothèse #{hyp.rank}] Composant suspect : {comp_str}")
        print(f"    Cause identifiée : {hyp.cause}")
        print(f"    Confiance        : {conf_str}")
        print(f"    Preuve requise   : [{hyp.query_id}] ({hyp.signal_type}) {hyp.proof_query}")
    print("\n" + "=" * 70)
    print(f"👉 N'oubliez pas d'examiner {host_path(output_path)} et de renseigner le champ 'verdict'.\n")

    return 0


if __name__ == "__main__":
    sys.exit(run())
