"""Records what each agent did: in the response, in a JSON log line, and as a span when tracing is on."""
import json
import logging
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache

from app import llm, metrics

logger = logging.getLogger("getnet")


class JsonFormatter(logging.Formatter):
    """One JSON object per line, so a log platform can filter by trace_id, agent or status."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "event": record.getMessage(),
            **getattr(record, "fields", {}),
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)


def log_event(event: str, **fields) -> None:
    logger.info(event, extra={"fields": fields})


@lru_cache
def _tracer():
    """An OpenTelemetry tracer, or None when no collector endpoint is configured."""
    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return None
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": "getnet-agents"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))  # reads the endpoint from the environment
    return provider.get_tracer("getnet")


@contextmanager
def span(name: str, **attributes):
    """A span around the block. Does nothing unless tracing is configured."""
    tracer = _tracer()
    if tracer is None:
        yield None
        return
    with tracer.start_as_current_span(name, attributes=attributes) as current:
        yield current


def traced(agent: str, node, on_error=None):
    """Wrap an agent so every run is timed, metered, recorded in state["steps"], and safe to fail.

    A node that raises hands the request to a human, unless `on_error(agent, state)` supplies
    another state update (the specialists use it to report a failed step back to the router).
    """

    def run(state: dict) -> dict:
        started = time.perf_counter()
        with span(f"agent.{agent}", trace_id=state.get("trace_id", "")) as current, llm.meter() as usage:
            try:
                update = node(state) or {}
                status = "ok"
            except Exception:
                logger.exception("%s agent failed", agent, extra={"fields": {"trace_id": state.get("trace_id")}})
                if on_error:
                    update = on_error(agent, state)
                else:
                    update = {"escalation_reason": f"The {agent} agent could not complete the request."}
                status = "error"

            step = {
                "agent": agent,
                "status": status,
                **update.pop("step", {}),  # tools used, routing decision
                "latency_ms": round((time.perf_counter() - started) * 1000),
            }
            if usage.calls:
                step |= {
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "cost_usd": round(usage.cost_usd, 6),
                }
            if current is not None:
                for key, value in step.items():
                    current.set_attribute(key, value if isinstance(value, (str, int, float, bool)) else str(value))
        log_event(
            "agent_step", trace_id=state.get("trace_id"), conversation_id=state.get("conversation_id"), **step
        )
        metrics.record_step(agent, step, update)
        return {**update, "steps": [step]}

    return run
