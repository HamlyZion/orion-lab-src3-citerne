"""Module de span métier pour l'étape de recherche vectorielle d'Orion RAG.

Ce fichier est monté dans le conteneur `rag` sous `/opt/orion/span-metier/span_metier.py`
et rechargé à chaque requête `/ask`.
"""

from contextlib import contextmanager
from typing import Any, Iterator

from opentelemetry import trace


@contextmanager
def retrieval_span(team: str, top_k: int) -> Iterator[Any]:
    """Ouvre un span OpenTelemetry autour de la recherche vectorielle dans PostgreSQL.

    Lorsque vous produirez un span actif (`yield span`), le service `rag` y ajoutera
    automatiquement les attributs `orion.team`, `rag.top_k`, `rag.docs_found` et
    `rag.top_distance`.
    """
    _ = (team, top_k)
    tracer = trace.get_tracer("orion.rag.metier")
    with tracer.start_as_current_span("rag.retrieval") as span:
        # Attributs semantiques GenAI pour la phase de retrieval
        span.set_attribute("gen_ai.operation.name", "retrieval")
        span.set_attribute("gen_ai.provider.name", "orion")
        span.set_attribute("gen_ai.request.model", "nomic-embed-text:v1.5")
        yield span
