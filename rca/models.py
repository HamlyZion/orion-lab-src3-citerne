"""Modèles de données Pydantic et schéma JSON pour l'outil de RCA (Lab 4b).

Conforme à l'ADR-004 (amendée G1 / T01c) et au §12 bis du contrat d'interfaces :
- Schéma JSON unifié pour les modes raw et pre_aggregated ;
- Au plus 2 hypothèses (minItems: 1, maxItems: 2) ;
- Cause en texte libre de 90 caractères au plus (maxLength: 90) ;
- Sélection de query_id dans le catalogue compact Q1..Q8 ;
- Réhydratation de signal_type et proof_query par Python après validation.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict
from pydantic import BaseModel, ConfigDict, Field

ComponentType = Literal[
    "gateway", "rag", "embed", "ollama", "simule", "postgres-db", "postgres-link"
]
QueryId = Literal["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8"]
SignalType = Literal["metrics", "logs", "traces"]
ConfidenceType = Literal["high", "medium", "low"]
VerdictType = Literal["juste", "fausse", "hallucinee", ""]


class CatalogueEntry(TypedDict):
    signal: SignalType
    summary: str
    query: str


class ModelHypothesis(BaseModel):
    """Hypothèse brute générée par le modèle (contrainte par le JSON Schema)."""

    model_config = ConfigDict(extra="forbid")

    rank: int = Field(ge=1, le=2)
    component: ComponentType
    cause: str = Field(min_length=4, max_length=90)
    query_id: QueryId
    confidence: ConfidenceType


class RCAModelOutput(BaseModel):
    """Sortie brute attendue du modèle Qwen3."""

    model_config = ConfigDict(extra="forbid")

    hypotheses: list[ModelHypothesis] = Field(min_length=1, max_length=2)


class RehydratedHypothesis(BaseModel):
    """Hypothèse finale après réhydratation de la requête et ajout du verdict étudiant."""

    model_config = ConfigDict(extra="ignore")

    rank: int
    component: ComponentType | str
    cause: str
    signal_type: str = ""
    query_id: str = ""
    proof_query: str = ""
    confidence: ConfidenceType | str = "medium"
    verdict: str = ""  # À renseigner par les étudiants : "juste", "fausse" ou "hallucinee"


RCAHypothesis = RehydratedHypothesis


class RCAOutputReport(BaseModel):
    """Rapport de RCA final exporté dans rca.yaml."""

    model_config = ConfigDict(extra="ignore")

    mode: str
    model: str = "qwen3:1.7b"
    generated_at: str
    actual_duration_s: float
    hypotheses: list[RCAHypothesis]
    metadata: dict[str, Any] = Field(default_factory=dict)


RCAReport = RCAOutputReport
RehydratedHypothesis.model_rebuild()
RCAOutputReport.model_rebuild()


RCA_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "hypotheses": {
            "type": "array",
            "minItems": 1,
            "maxItems": 2,
            "items": {
                "type": "object",
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
                    "cause": {"type": "string", "minLength": 4, "maxLength": 90},
                    "query_id": {
                        "type": "string",
                        "enum": ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8"],
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                },
                "required": [
                    "rank",
                    "component",
                    "cause",
                    "query_id",
                    "confidence",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["hypotheses"],
    "additionalProperties": False,
}
