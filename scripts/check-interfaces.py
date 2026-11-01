#!/usr/bin/env python3
"""Vérification de la disponibilité et de l'authenticité des interfaces Orion depuis l'hôte."""

from __future__ import annotations

import json
import os
from pathlib import Path
import ssl
import sys
import time
import urllib.error
import urllib.request


def get_ssl_context(repo_root: Path) -> ssl.SSLContext:
    ca_path = repo_root / "config/traefik/certs/ca.crt"
    if ca_path.is_file():
        ctx = ssl.create_default_context(cafile=str(ca_path))
        # Python >= 3.13 exige l'Authority Key Identifier, absent des certificats générés avant ce correctif
        ctx.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)
        return ctx
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def check_interface(target: dict, repo_root: Path) -> tuple[bool, str]:
    url = target["url"]
    ssl_ctx = get_ssl_context(repo_root) if url.startswith("https://") else None
    req = urllib.request.Request(url, headers={"User-Agent": "orion-healthcheck/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=3.0, context=ssl_ctx) as resp:
            status = resp.status
            body = resp.read().decode("utf-8", errors="replace")

            if status != 200:
                return False, f"code HTTP {status}"

            validator = target.get("validator")
            if validator:
                ok, reason = validator(body)
                if not ok:
                    return False, reason

            return True, "OK"
    except urllib.error.HTTPError as e:
        validator = target.get("validator")
        if validator:
            try:
                body = e.read().decode("utf-8", errors="replace")
                ok, reason = validator(body)
                if ok and e.code == 200:
                    return True, "OK"
            except Exception:
                pass
        return False, f"code HTTP {e.code}"
    except urllib.error.URLError as e:
        return False, f"connexion impossible ({e.reason})"
    except Exception as e:
        return False, f"erreur : {e}"


def validate_traefik_healthz(body: str) -> tuple[bool, str]:
    try:
        data = json.loads(body)
        if data.get("status") == "ok":
            return True, "OK"
        return False, f"contenu JSON inattendu : status={data.get('status')}"
    except Exception:
        if '{"status":"ok"}' in body.replace(" ", ""):
            return True, "OK"
        return False, "réponse non conforme à {'status':'ok'}"


def validate_grafana_health(body: str) -> tuple[bool, str]:
    try:
        data = json.loads(body)
        if "database" in data:
            return True, "OK"
        return False, "champ 'database' absent du JSON"
    except Exception:
        if '"database"' in body:
            return True, "OK"
        return False, "réponse non conforme (JSON Grafana avec 'database' attendu)"


def validate_console_page(body: str) -> tuple[bool, str]:
    if "Poste d'incident Orion" in body or "CONSOLE D'INCIDENT" in body or "POSTE D'AIGUILLAGE ORION" in body:
        return True, "OK"
    return False, "signature de la console Orion absente de la page HTML"


TARGETS = [
    {
        "name": "Traefik (RAG / Healthz)",
        "port": 8443,
        "url": "https://127.0.0.1:8443/healthz",
        "validator": validate_traefik_healthz,
    },
    {
        "name": "Prometheus",
        "port": 9090,
        "url": "http://127.0.0.1:9090/-/ready",
        "validator": None,
    },
    {
        "name": "Grafana",
        "port": 3000,
        "url": "http://127.0.0.1:3000/api/health",
        "validator": validate_grafana_health,
    },
    {
        "name": "Alertmanager",
        "port": 9093,
        "url": "http://127.0.0.1:9093/-/ready",
        "validator": None,
    },
    {
        "name": "Console d'incident",
        "port": 8088,
        "url": "http://127.0.0.1:8088/",
        "validator": validate_console_page,
    },
]


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    timeout = int(os.environ.get("ORION_CHECK_TIMEOUT", "60"))
    deadline = time.time() + timeout

    print(f"=== Vérification de la disponibilité des interfaces Orion (délai max : {timeout} s) ===")

    success_status: dict[int, bool] = {t["port"]: False for t in TARGETS}
    last_errors: dict[int, str] = {t["port"]: "en attente" for t in TARGETS}

    while time.time() < deadline:
        all_ok = True
        current_status: dict[int, bool] = {}
        for t in TARGETS:
            port = t["port"]
            ok, msg = check_interface(t, repo_root)
            current_status[port] = ok
            if not ok:
                all_ok = False
                last_errors[port] = msg

        success_status = current_status

        if all_ok:
            for t in TARGETS:
                print(f"  [OK] {t['name']} (port {t['port']}) répond correctement.")
            print("[OK] Toutes les interfaces Orion répondent et sont prêtes.")
            return 0

        time.sleep(1.0)

    print("[ERREUR] Une ou plusieurs interfaces Orion ne répondent pas correctement après le délai imparti :", file=sys.stderr)
    for t in TARGETS:
        port = t["port"]
        if not success_status[port]:
            err_msg = last_errors[port]
            print(
                f"\n[ERREUR] L'interface {t['name']} sur le port {port} ne répond pas ou ne renvoie pas la réponse attendue ({err_msg}).\n"
                f"  -> Pour identifier le programme occupant ce port : lsof -nP -iTCP:{port} -sTCP:LISTEN\n"
                f"  -> Sous Colima, si docker compose ps montre les conteneurs Up : colima restart, puis make up",
                file=sys.stderr,
            )

    return 1


if __name__ == "__main__":
    sys.exit(main())
