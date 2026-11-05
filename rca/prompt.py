"""Formatage des prompts, paquet de preuves et catalogue Q1..Q8 (Lab 4b).

Conforme à l'ADR-004 (amendée G1 / T01c) et au §12 bis du contrat d'interfaces :
- Mode brut (raw) : preuves brutes complètes (~2 600 tokens)
- Mode résumé (pre_aggregated) : preuves calculées par Python sur le gabarit P3 (<= 450 tokens)
- Prompt total du mode résumé <= 850 tokens
- Catalogue Q1..Q8 compact injecté dans le prompt
- Aucune interprétation subjective écrite à la main
"""

from __future__ import annotations

import json
from typing import Any

try:
    from .models import CatalogueEntry, QueryId, RCAHypothesis, RCAModelOutput
except (ImportError, ValueError):
    from models import CatalogueEntry, QueryId, RCAHypothesis, RCAModelOutput

SYSTEM_PROMPT = """Tu es un ingenieur SRE analysant un incident sur la stack Orion.
Topologie et composants autorises (choisis uniquement parmi ces 7 identifiants) :
- gateway : proxy LLM (gateway-llm:8000, metriques gateway_*)
- rag : service applicatif POST /ask (orion-rag, stages embed/retrieval/prompt/generate, attente pool SQL)
- embed : vectorisation (/v1/embeddings, nominal < 0.15s)
- ollama : moteur LLM local reel
- simule : simulateur LLM (llm-simule:11435, generation chat nominale 1.2s a 2.0s)
- postgres-db : moteur SQL interne (temps_actif_sql_par_tx, seq_scan_documents ; nominal < 0.02s)
- postgres-link : liaison reseau TCP entre orion-rag et postgres:5432
Regle d'attribution : formule 2 hypotheses sur les seuls composants presentant un ecart franc par rapport au comportement nominal. Distingue le temps d'appel observe cote client (stage ou span sortant avec cible) du temps d'execution interne cote serveur : si l'appel vers une cible distante s'allonge alors que le serveur distant reste rapide en interne, incrimine la liaison reseau correspondante plutot que le serveur distant.
Reponds en JSON compact sur UNE SEULE LIGNE sans indentation ni parenthese (cause factuelle de 4 a 8 mots) :
{"hypotheses":[{"rank":1,"component":"<composant_1>","cause":"<4 a 8 mots sans parenthese>","query_id":"<Qn>","confidence":"high"},{"rank":2,"component":"<composant_2>","cause":"<4 a 8 mots sans parenthese>","query_id":"<Qm>","confidence":"medium"}]}"""


def build_catalogue(telemetry: dict[str, Any]) -> dict[QueryId, CatalogueEntry]:
    """Construit dynamiquement le catalogue Q1..Q8 de requêtes de preuve."""
    catalogue: dict[QueryId, CatalogueEntry] = {
        "Q1": {
            "signal": "metrics",
            "summary": "p95 rag_stage_duration_seconds par stage",
            "query": "histogram_quantile(0.95, sum by (le, stage) (rate(rag_stage_duration_seconds_bucket[5m])))",
        },
        "Q2": {
            "signal": "metrics",
            "summary": "p50 rag_stage_duration_seconds par stage",
            "query": "histogram_quantile(0.50, sum by (le, stage) (rate(rag_stage_duration_seconds_bucket[5m])))",
        },
        "Q3": {
            "signal": "metrics",
            "summary": "Temps actif SQL moyen par transaction sur postgres-db",
            "query": 'rate(pg_stat_database_active_time_seconds_total{datname="orion"}[5m]) / clamp_min(rate(pg_stat_database_xact_commit{datname="orion"}[5m]), 1e-6)',
        },
        "Q4": {
            "signal": "metrics",
            "summary": "p95 attente pool de connexions SQL rag",
            "query": "histogram_quantile(0.95, sum by (le) (rate(rag_db_pool_wait_seconds_bucket[5m])))",
        },
        "Q5": {
            "signal": "metrics",
            "summary": "Taux erreurs et requetes gateway par route et code",
            "query": "sum by (route, code) (rate(gateway_requests_total[5m]))",
        },
        "Q6": {
            "signal": "metrics",
            "summary": "p95 duree requetes gateway par backend et route",
            "query": "histogram_quantile(0.95, sum by (le, backend, route) (rate(gateway_request_duration_seconds_bucket[5m])))",
        },
        "Q7": {
            "signal": "logs",
            "summary": "Logs WARN/ERROR ou requetes lentes (> 2,5 s) sur rag et gateway",
            "query": '{service=~"rag|gateway"} | json | level=~"(?i)warn|error" or latency_ms > 2500',
        },
        "Q8": {
            "signal": "traces",
            "summary": "Traces lentes POST /ask (> 2,5 s) et spans enfants",
            "query": '{ name = "POST /ask" && duration > 2500ms }',
        },
    }
    return catalogue


