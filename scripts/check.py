#!/usr/bin/env python3
"""Script de vérification et d'étalonnage du poste étudiant (make check).

Utilise uniquement la bibliothèque standard de Python 3.
"""

from __future__ import annotations

import ipaddress
import json
import os
import pathlib
import platform
import re
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env"

REQUIRED_OLLAMA_VERSION = "0.40.9"
GEN_MODEL = "qwen3:1.7b"
GEN_DIGEST_PREFIX = "8f68893c685c"
EMBED_MODEL = "nomic-embed-text:v1.5"
EMBED_DIGEST_PREFIX = "0a109f422b47"

DEFAULT_CHAOS_SUBNET = "10.200.84.0/24"
DEFAULT_TOXIPROXY_IP = "10.200.84.10"

# Schéma JSON unifié de l'outil de RCA (contrat §12 bis, ADR-004)
RCA_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["hypotheses"],
    "additionalProperties": False,
    "properties": {
        "hypotheses": {
            "type": "array",
            "minItems": 1,
            "maxItems": 2,
            "items": {
                "type": "object",
                "required": ["rank", "component", "cause", "query_id", "confidence"],
                "additionalProperties": False,
                "properties": {
                    "rank": {"type": "integer", "enum": [1, 2]},
                    "component": {
                        "type": "string",
                        "enum": [
                            "gateway",
                            "rag",
                            "embed",
                            "ollama",
                            "simule",
                            "postgres-db",
                            "postgres-link",
                        ],
                    },
                    "cause": {"type": "string", "minLength": 8, "maxLength": 90},
                    "query_id": {
                        "type": "string",
                        "enum": ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8"],
                    },
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
            },
        }
    },
}

RCA_CALIBRATION_PROMPT = """Tu es un assistant SRE d'analyse de cause racine (RCA) pour le service Orion.
Réponds uniquement par un objet JSON compact sur une seule ligne respectant le schéma fourni.
Exemple de format : {"hypotheses":[{"rank":1,"component":"postgres-db","cause":"Index HNSW absent causant un parcours séquentiel lent","query_id":"Q1","confidence":"high"}]}

Requêtes d'investigation disponibles :
- Q1 | metric | histogram_quantile(0.95, sum by (le, stage) (rate(rag_stage_duration_seconds_bucket[5m]))) -> stage retrieval à 0.34s (seuil 0.05s)
- Q2 | metric | histogram_quantile(0.95, sum by (le) (rate(rag_db_pool_wait_seconds_bucket[5m]))) -> 0.01s
- Q3 | metric | histogram_quantile(0.95, sum by (le, backend) (rate(gateway_request_duration_seconds_bucket[5m]))) -> simule=0.82s, ollama=3.10s
- Q4 | metric | sum by (code) (rate(traefik_service_requests_total{service="rag@file"}[5m])) -> 200=0.49 req/s, 500=0.00 req/s
- Q5 | log | {service="rag"} |= "retrieval" -> top_score=0.89, duration_ms=342, embed_model="nomic-embed-text:v1.5"
- Q6 | log | {service="gateway"} |= "attempt" -> backend="simule", ttft_ms=65, tokens_in=320, tokens_out=95
- Q7 | trace | span rag.retrieval -> duration=338ms, db.system="postgresql", db.operation="SELECT search_documents"
- Q8 | metric | pg_stat_user_tables_seq_scan{relname="documents"} -> hausse continue des lectures séquentielles sur public.documents

Extraits de télémétrie observés sur la fenêtre [T-10m, T] :
1. [METRIC] rag_stage_duration_seconds (p95) : embed=0.012s, retrieval=0.341s, prompt=0.002s, generate=0.815s.
2. [METRIC] gateway_request_duration_seconds (p95) : backend=simule 0.82s, backend=ollama 3.12s.
3. [LOG] ts=2026-10-24T10:04:12Z level=WARN service=rag team=support msg="slow vector search" duration_ms=345 top_score=0.88
4. [LOG] ts=2026-10-24T10:04:18Z level=WARN service=rag team=rh msg="slow vector search" duration_ms=339 top_score=0.91
5. [TRACE] trace_id=4bf92f3577b34da6a3ce929d0e0e4736 root=traefik -> rag (365ms) -> rag.retrieval (340ms) -> postgres:5432.
Identifie la cause racine principale et formule au plus deux hypothèses classées."""


