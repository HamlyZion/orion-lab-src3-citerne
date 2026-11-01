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
    # TODO(lab-3): remplacer `yield None` par l'ouverture d'un span "rag.retrieval"
    # à l'aide de trace.get_tracer("orion.rag.metier").start_as_current_span("rag.retrieval"),
    # poser les attributs GenAI (gen_ai.operation.name, gen_ai.provider.name,
    # gen_ai.request.model), puis céder le span avec `yield span`.
    _ = (trace, team, top_k)
    yield None