def format_catalogue_for_prompt(catalogue: dict[QueryId, CatalogueEntry]) -> str:
    lines = ["Catalogue (Qn | signal | description) :"]
    for qid, entry in catalogue.items():
        lines.append(f"{qid} | {entry['signal']} | {entry['summary']}")
    lines.append(
        "JSON sur UNE LIGNE sans indentation ni parenthese (cause de 4 a 8 mots) :"
    )
    return "\n".join(lines)


def _scalar_value(series: list[dict[str, Any]]) -> float | None:
    if not series:
        return None
    raw = series[0].get("value", [0, None])[1]
    if raw is None:
        return None
    try:
        val = float(raw)
        return None if val != val else val
    except (TypeError, ValueError):
        return None


def format_evidence_pre_aggregated(telemetry: dict[str, Any]) -> str:
    """Génère le paquet de preuves résumé calculé par Python (<= 450 tokens).

    Synthèse objective des signaux collectés sans valeur inventée ni composant pré-désigné :
    1. Alertes actives
    2. Séries métriques clés mesurées
    3. Journaux récents (erreurs, avertissements ou requêtes lentes)
    4. Trace lente et spans les plus longs (avec adresse cible éventuelle)
    """
    alerts = telemetry.get("alerts", [])
    metrics = telemetry.get("metrics", {})
    logs = telemetry.get("logs", [])
    traces = telemetry.get("traces", [])

    lines = ["# Preuves resumees"]

    # 1. Alertes actives
    if alerts:
        alert_strs = []
        for a in alerts[:3]:
            name = a.get("name", "Alert")
            state = a.get("state", "firing")
            alert_strs.append(f"{name} ({state})")
        lines.append(f"1. Alertes : {', '.join(alert_strs)}.")
    else:
        lines.append("1. Alertes : aucune alerte active.")

    # 2. Séries métriques réellement mesurées
    series_desc: list[str] = []

    rate5m = _scalar_value(metrics.get("traefik_rate5m", []))
    err5xx = _scalar_value(metrics.get("traefik_errors5xx", []))
    if rate5m is not None or err5xx is not None:
        r_txt = f"{rate5m:.3f} req/s" if rate5m is not None else "n/a"
        e_txt = f"{err5xx:.4f} err/s" if err5xx is not None else "0.0000 err/s"
        series_desc.append(f"Trafic entree rag@file : debit={r_txt}, erreurs_5xx={e_txt}.")

    stage_p95: dict[str, float] = {}
    for r in metrics.get("rag_stage_p95", []):
        stg = r.get("metric", {}).get("stage")
        v = _scalar_value([r])
        if stg and v is not None:
            stage_p95[stg] = v
    if stage_p95:
        parts = [f"{k}={v:.3f}s" for k, v in sorted(stage_p95.items())]
        series_desc.append(f"Duree rag p95 par stage : {', '.join(parts)}.")

    pool_p95 = _scalar_value(metrics.get("rag_pool_wait_p95", []))
    if pool_p95 is not None:
        series_desc.append(f"Attente pool SQL cote rag p95 : {pool_p95:.3f}s.")

    pg_sql = _scalar_value(metrics.get("postgres_internal_sql", []))
    pg_seq = _scalar_value(metrics.get("postgres_seq_scan", []))
    if pg_sql is not None or pg_seq is not None:
        pg_parts = []
        if pg_sql is not None:
            pg_parts.append(f"temps_actif_sql_par_tx={pg_sql:.4f}s")
        if pg_seq is not None:
            pg_parts.append(f"seq_scan_documents={pg_seq:.3f}/s")
        series_desc.append(f"Mesures internes serveur postgres-db : {', '.join(pg_parts)}.")

    gw_parts = []
    for r in metrics.get("gateway_duration_p95", []):
        backend = r.get("metric", {}).get("backend", "?")
        route = r.get("metric", {}).get("route", "?")
        v = _scalar_value([r])
        if v is not None:
            gw_parts.append(f"{backend}:{route}={v:.3f}s")
    if gw_parts:
        series_desc.append(f"Duree gateway p95 : {', '.join(gw_parts[:4])}.")

    lines.append("2. Metriques :")
    if series_desc:
        for s in series_desc:
            lines.append(f"- {s}")
    else:
        lines.append("- aucune serie metrique disponible.")

    # 3. Logs pertinents
    log_summaries: list[str] = []
    for entry in logs[:2]:
        svc = entry.get("service", "unknown")
        raw_line = str(entry.get("line", "")).strip()
        try:
            parsed = json.loads(raw_line)
            lvl = parsed.get("level", "")
            code = parsed.get("status_code", "")
            lat = parsed.get("latency_ms", "")
            msg = str(parsed.get("msg", ""))[:60]
            log_summaries.append(f"{svc}[{lvl}] status={code} latency_ms={lat} {msg}".strip())
        except Exception:
            cleaned = raw_line.replace("{", "").replace("}", "").strip()[:100]
            log_summaries.append(f"{svc}: {cleaned}")
    if log_summaries:
        lines.append(f"3. Logs recents : {' ; '.join(log_summaries)}.")
    else:
        lines.append("3. Logs recents : aucun log WARN/ERROR ni requete lente.")

    # 4. Trace lente et spans triés par durée décroissante
    slow_trace = traces[0] if traces else None
    if slow_trace:
        dur = slow_trace.get("duration_ms", 0)
        spans = sorted(
            slow_trace.get("spans", []),
            key=lambda sp: float(sp.get("duration_ms", 0) or 0),
            reverse=True,
        )
        span_desc = []
        for sp in spans[:11]:
            sp_name = sp.get("name") or "span"
            sp_svc = sp.get("service") or "?"
            sp_dur = float(sp.get("duration_ms", 0) or 0)
            peer_addr = sp.get("peer_address")
            peer_port = sp.get("peer_port")
            target_str = f" cible={peer_addr}:{peer_port}" if peer_addr else ""
            span_desc.append(f"{sp_svc}/{sp_name}={sp_dur:.1f}ms{target_str}")
        span_details = ", ".join(span_desc) if span_desc else "aucun span detaille"
        lines.append(f"4. Trace lente ({int(dur)}ms) : {span_details}.")
    else:
        lines.append("4. Trace : aucune trace lente detectee.")

    return "\n".join(lines)