def load_existing_env(path: pathlib.Path) -> dict[str, str]:
    env_map: dict[str, str] = {}
    if not path.is_file():
        return env_map
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env_map[k.strip()] = v.strip()
    return env_map


def detect_os_and_wsl() -> tuple[str, bool]:
    sys_name = platform.system()
    if sys_name == "Darwin":
        return "macOS", False
    if sys_name == "Linux":
        try:
            proc_ver = pathlib.Path("/proc/version").read_text(encoding="utf-8").lower()
            if "microsoft" in proc_ver or "wsl" in proc_ver:
                return "WSL2", True
        except OSError:
            pass
        return "Linux", False
    return sys_name, False


def get_host_ram_gib() -> float:
    sys_name = platform.system()
    try:
        if sys_name == "Darwin":
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip()
            return int(out) / (1024**3)
        if sys_name == "Linux":
            for line in pathlib.Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return kb / (1024**2)
    except Exception:
        pass
    return 0.0


def check_docker_engine() -> tuple[bool, float, str]:
    # Vérification préliminaire d'une installation Snap
    try:
        which_docker = subprocess.check_output(
            ["which", "docker"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        if "/snap/" in which_docker:
            return False, 0.0, (
                "Docker est installé via Snap (snap install docker).\n"
                "  Le confinement Snap bloque l'accès au socket Docker (/var/run/docker.sock) et perturbe la pile.\n"
                "  Veuillez désinstaller le paquet Snap et installer Docker via les paquets recommandés :\n"
                "    sudo snap remove docker\n"
                "    sudo apt update && sudo apt install -y docker.io docker-compose-v2\n"
                "    sudo usermod -aG docker $USER\n"
                "    newgrp docker"
            )
    except Exception:
        pass

    try:
        out = subprocess.check_output(
            ["docker", "info", "--format", "{{.MemTotal}}|{{.OperatingSystem}}|{{.Name}}"],
            stderr=subprocess.STDOUT,
            text=True,
            timeout=10,
        ).strip()
        parts = out.split("|")
        mem_bytes = int(parts[0]) if parts and parts[0].isdigit() else 0
        os_label = parts[1] if len(parts) > 1 else "Docker"
        subprocess.check_output(
            ["docker", "compose", "version"],
            stderr=subprocess.STDOUT,
            text=True,
            timeout=10,
        )
        return True, mem_bytes / (1024**3), os_label
    except Exception as exc:
        err_msg = str(exc)
        if "permission denied" in err_msg.lower() and pathlib.Path("/snap/docker").is_dir():
            return False, 0.0, (
                "Docker est installé via Snap (snap install docker).\n"
                "  Le confinement Snap bloque l'accès au socket Docker (/var/run/docker.sock).\n"
                "  Veuillez désinstaller le paquet Snap et installer Docker via les paquets recommandés :\n"
                "    sudo snap remove docker\n"
                "    sudo apt update && sudo apt install -y docker.io docker-compose-v2\n"
                "    sudo usermod -aG docker $USER\n"
                "    newgrp docker"
            )
        return False, 0.0, err_msg


def check_corporate_proxy() -> list[str]:
    warnings: list[str] = []
    http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or ""
    https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or ""
    no_proxy = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
    if http_proxy or https_proxy:
        missing = [
            host
            for host in ("localhost", "127.0.0.1", "host.docker.internal")
            if host not in no_proxy
        ]
        if missing:
            warnings.append(
                "Proxy d'entreprise détecté (HTTP_PROXY/HTTPS_PROXY), mais NO_PROXY ne contient pas : "
                + ", ".join(missing)
                + ". Ajoutez-les à NO_PROXY pour ne pas détourner les appels locaux vers Ollama."
            )
    return warnings


def parse_host_routes() -> list[tuple[ipaddress.IPv4Network, str]]:
    routes: list[tuple[ipaddress.IPv4Network, str]] = []
    simulated = os.environ.get("ORION_SIMULATE_ROUTES", "").strip()
    if simulated:
        for token in simulated.split(","):
            token = token.strip()
            if not token:
                continue
            try:
                net = ipaddress.IPv4Network(token, strict=False)
                routes.append((net, f"route simulée ({token})"))
            except ValueError:
                pass

    sys_name = platform.system()
    try:
        if sys_name == "Linux":
            out = subprocess.check_output(["ip", "-4", "route", "show"], text=True, timeout=5)
            for line in out.splitlines():
                parts = line.split()
                if not parts or parts[0] == "default":
                    continue
                prefix = parts[0]
                dev = ""
                if "dev" in parts:
                    idx = parts.index("dev")
                    if idx + 1 < len(parts):
                        dev = parts[idx + 1]
                # Ignorer les ponts Docker déjà créés par la stack elle-même
                if dev.startswith("br-") or dev == "docker0":
                    continue
                try:
                    net = ipaddress.IPv4Network(prefix, strict=False)
                    if net.prefixlen > 0:
                        routes.append((net, f"{prefix} (interface {dev or '?'})"))
                except ValueError:
                    continue
        elif sys_name == "Darwin":
            out = subprocess.check_output(["netstat", "-rn", "-f", "inet"], text=True, timeout=5)
            for line in out.splitlines():
                parts = line.split()
                if len(parts) < 4:
                    continue
                dest, gw, _flags, netif = parts[0], parts[1], parts[2], parts[3]
                if dest in ("default", "Destination", "0.0.0.0") or dest.startswith("127.") or dest.startswith("224.") or dest.startswith("255."):
                    continue
                net = _parse_bsd_destination(dest)
                if net is not None and net.prefixlen > 0 and not net.is_loopback and not net.is_link_local and not net.is_multicast:
                    routes.append((net, f"{net} via {gw} ({netif})"))
    except Exception:
        pass
    return routes


def _parse_bsd_destination(dest: str) -> ipaddress.IPv4Network | None:
    try:
        if "/" in dest:
            addr_part, plen = dest.split("/", 1)
            octets = addr_part.split(".")
            while len(octets) < 4:
                octets.append("0")
            return ipaddress.IPv4Network(".".join(octets) + "/" + plen, strict=False)
        octets = dest.split(".")
        if len(octets) == 4:
            return ipaddress.IPv4Network(dest + "/32", strict=False)
        if 1 <= len(octets) < 4:
            plen = len(octets) * 8
            while len(octets) < 4:
                octets.append("0")
            return ipaddress.IPv4Network(".".join(octets) + f"/{plen}", strict=False)
    except ValueError:
        return None
    return None


def check_subnet_overlap(
    subnet_str: str,
    ip_str: str,
    os_kind: str,
    docker_os_label: str,
) -> tuple[bool, str | None]:
    """Vérifie le sous-réseau interne et détecte un chevauchement VPN (ADR-023).

    Retourne (is_fatal, message).
    Sous Linux et WSL2 (où les ponts Docker sont routés sur l'hôte), un chevauchement est bloquant.
    Sous macOS ou Docker Desktop (conteneurs dans une VM), un avertissement non bloquant est affiché.
    """
    try:
        subnet = ipaddress.IPv4Network(subnet_str, strict=False)
        ip_addr = ipaddress.IPv4Address(ip_str)
    except ValueError as exc:
        return True, f"Configuration IPv4 invalide ({subnet_str} / {ip_str}) : {exc}"

    if ip_addr not in subnet or ip_addr in (subnet.network_address, subnet.broadcast_address):
        return (
            True,
            f"L'adresse ORION_TOXIPROXY_IP ({ip_str}) n'appartient pas au sous-réseau ORION_CHAOS_SUBNET ({subnet_str}).",
        )

    routes = parse_host_routes()
    conflicts = [desc for r_net, desc in routes if r_net.overlaps(subnet)]
    if not conflicts:
        return False, None

    remediation = (
        f"Chevauchement détecté entre le sous-réseau interne {subnet} et la table de routage "
        f"de la machine ({conflicts[0]}).\n"
        "  Pour utiliser une autre plage privée libre, ajoutez ces deux lignes dans le fichier .env :\n"
        "    ORION_CHAOS_SUBNET=10.219.84.0/24\n"
        "    ORION_TOXIPROXY_IP=10.219.84.10\n"
        "  puis relancez : make check"
    )

    force_mode = os.environ.get("ORION_SUBNET_CHECK_MODE", "").strip().lower()
    if force_mode == "error":
        return True, remediation
    if force_mode == "warn":
        return False, remediation

    is_vm = os_kind == "macOS" or "docker desktop" in docker_os_label.lower()
    if is_vm and os_kind != "WSL2":
        return False, remediation
    return True, remediation


def http_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "Host": "localhost",
            "User-Agent": "orion-check/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def compute_ollama_ratio(decode_tps: float, gen_seconds: float) -> float:
    if gen_seconds >= 18.0 or decode_tps < 8.0:
        return 0.0
    if decode_tps >= 35.0 and gen_seconds <= 6.0:
        return 0.25
    if decode_tps >= 20.0 and gen_seconds <= 10.0:
        return 0.20
    if decode_tps >= 12.0 and gen_seconds <= 14.0:
        return 0.15
    return 0.10


def ensure_tls_certs() -> None:
    gen_script = REPO_ROOT / "scripts" / "gen-certs.sh"
    if gen_script.is_file():
        subprocess.run(["sh", str(gen_script)], check=True)


def write_env_file(
    existing: dict[str, str],
    updates: dict[str, str],
) -> dict[str, str]:
    merged = dict(existing)
    for team in ("SUPPORT", "RH", "DEV"):
        key_var = f"ORION_KEY_{team}"
        if not merged.get(key_var):
            merged[key_var] = f"sk-nordel-{team.lower()}-{secrets.token_hex(6)}"

    merged.setdefault("ORION_CHAOS_SUBNET", DEFAULT_CHAOS_SUBNET)
    merged.setdefault("ORION_TOXIPROXY_IP", DEFAULT_TOXIPROXY_IP)
    merged.update(updates)

    ordered_keys = [
        "LOW_MEM",
        "ORION_USE_LINUX_COMPOSE",
        "ORION_OLLAMA_MODELS_DIR",
        "ORION_OLLAMA_RATIO",
        "ORION_RCA_MODE",
        "OLLAMA_RCA_NUM_THREAD",
        "ORION_CHAOS_SUBNET",
        "ORION_TOXIPROXY_IP",
        "ORION_KEY_SUPPORT",
        "ORION_KEY_RH",
        "ORION_KEY_DEV",
    ]
    lines = [
        "# Fichier généré automatiquement par make check (ne jamais commiter)",
    ]
    written: set[str] = set()
    for k in ordered_keys:
        if k in merged:
            lines.append(f"{k}={merged[k]}")
            written.add(k)
    for k, v in sorted(merged.items()):
        if k not in written:
            lines.append(f"{k}={v}")

    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return merged


def main() -> int:
    sys_raw = platform.system()
    if sys_raw == "Windows":
        print(
            "=== Vérification de l'environnement Orion (make check) ===\n"
            "[ERREUR] Vous exécutez make check sous Windows natif (PowerShell ou Invite de commandes).\n"
            "  Pour le cours Orion, tout l'environnement doit s'exécuter dans Ubuntu sous WSL2 :\n"
            "  1. Ouvrez votre terminal Ubuntu sous WSL2.\n"
            "  2. Assurez-vous d'avoir cloné orion-lab dans votre répertoire personnel Linux (ex: ~/orion-lab),\n"
            "     et JAMAIS sous le système de fichiers Windows (/mnt/c/...). \n"
            "  3. Relancez ensuite dans ce terminal Ubuntu : make check",
            file=sys.stderr,
        )
        return 1

    print("=== Vérification de l'environnement Orion (make check) ===")
    existing_env = load_existing_env(ENV_FILE)

    low_mem_str = os.environ.get("LOW_MEM", "0").strip()
    low_mem = low_mem_str in ("1", "true", "TRUE", "yes")

    os_kind, is_wsl = detect_os_and_wsl()
    arch = platform.machine()
    host_ram_gib = get_host_ram_gib()
    docker_ok, docker_ram_gib, docker_os_label = check_docker_engine()

    print(f"[1/6] Système : {os_kind} ({arch}) — RAM hôte : {host_ram_gib:.1f} Gio")
    if not docker_ok:
        print(f"[ERREUR] Le moteur Docker ou Docker Compose n'est pas joignable : {docker_os_label}", file=sys.stderr)
        return 1
    print(f"      Moteur Docker : {docker_os_label} — RAM allouée : {docker_ram_gib:.1f} Gio")

    if not low_mem and host_ram_gib > 0 and host_ram_gib < 12.0:
        print(
            "[AVERTISSEMENT] Moins de 12 Gio de RAM détectés. "
            "Si cette machine dispose de 8 Go, utilisez : make check LOW_MEM=1"
        )

    for warn in check_corporate_proxy():
        print(f"[AVERTISSEMENT] {warn}")

    # [2/6] Vérification du sous-réseau interne (ADR-023)
    chaos_subnet = os.environ.get(
        "ORION_CHAOS_SUBNET",
        existing_env.get("ORION_CHAOS_SUBNET", DEFAULT_CHAOS_SUBNET),
    ).strip()
    toxiproxy_ip = os.environ.get(
        "ORION_TOXIPROXY_IP",
        existing_env.get("ORION_TOXIPROXY_IP", DEFAULT_TOXIPROXY_IP),
    ).strip()

    is_fatal_overlap, overlap_msg = check_subnet_overlap(
        chaos_subnet,
        toxiproxy_ip,
        os_kind,
        docker_os_label,
    )
    if overlap_msg:
        if is_fatal_overlap:
            print(f"[ERREUR] {overlap_msg}", file=sys.stderr)
            return 1
        print(f"[AVERTISSEMENT] {overlap_msg}")
    else:
        print(f"[2/6] Réseau interne : plage {chaos_subnet} ({toxiproxy_ip}) sans conflit de route")

    # Génération idempotente des certificats TLS de lab
    ensure_tls_certs()

    if low_mem:
        print("[3/6] Mode LOW_MEM=1 actif : contrôles d'Ollama sautés (ORION_OLLAMA_RATIO=0)")
        low_mem_compose = REPO_ROOT / "compose" / "low-mem.yml"
        k6_questions = REPO_ROOT / "k6" / "k6-questions.yaml"
        ref_questions = REPO_ROOT / "k6" / "reference-questions.yaml"
        if not low_mem_compose.is_file() or not k6_questions.is_file() or not ref_questions.is_file():
            print(
                "[ERREUR] Fichiers compose/low-mem.yml, k6/k6-questions.yaml ou k6/reference-questions.yaml introuvables.",
                file=sys.stderr,
            )
            return 1
        print(
            "[4/6] Vérification LOW_MEM : compose/low-mem.yml, k6/k6-questions.yaml (300) "
            "et k6/reference-questions.yaml (36) présents (empreinte < 3 Go)"
        )
        print("[5/6] Étalonnage RCA : non applicable en LOW_MEM=1 (le lab 4b s'exécute sur la machine de 16 Go du trinôme)")

        write_env_file(
            existing_env,
            {
                "LOW_MEM": "1",
                "ORION_USE_LINUX_COMPOSE": "0",
                "ORION_OLLAMA_RATIO": "0",
                "ORION_RCA_MODE": "pre_aggregated",
                "OLLAMA_RCA_NUM_THREAD": "",
                "ORION_CHAOS_SUBNET": chaos_subnet,
                "ORION_TOXIPROXY_IP": toxiproxy_ip,
            },
        )
        print("[6/6] Fichier .env écrit avec succès.")
        print("\n--- Résumé à recopier dans le formulaire (aucun identifiant de machine) ---")
        print(f"OS={os_kind} ({arch}) | RAM_HOTE={host_ram_gib:.1f}GiB | RAM_DOCKER={docker_ram_gib:.1f}GiB")
        print("MODE=LOW_MEM | OLLAMA=desactive | ORION_OLLAMA_RATIO=0 | ORION_RCA_MODE=pre_aggregated")
        print("---------------------------------------------------------------------------")
        return 0

    # [3/6] Contrôle d'Ollama (version 0.40.9 obligatoire et modèles)
    use_container_ollama = os_kind in ("Linux", "WSL2")
    host_models_dir: str | None = None
    compose_files = [
        "-f", str(REPO_ROOT / "compose" / "docker-compose.yml"),
        "-f", str(REPO_ROOT / "compose" / "linux.yml"),
    ]
    env_compose = os.environ.copy()

    if use_container_ollama:
        print("[3/6] Préparation d'Ollama en conteneur (compose/linux.yml)...")
        candidates = [
            pathlib.Path("/usr/share/ollama/.ollama/models"),
            pathlib.Path.home() / ".ollama" / "models",
        ]
        for cand in candidates:
            if cand.is_dir() and (cand / "manifests").is_dir():
                host_models_dir = str(cand.parent)
                print(f"      Modèles hôtes détectés dans {host_models_dir} (réutilisation sans téléchargement)")
                break

        if host_models_dir:
            env_compose["ORION_OLLAMA_MODELS_DIR"] = host_models_dir

        try:
            print("      Démarrage du conteneur ollama-svc (téléchargement de l'image si nécessaire)...")
            subprocess.run(
                ["docker", "compose", *compose_files, "up", "-d", "ollama-svc"],
                cwd=str(REPO_ROOT),
                env=env_compose,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=300,
            )
        except Exception as exc:
            print(f"[ERREUR] Échec du démarrage du conteneur ollama-svc : {exc}", file=sys.stderr)
            return 1

    default_ollama_url = "http://127.0.0.1:11435" if use_container_ollama else "http://127.0.0.1:11434"
    ollama_url = os.environ.get("OLLAMA_HOST_URL", default_ollama_url).rstrip("/")
    ver_data: dict[str, Any] = {}
    for _ in range(30):
        try:
            ver_data = http_json(f"{ollama_url}/api/version", timeout=2.0)
            if ver_data.get("version"):
                break
        except Exception:
            time.sleep(1.0)

    if not ver_data.get("version"):
        if use_container_ollama:
            print(
                f"[ERREUR] Impossible de joindre le conteneur Ollama sur {ollama_url}/api/version après 30 s.\n"
                "  Vérifiez l'état du conteneur avec : docker compose logs ollama-svc",
                file=sys.stderr,
            )
        else:
            print(
                f"[ERREUR] Impossible de joindre Ollama sur {ollama_url}/api/version : délai d'attente dépassé.\n"
                "  Vérifiez qu'Ollama 0.40.9 est démarré (ou utilisez make check LOW_MEM=1 sur une machine de 8 Go).",
                file=sys.stderr,
            )
        return 1

    ollama_version = str(ver_data.get("version", "")).strip()
    if ollama_version != REQUIRED_OLLAMA_VERSION:
        print(
            f"[ERREUR] Version d'Ollama non conforme : '{ollama_version}' détectée, "
            f"mais la version '{REQUIRED_OLLAMA_VERSION}' est exigée par le contrat.",
            file=sys.stderr,
        )
        return 1
    target_label = "conteneur" if use_container_ollama else "natif"
    print(f"[3/6] Ollama ({target_label}) : version {ollama_version} conforme")

    try:
        tags_data = http_json(f"{ollama_url}/api/tags", timeout=5.0)
        models = {m.get("name"): str(m.get("digest", "")) for m in tags_data.get("models", [])}
    except Exception as exc:
        print(f"[ERREUR] Impossible de lire /api/tags sur Ollama : {exc}", file=sys.stderr)
        return 1

    for req_model, req_digest in ((GEN_MODEL, GEN_DIGEST_PREFIX), (EMBED_MODEL, EMBED_DIGEST_PREFIX)):
        if req_model not in models:
            if use_container_ollama:
                print(f"      Téléchargement du modèle {req_model} dans le conteneur Ollama...")
                pull_res = subprocess.run(
                    ["docker", "compose", *compose_files, "exec", "-T", "ollama-svc", "ollama", "pull", req_model],
                    cwd=str(REPO_ROOT),
                    env=env_compose,
                    check=False,
                )
                if pull_res.returncode != 0:
                    print(f"[ERREUR] Échec du téléchargement de {req_model} dans le conteneur.", file=sys.stderr)
                    return 1
                try:
                    tags_data = http_json(f"{ollama_url}/api/tags", timeout=5.0)
                    models = {m.get("name"): str(m.get("digest", "")) for m in tags_data.get("models", [])}
                except Exception:
                    pass
            else:
                print(
                    f"[ERREUR] Modèle Ollama manquant : {req_model}. Lancez : make pull",
                    file=sys.stderr,
                )
                return 1
        if req_digest and not models.get(req_model, "").startswith(req_digest):
            print(
                f"[AVERTISSEMENT] Digest de {req_model} ({models.get(req_model, '')[:12]}) différent "
                f"du digest de référence ({req_digest})."
            )

    # Pré-chargement de l'embedding et vérification de /api/ps
    try:
        http_json(
            f"{ollama_url}/api/embed",
            method="POST",
            payload={"model": EMBED_MODEL, "input": ["Vérification du modèle d'embedding Nordel"], "keep_alive": "24h"},
            timeout=15.0,
        )
    except Exception as exc:
        print(f"[ERREUR] Échec du test d'embedding sur {EMBED_MODEL} : {exc}", file=sys.stderr)
        return 1

    # [4/6] Génération de référence (<= 150 tokens) et calcul de ORION_OLLAMA_RATIO
    print("[4/6] Génération de référence sur qwen3:1.7b (max 150 tokens, think: false)...")
    t0 = time.monotonic()
    try:
        gen_resp = http_json(
            f"{ollama_url}/api/chat",
            method="POST",
            payload={
                "model": GEN_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Explique en quatre phrases courtes le rôle d'un index HNSW dans PostgreSQL "
                            "avec pgvector et pourquoi son absence ralentit les recherches vectorielles."
                        ),
                    }
                ],
                "think": False,
                "stream": False,
                "keep_alive": "24h",
                "options": {
                    "num_ctx": 4096,
                    "num_predict": 150,
                    "temperature": 0,
                },
            },
            timeout=35.0,
        )
    except Exception as exc:
        print(
            f"[ERREUR] La génération de référence a dépassé le timeout par tentative (35 s) ou a échoué : {exc}",
            file=sys.stderr,
        )
        return 1
    gen_elapsed = time.monotonic() - t0

    eval_count = int(gen_resp.get("eval_count") or 1)
    eval_dur_s = max(float(gen_resp.get("eval_duration") or 1e9) / 1e9, 1e-3)
    ref_decode_tps = eval_count / eval_dur_s
    ollama_ratio = compute_ollama_ratio(ref_decode_tps, gen_elapsed)

    # Vérification de /api/ps (les deux modèles doivent pouvoir résider simultanément)
    try:
        ps_data = http_json(f"{ollama_url}/api/ps", timeout=5.0)
        loaded_names = [str(m.get("name", "")) for m in ps_data.get("models", [])]
    except Exception:
        loaded_names = []

    print(
        f"      Génération : {eval_count} tokens en {gen_elapsed:.2f} s ({ref_decode_tps:.1f} tok/s) "
        f"-> ORION_OLLAMA_RATIO={ollama_ratio:.2f}"
    )
    print(f"      Modèles chargés (/api/ps) : {', '.join(loaded_names) if loaded_names else 'aucun'}")
    if len(loaded_names) < 2:
        print(
            "[AVERTISSEMENT] Un seul modèle est actif dans /api/ps. "
            "Assurez-vous que OLLAMA_MAX_LOADED_MODELS=2 est bien configuré sur le service Ollama."
        )

    # [5/6] Étalonnage de l'outil de RCA (contrat §12 et §12 bis, ADR-004)
    rca_num_thread = ""
    if os_kind != "macOS":
        cpu_cnt = os.cpu_count() or 4
        rca_num_thread = str(min(max(cpu_cnt // 2, 2), 4))

    rca_options: dict[str, Any] = {
        "num_ctx": 4096,
        "temperature": 0,
        "num_predict": 120,
    }
    if rca_num_thread:
        rca_options["num_thread"] = int(rca_num_thread)

    print("[5/6] Étalonnage de la RCA (schéma JSON structuré, estimation sur 3 100 tokens d'entrée + 80 de sortie)...")
    calibration_prompt = f"[Session d'étalonnage {secrets.token_hex(8)}]\n{RCA_CALIBRATION_PROMPT}"
    try:
        rca_resp = http_json(
            f"{ollama_url}/api/chat",
            method="POST",
            payload={
                "model": GEN_MODEL,
                "messages": [{"role": "user", "content": calibration_prompt}],
                "think": False,
                "truncate": False,
                "stream": False,
                "keep_alive": "24h",
                "format": RCA_JSON_SCHEMA,
                "options": rca_options,
            },
            timeout=45.0,
        )
    except Exception as exc:
        print(f"[ERREUR] Échec de l'étalonnage RCA sur Ollama : {exc}", file=sys.stderr)
        return 1

    p_eval_count = max(int(rca_resp.get("prompt_eval_count") or 400), 1)
    p_eval_dur_s = max(float(rca_resp.get("prompt_eval_duration") or 1e9) / 1e9, 1e-3)
    c_eval_count = max(int(rca_resp.get("eval_count") or 40), 1)
    c_eval_dur_s = max(float(rca_resp.get("eval_duration") or 1e9) / 1e9, 1e-3)

    prefill_tps = p_eval_count / p_eval_dur_s
    decode_tps = c_eval_count / c_eval_dur_s
    estimated_rca_seconds = (3100.0 / prefill_tps) + (80.0 / decode_tps)
    rca_mode = "raw" if estimated_rca_seconds < 30.0 else "pre_aggregated"

    print(
        f"      Débit de prefill : {prefill_tps:.1f} tok/s | Débit de décodage (JSON) : {decode_tps:.1f} tok/s"
    )
    print(
        f"      Temps estimé RCA (3 100 / {prefill_tps:.1f} + 80 / {decode_tps:.1f}) = {estimated_rca_seconds:.2f} s "
        f"-> ORION_RCA_MODE={rca_mode}"
    )

    env_updates: dict[str, str] = {
        "LOW_MEM": "0",
        "ORION_USE_LINUX_COMPOSE": "1" if use_container_ollama else "0",
        "ORION_OLLAMA_RATIO": f"{ollama_ratio:.2f}",
        "ORION_RCA_MODE": rca_mode,
        "OLLAMA_RCA_NUM_THREAD": rca_num_thread,
        "ORION_CHAOS_SUBNET": chaos_subnet,
        "ORION_TOXIPROXY_IP": toxiproxy_ip,
    }
    if host_models_dir:
        env_updates["ORION_OLLAMA_MODELS_DIR"] = host_models_dir

    write_env_file(existing_env, env_updates)
    print("[6/6] Fichier .env écrit avec succès.")

    print("\n--- Résumé à recopier dans le formulaire (aucun identifiant de machine) ---")
    print(f"OS={os_kind} ({arch}) | RAM_HOTE={host_ram_gib:.1f}GiB | RAM_DOCKER={docker_ram_gib:.1f}GiB")
    print(
        f"OLLAMA={ollama_version} | PREFILL_TPS={prefill_tps:.1f} | DECODE_TPS={decode_tps:.1f} | "
        f"RCA_EST_S={estimated_rca_seconds:.2f} | ORION_RCA_MODE={rca_mode} | ORION_OLLAMA_RATIO={ollama_ratio:.2f}"
    )
    print("---------------------------------------------------------------------------")
    return 0


if __name__ == "__main__":
    sys.exit(main())
