"""Gestionnaire du bail de suspension du routage de la gateway (Lab 4b).

Conforme au §4 bis et §12 bis du contrat d'interfaces :
- POST /internal/routing-pause : ouverture du bail (ttl_seconds=60)
- PUT /internal/routing-pause/{lease_id} : renouvellement périodique (toutes les 20 s)
- DELETE /internal/routing-pause/{lease_id} : libération garantie dans un bloc finally
- Expiration automatique sous 60 s en cas d'interruption brutale (kill -9)
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import httpx

logger = logging.getLogger("orion-rca.lease")


class GatewayLease:
    """Gestionnaire de contexte pour le bail de suspension du routage réel vers Ollama."""

    def __init__(
        self,
        gateway_internal_url: str = "http://gateway:8090",
        holder: str = "rca",
        ttl_seconds: int = 60,
        renew_interval_s: float = 20.0,
    ) -> None:
        self.base_url = gateway_internal_url.rstrip("/")
        self.holder = holder
        self.ttl_seconds = min(60, max(5, ttl_seconds))
        self.renew_interval_s = renew_interval_s
        self.lease_id: str | None = None
        self._stop_event = threading.Event()
        self._renew_thread: threading.Thread | None = None

    @property
    def active(self) -> bool:
        """Indique si le bail est actuellement actif."""
        return self.lease_id is not None

    def __enter__(self) -> GatewayLease:
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()

    def acquire(self) -> str | None:
        """Ouvre le bail auprès de la gateway."""
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.post(
                    f"{self.base_url}/internal/routing-pause",
                    json={"holder": self.holder, "ttl_seconds": self.ttl_seconds},
                )
                if resp.status_code == 201:
                    data = resp.json()
                    self.lease_id = data.get("lease_id")
                    logger.info("Bail ouvert avec succès (lease_id=%s, ttl=%ds)", self.lease_id, self.ttl_seconds)
                    self._start_renew_loop()
                    return self.lease_id
                logger.warning("Échec ouverture bail gateway (HTTP %d : %s)", resp.status_code, resp.text)
        except Exception as exc:
            logger.warning("Impossible de joindre la gateway pour ouvrir le bail : %s", exc)
        return None

    def _start_renew_loop(self) -> None:
        """Lance un thread d'arrière-plan pour renouveler le bail toutes les 20 s."""
        if not self.lease_id:
            return

        def _loop() -> None:
            while not self._stop_event.wait(timeout=self.renew_interval_s):
                if not self.lease_id:
                    break
                try:
                    with httpx.Client(timeout=5.0) as client:
                        resp = client.put(
                            f"{self.base_url}/internal/routing-pause/{self.lease_id}",
                            json={"ttl_seconds": self.ttl_seconds},
                        )
                        if resp.status_code != 200:
                            logger.warning("Échec renouvellement bail (HTTP %d)", resp.status_code)
                except Exception as exc:
                    logger.warning("Erreur lors du renouvellement du bail : %s", exc)

        self._renew_thread = threading.Thread(target=_loop, daemon=True, name="gateway-lease-renew")
        self._renew_thread.start()

    def release(self) -> None:
        """Libère le bail auprès de la gateway et arrête le renouvellement."""
        self._stop_event.set()
        if self._renew_thread and self._renew_thread.is_alive():
            self._renew_thread.join(timeout=2.0)

        if not self.lease_id:
            return

        lease_to_delete = self.lease_id
        self.lease_id = None
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.delete(f"{self.base_url}/internal/routing-pause/{lease_to_delete}")
                if resp.status_code == 204:
                    logger.info("Bail libéré avec succès (lease_id=%s)", lease_to_delete)
                else:
                    logger.warning("Échec libération bail (HTTP %d : %s)", resp.status_code, resp.text)
        except Exception as exc:
            logger.warning("Impossible de joindre la gateway pour libérer le bail : %s", exc)