def format_evidence_raw(telemetry: dict[str, Any]) -> str:
    """Génère le paquet de preuves brut complet (~2 600 tokens, compatible num_ctx=4096)."""
    alerts = telemetry.get("alerts", [])[:5]
    compact_metrics: dict[str, list[dict[str, Any]]] = {}
    for key, series_list in telemetry.get("metrics", {}).items():
        cleaned_series = []
        for item in (series_list or [])[:12]:
            raw_val = item.get("value", [0, None])[1]
            try:
                val_out: Any = round(float(raw_val), 4)
            except (TypeError, ValueError):
                val_out = raw_val
            cleaned_series.append({
                "metric": item.get("metric", {}),
                "value": val_out,
            })
        compact_metrics[key] = cleaned_series

    logs = [
        {"service": l.get("service"), "line": str(l.get("line", ""))[:160]}
        for l in telemetry.get("logs", [])[:6]
    ]
    compact_traces = []
    for t in telemetry.get("traces", [])[:2]:
        sorted_spans = sorted(
            t.get("spans", []),
            key=lambda s: float(s.get("duration_ms", 0) or 0),
            reverse=True,
        )
        compact_traces.append({
            "trace_id": t.get("trace_id"),
            "duration_ms": t.get("duration_ms"),
            "root": t.get("root"),
            "spans": [
                {
                    "name": s.get("name"),
                    "service": s.get("service"),
                    "duration_ms": s.get("duration_ms"),
                    "peer_address": s.get("peer_address"),
                    "peer_port": s.get("peer_port"),
                }
                for s in sorted_spans[:11]
            ],
        })

    metric_lines = [
        f"  {k}: {json.dumps(v, ensure_ascii=False, separators=(',', ':'))}"
        for k, v in compact_metrics.items()
    ]
    log_lines = [
        f"  {json.dumps(entry, ensure_ascii=False, separators=(',', ':'))}"
        for entry in logs
    ]
    trace_lines = [
        f"  {json.dumps(tr, ensure_ascii=False, separators=(',', ':'))}"
        for tr in compact_traces
    ]

    lines = [
        "# Paquet de preuves brut",
        f"Horodatage de collecte : {telemetry.get('timestamp')}",
        "\n## 1. Alertes actives (Prometheus)",
        json.dumps(alerts, ensure_ascii=False, separators=(",", ":")),
        "\n## 2. Metriques d'observabilite cles (Prometheus)",
        "\n".join(metric_lines) if metric_lines else "  {}",
        "\n## 3. Logs recents (Loki)",
        "\n".join(log_lines) if log_lines else "  []",
        "\n## 4. Traces distribuees lentes (Tempo)",
        "\n".join(trace_lines) if trace_lines else "  []",
    ]
    return "\n".join(lines)


