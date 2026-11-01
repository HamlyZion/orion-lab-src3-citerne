"""Instrumentation OpenTelemetry avec conventions sémantiques GenAI pour l'outil de RCA.

Conforme au §12 bis du contrat d'interfaces :
- service.name = orion-rca
- OTLP gRPC vers http://alloy:4317
- Attributs GenAI : gen_ai.operation.name, gen_ai.provider.name, gen_ai.request.model,
  gen_ai.usage.input_tokens, gen_ai.usage.output_tokens
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Generator

logger = logging.getLogger("orion-rca.tracer")

_TRACER = None


def get_tracer():
    """Initialise et retourne le Tracer OpenTelemetry pour orion-rca."""
    global _TRACER
    if _TRACER is not None:
        return _TRACER

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        service_name = os.environ.get("OTEL_SERVICE_NAME", "orion-rca")
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://alloy:4317")

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        _TRACER = trace.get_tracer("orion-rca", "1.0.0")
        logger.info("Traceur OpenTelemetry initialisé vers %s", endpoint)
    except Exception as exc:
        logger.warning("Impossible d'initialiser OpenTelemetry : %s (mode sans trace)", exc)
        _TRACER = None

    return _TRACER


@contextmanager
def trace_rca_chat(
    model: str = "qwen3:1.7b",
    provider: str = "ollama",
    **kwargs: Any,
) -> Generator[dict[str, Any], None, None]:
    """Gestionnaire de contexte émettant un span GenAI lors de l'appel LLM."""
    tracer = get_tracer()
    metadata: dict[str, Any] = {
        "input_tokens": 0,
        "output_tokens": 0,
        "error": None,
    }

    if tracer is None:
        yield metadata
        return

    from opentelemetry.trace import Status, StatusCode

    with tracer.start_as_current_span("chat " + model) as span:
        span.set_attribute("gen_ai.operation.name", "chat")
        span.set_attribute("gen_ai.provider.name", provider)
        span.set_attribute("gen_ai.request.model", model)

        try:
            yield metadata
        except Exception as exc:
            metadata["error"] = str(exc)
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
        finally:
            if metadata.get("input_tokens"):
                span.set_attribute("gen_ai.usage.input_tokens", int(metadata["input_tokens"]))
            if metadata.get("output_tokens"):
                span.set_attribute("gen_ai.usage.output_tokens", int(metadata["output_tokens"]))
            if not metadata.get("error"):
                span.set_status(Status(StatusCode.OK))
