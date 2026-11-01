"""Client direct Ollama pour l'outil de RCA Orion (ADR-004, §12 bis).

Caractéristiques :
- Accès direct sans proxy ni gateway (Host: localhost, User-Agent: orion-rca).
- Options fixées : think=false, truncate=false, keep_alive=24h, num_ctx=4096, temperature=0, num_predict=500.
- Schéma JSON contraint (RCA_JSON_SCHEMA).
- Tracé avec OpenTelemetry (conventions sémantiques GenAI).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Optional

import httpx

try:
    from .models import RCAModelOutput, RCA_JSON_SCHEMA
    from .tracer import trace_rca_chat
except (ImportError, ValueError):
    from models import RCAModelOutput, RCA_JSON_SCHEMA
    from tracer import trace_rca_chat

logger = logging.getLogger("orion.rca.ollama")


class OllamaClientError(Exception):
    """Erreur lors de l'appel à Ollama."""
    pass


class OllamaRCAClient:
    """Client Ollama dédié à la RCA d'Orion."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: str = "qwen3:1.7b",
        num_threads: Optional[int] = None,
        timeout_seconds: float = 120.0,
    ):
        raw_url = (
            base_url
            or os.environ.get("OLLAMA_RCA_URL")
            or os.environ.get("OLLAMA_URL")
            or "http://127.0.0.1:11434"
        )
        self.base_url = raw_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

        # Threads CPU configurables (ADR-004)
        if num_threads is not None:
            self.num_threads = num_threads
        else:
            env_threads = os.environ.get("OLLAMA_RCA_NUM_THREAD", "").strip()
            self.num_threads = int(env_threads) if env_threads.isdigit() else None

    def call_rca(
        self,
        system_prompt: str,
        user_prompt: str,
        model_name: Optional[str] = None,
    ) -> tuple[RCAModelOutput, dict[str, Any]]:
        """Appelle Ollama /api/chat avec le schéma contraint et le traçage GenAI.
        
        Retourne (output_valide, metadata_statistiques).
        """
        target_model = model_name or self.model
        api_url = f"{self.base_url}/api/chat"

        options: dict[str, Any] = {
            "num_ctx": 4096,
            "temperature": 0.0,
            "num_predict": 500,
        }
        if self.num_threads:
            options["num_thread"] = self.num_threads

        payload = {
            "model": target_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "think": False,
            "truncate": False,
            "keep_alive": "24h",
            "format": RCA_JSON_SCHEMA,
            "options": options,
        }

        headers = {
            "Host": "localhost",
            "User-Agent": "orion-rca",
            "Content-Type": "application/json",
        }

        full_prompt = f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}"

        logger.info(
            "Appel direct Ollama sur %s (modèle=%s, threads=%s)",
            api_url,
            target_model,
            self.num_threads or "auto",
        )

        with trace_rca_chat(
            model=target_model,
            prompt=full_prompt,
            server_address=self.base_url,
            temperature=0.0,
            max_tokens=500,
        ) as span_ctx:
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(api_url, json=payload, headers=headers)
                    response.raise_for_status()
                    data = response.json()
            except httpx.ConnectError as err:
                msg = f"Impossible de joindre Ollama sur {api_url} : {err}"
                logger.error(msg)
                raise OllamaClientError(msg) from err
            except httpx.HTTPStatusError as err:
                msg = f"Ollama a répondu avec statut {err.response.status_code} : {err.response.text}"
                logger.error(msg)
                raise OllamaClientError(msg) from err
            except Exception as err:
                msg = f"Erreur inattendue lors de l'appel Ollama : {err}"
                logger.error(msg)
                raise OllamaClientError(msg) from err

            message = data.get("message", {})
            raw_content = message.get("content", "").strip()

            prompt_eval_count = data.get("prompt_eval_count", 0)
            eval_count = data.get("eval_count", 0)
            total_duration_ns = data.get("total_duration", 0)
            total_duration_s = total_duration_ns / 1e9 if total_duration_ns else 0.0

            span_ctx["response"] = raw_content
            span_ctx["input_tokens"] = prompt_eval_count
            span_ctx["output_tokens"] = eval_count
            span_ctx["finish_reason"] = data.get("done_reason", "stop")

            # Validation du contenu JSON
            try:
                parsed_output = RCAModelOutput.model_validate_json(raw_content)
            except Exception as err:
                logger.warning(
                    "Échec validation modèle Pydantic directe : %s. Contenu brut : %s",
                    err,
                    raw_content,
                )
                # Tentative d'extraction si encadré par des backticks ou accolades
                clean_json = raw_content
                if "```json" in clean_json:
                    clean_json = clean_json.split("```json", 1)[1].split("```", 1)[0].strip()
                elif "```" in clean_json:
                    clean_json = clean_json.split("```", 1)[1].split("```", 1)[0].strip()

                try:
                    parsed_output = RCAModelOutput.model_validate_json(clean_json)
                except Exception as err2:
                    raise OllamaClientError(
                        f"Sortie Ollama non conforme au schéma : {err2}\nContenu brut : {raw_content}"
                    ) from err2

            meta = {
                "model": target_model,
                "prompt_eval_count": prompt_eval_count,
                "eval_count": eval_count,
                "total_duration_seconds": round(total_duration_s, 3),
                "done_reason": data.get("done_reason", "stop"),
            }

            return parsed_output, meta
