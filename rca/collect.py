"""Collecte déterministe multi-signaux pour l'outil de RCA (Lab 4b).

Interroge :
- Prometheus : alertes actives et séries métriques clés (RED / USE)
- Loki : logs d'erreur et avertissements récents
- Tempo : traces lentes et attributs de spans (ex. server.address sur liaisons)
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

logger = logging.getLogger("orion-rca.collect")


class TelemetryCollector:
    """Collecteur des signaux d'observabilité d'Orion."""

    def __init__(
        self,
        prom_url: str | None = None,
        loki_url: str | None = None,
        tempo_url: str | None = None,
    ) -> None:
        self.prom_url = (prom_url or os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")).rstrip("/")
        self.loki_url = (loki_url or os.environ.get("LOKI_URL", "http://loki:3100")).rstrip("/")
        self.tempo_url = (tempo_url or os.environ.get("TEMPO_URL", "http://tempo:3200")).rstrip("/")

    def collect_alerts(self, client: httpx.Client) -> list[dict[str, Any]]:
        """Collecte les alertes en cours d'évaluation ou actives."""
        try:
            resp = client.get(f"{self.prom_url}/api/v1/alerts", timeout=5.0)
            if resp.status_code == 200:
                data = resp.json().get("data", {}).get("alerts", [])
                return [
                    {
                        "name": a.get("labels", {}).get("alertname", "UnknownAlert"),
                        "state": a.get("state"),
                        "labels": a.get("labels", {}),
                        "annotations": a.get("annotations", {}),
                        "activeAt": a.get("activeAt"),
                        "value": a.get("value"),
                    }
                    for a in data
                    if a.get("state") in ("firing", "pending")
                ]
        except Exception as exc:
            logger.warning("Échec collecte alertes Prometheus : %s", exc)
        return []

    def query_prom_instant(self, client: httpx.Client, query: str) -> list[dict[str, Any]]:
        """Exécute une requête PromQL instantanée."""
        try:
            resp = client.get(f"{self.prom_url}/api/v1/query", params={"query": query}, timeout=6.0)
            if resp.status_code == 200:
                payload = resp.json()
                if payload.get("status") == "success":
                    return payload.get("data", {}).get("result", [])
        except Exception as exc:
            logger.debug("Échec requête PromQL '%s' : %s", query, exc)
        return []

    def collect_key_metrics(self, client: httpx.Client) -> dict[str, Any]:
        """Collecte les séries temporelles clés pour le diagnostic."""
        queries = {
            "traefik_rate5m": 'sum(rate(traefik_service_requests_total{service="rag@file", code!="429"}[5m]))',
            "traefik_errors5xx": 'sum(rate(traefik_service_requests_total{service="rag@file", code=~"5.."}[5m]))',
            "rag_stage_p95": 'histogram_quantile(0.95, sum by (le, stage) (rate(rag_stage_duration_seconds_bucket[5m])))',
            "rag_stage_p50": 'histogram_quantile(0.50, sum by (le, stage) (rate(rag_stage_duration_seconds_bucket[5m])))',
            "gateway_duration_p95": 'histogram_quantile(0.95, sum by (le, backend, route) (rate(gateway_request_duration_seconds_bucket[5m])))',
            "gateway_attempts": 'sum by (backend, outcome) (rate(gateway_backend_attempts_total[5m]))',
            "gateway_queue_depth": 'gateway_queue_depth',
            "rag_pool_wait_p95": 'histogram_quantile(0.95, sum by (le) (rate(rag_db_pool_wait_seconds_bucket[5m])))',
            "postgres_internal_sql": 'rate(pg_stat_database_active_time_seconds_total{datname="orion"}[5m]) / clamp_min(rate(pg_stat_database_xact_commit{datname="orion"}[5m]), 1e-6)',
            "postgres_seq_scan": 'rate(pg_stat_user_tables_seq_scan{datname="orion",relname="documents"}[5m])',
        }

        results: dict[str, Any] = {}
        for key, q in queries.items():
            results[key] = self.query_prom_instant(client, q)
        return results

    def collect_recent_logs(self, client: httpx.Client, limit: int = 15) -> list[dict[str, Any]]:
        """Collecte les logs WARN/ERROR ou requêtes lentes récents depuis Loki."""
        logql = '{service=~"rag|gateway|worker"} | json | level=~"(?i)warn|error" or latency_ms > 2500'
        now_ns = time.time_ns()
        start_ns = now_ns - (5 * 60 * 1_000_000_000)  # 5 minutes

        try:
            resp = client.get(
                f"{self.loki_url}/loki/api/v1/query_range",
                params={"query": logql, "start": str(start_ns), "end": str(now_ns), "limit": limit},
                timeout=6.0,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", {}).get("result", [])
                extracted = []
                for stream in data:
                    svc = stream.get("stream", {}).get("service", "unknown")
                    for entry in stream.get("values", []):
                        ts_ns, line = entry[0], entry[1]
                        extracted.append({"ts": ts_ns, "service": svc, "line": line})
                return extracted[:limit]
        except Exception as exc:
            logger.debug("Échec collecte logs Loki : %s", exc)
        return []

    def collect_slow_traces(
        self,
        client: httpx.Client,
        limit: int = 5,
        min_duration: str = "2500ms",
    ) -> list[dict[str, Any]]:
        """Recherche uniquement les traces lentes dans Tempo et trie leurs spans par durée décroissante."""
        now_s = int(time.time())
        start_s = now_s - 300  # 5 minutes

        traces = []
        try:
            resp = client.get(
                f"{self.tempo_url}/api/search",
                params={
                    "q": f'{{ name = "POST /ask" && duration > {min_duration} }}',
                    "minDuration": min_duration,
                    "start": start_s,
                    "end": now_s,
                    "limit": max(limit * 4, 20),
                },
                timeout=6.0,
            )
            if resp.status_code == 200:
                raw_traces = sorted(
                    resp.json().get("traces", []),
                    key=lambda item: float(item.get("durationMs", 0) or 0),
                    reverse=True,
                )
                for t in raw_traces[:limit]:
                    trace_id = t.get("traceID")
                    duration_ms = t.get("durationMs", 0)
                    root_name = (t.get("rootServiceName", "") + " " + t.get("rootTraceName", "")).strip()
                    spans_summary = []

                    if trace_id:
                        detail_resp = client.get(f"{self.tempo_url}/api/traces/{trace_id}", timeout=4.0)
                        if detail_resp.status_code == 200:
                            spans_data = detail_resp.json()
                            for batch in spans_data.get("batches", []):
                                svc_attrs = {
                                    a.get("key"): a.get("value", {}).get("stringValue")
                                    for a in batch.get("resource", {}).get("attributes", [])
                                }
                                svc_name = svc_attrs.get("service.name", "")
                                for scope_span in batch.get("scopeSpans", []):
                                    for s in scope_span.get("spans", []):
                                        attrs = {
                                            a.get("key"): (
                                                a.get("value", {}).get("stringValue")
                                                or a.get("value", {}).get("intValue")
                                            )
                                            for a in s.get("attributes", [])
                                        }
                                        spans_summary.append({
                                            "name": s.get("name"),
                                            "service": svc_name,
                                            "peer_address": attrs.get("server.address") or attrs.get("net.peer.name"),
                                            "peer_port": attrs.get("server.port") or attrs.get("net.peer.port"),
                                            "duration_ms": round(
                                                (int(s.get("endTimeUnixNano", 0)) - int(s.get("startTimeUnixNano", 0)))
                                                / 1_000_000,
                                                2,
                                            ),
                                        })

                    spans_summary.sort(key=lambda sp: float(sp.get("duration_ms", 0) or 0), reverse=True)
                    traces.append({
                        "trace_id": trace_id,
                        "duration_ms": duration_ms,
                        "root": root_name,
                        "spans": spans_summary[:12],
                    })
        except Exception as exc:
            logger.debug("Échec collecte traces Tempo : %s", exc)
        return traces

    def collect_all(self) -> dict[str, Any]:
        """Exécute l'ensemble de la collecte déterministe."""
        with httpx.Client(timeout=10.0) as client:
            alerts = self.collect_alerts(client)
            metrics = self.collect_key_metrics(client)
            logs = self.collect_recent_logs(client)
            traces = self.collect_slow_traces(client)

        return {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "alerts": alerts,
            "metrics": metrics,
            "logs": logs,
            "traces": traces,
        }


DeterministicCollector = TelemetryCollector