def build_prompt_messages(
    telemetry: dict[str, Any],
    mode: str = "raw",
) -> tuple[list[dict[str, str]], dict[QueryId, CatalogueEntry]]:
    """Construit la liste des messages pour l'appel Ollama /api/chat."""
    catalogue = build_catalogue(telemetry)
    cat_str = format_catalogue_for_prompt(catalogue)

    if mode == "pre_aggregated":
        evidence_str = format_evidence_pre_aggregated(telemetry)
    else:
        evidence_str = format_evidence_raw(telemetry)

    user_content = f"{evidence_str}\n\n{cat_str}"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    return messages, catalogue


build_dynamic_catalogue = build_catalogue


def build_evidence_packet(telemetry: dict[str, Any], mode: str = "raw") -> str:
    """Construit la chaîne de preuves selon le mode demandé."""
    if mode == "pre_aggregated":
        return format_evidence_pre_aggregated(telemetry)
    return format_evidence_raw(telemetry)


def build_prompt(
    evidence_packet: str,
    mode: str = "raw",
    dynamic_catalogue: dict[QueryId, CatalogueEntry] | None = None,
) -> tuple[str, str]:
    """Construit le couple (system_prompt, user_prompt)."""
    cat = dynamic_catalogue or {}
    cat_str = format_catalogue_for_prompt(cat)
    user_prompt = f"{evidence_packet}\n\n{cat_str}"
    return SYSTEM_PROMPT, user_prompt


def rehydrate_report(
    model_output: RCAModelOutput,
    catalogue: dict[QueryId, CatalogueEntry],
) -> list[RCAHypothesis]:
    """Réhydrate les hypothèses du modèle avec les détails des requêtes de preuve."""
    rehydrated: list[RCAHypothesis] = []
    for hyp in model_output.hypotheses:
        entry = catalogue.get(hyp.query_id, {})
        rehydrated.append(
            RCAHypothesis(
                rank=hyp.rank,
                component=hyp.component,
                cause=hyp.cause,
                query_id=hyp.query_id,
                signal_type=entry.get("signal", ""),
                proof_query=entry.get("query", ""),
                confidence=hyp.confidence,
                verdict="",
            )
        )
    return rehydrated

