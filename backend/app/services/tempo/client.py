import asyncio
import base64
import binascii
import logging
import time
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger("kubernetes-dashboard")


class TempoUnavailableError(RuntimeError):
    """Raised when Tempo cannot be reached or returns an error response."""


async def _get(settings: Settings, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(f"{settings.tempo_url}{path}", params=params or {})
    except httpx.HTTPError as exc:
        raise TempoUnavailableError(str(exc)) from exc

    if response.status_code == 404:
        raise TempoUnavailableError("Trace not found")
    if response.status_code >= 400:
        raise TempoUnavailableError(f"Tempo returned {response.status_code}")

    return response.json()


def _hex_id(value: str | None) -> str | None:
    """Tempo's trace-by-id endpoint returns OTLP ids base64-encoded, while its
    search endpoint returns them as hex — normalise everything to hex."""
    if not value:
        return None
    try:
        return base64.b64decode(value).hex()
    except (binascii.Error, ValueError):
        return value


def _attribute_value(value: dict[str, Any]) -> Any:
    """Unwrap one OTLP AnyValue into a plain Python value."""
    if "stringValue" in value:
        return value["stringValue"]
    if "intValue" in value:
        return int(value["intValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "boolValue" in value:
        return bool(value["boolValue"])
    if "arrayValue" in value:
        return [_attribute_value(item) for item in value["arrayValue"].get("values") or []]
    return ""


def _attributes(items: list[dict[str, Any]] | None) -> dict[str, Any]:
    return {item["key"]: _attribute_value(item.get("value") or {}) for item in items or []}


def _span_status(span: dict[str, Any], attributes: dict[str, Any]) -> str:
    if (span.get("status") or {}).get("code") == "STATUS_CODE_ERROR":
        return "error"
    # FastAPI/OTel marks 5xx on the attribute rather than the span status.
    try:
        if int(attributes.get("http.status_code", 0) or 0) >= 500:
            return "error"
    except (TypeError, ValueError):
        pass
    return "ok"


def _flatten_spans(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    for batch in payload.get("batches") or []:
        resource = _attributes((batch.get("resource") or {}).get("attributes"))
        service = resource.get("service.name", "unknown")
        for scope_span in batch.get("scopeSpans") or []:
            for span in scope_span.get("spans") or []:
                attributes = _attributes(span.get("attributes"))
                start = int(span.get("startTimeUnixNano", 0))
                end = int(span.get("endTimeUnixNano", 0))
                spans.append(
                    {
                        "id": _hex_id(span.get("spanId")) or "",
                        "parentId": _hex_id(span.get("parentSpanId")),
                        "name": span.get("name", ""),
                        "service": service,
                        "kind": span.get("kind", "SPAN_KIND_INTERNAL"),
                        "startUnixNano": start,
                        "durationMs": max((end - start) / 1_000_000, 0),
                        "status": _span_status(span, attributes),
                        "attributes": attributes,
                    }
                )
    return spans


def _build_trace(trace_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    spans = _flatten_spans(payload)
    if not spans:
        return {
            "id": trace_id,
            "rootService": "unknown",
            "operation": "unknown",
            "durationMs": 0.0,
            "status": "ok",
            "startUnixNano": 0,
            "spans": [],
        }

    span_ids = {span["id"] for span in spans}
    # A span whose parent was sampled away is still a root as far as this trace goes.
    roots = [span for span in spans if not span["parentId"] or span["parentId"] not in span_ids]
    trace_start = min(span["startUnixNano"] for span in spans)
    trace_end = max(span["startUnixNano"] + int(span["durationMs"] * 1_000_000) for span in spans)
    root = min(roots, key=lambda span: span["startUnixNano"]) if roots else spans[0]

    ordered = sorted(spans, key=lambda span: (span["startUnixNano"], span["name"]))
    for span in ordered:
        span["startOffsetMs"] = (span["startUnixNano"] - trace_start) / 1_000_000
        span["durationMs"] = round(span["durationMs"], 3)

    return {
        "id": trace_id,
        "rootService": root["service"],
        "operation": root["name"],
        "durationMs": round((trace_end - trace_start) / 1_000_000, 3),
        "status": "error" if any(span["status"] == "error" for span in spans) else "ok",
        "startUnixNano": trace_start,
        "spans": ordered,
    }


async def search_traces(
    settings: Settings,
    limit: int,
    range_minutes: int,
    service: str | None = None,
    min_duration_ms: int = 0,
) -> list[dict[str, Any]]:
    end = int(time.time())
    params: dict[str, Any] = {
        "limit": limit,
        "start": end - range_minutes * 60,
        "end": end,
    }
    if min_duration_ms > 0:
        params["minDuration"] = f"{min_duration_ms}ms"
    if service:
        # TraceQL: Tempo's tag-based `tags=` form was removed in favour of `q`.
        escaped = service.replace('"', '\\"')
        params["q"] = f'{{resource.service.name="{escaped}"}}'

    payload = await _get(settings, "/api/search", params)
    traces = []
    for trace in payload.get("traces") or []:
        start_nano = int(trace.get("startTimeUnixNano", 0))
        traces.append(
            {
                "id": trace.get("traceID", ""),
                "rootService": trace.get("rootServiceName", "unknown"),
                "operation": trace.get("rootTraceName", "unknown"),
                "durationMs": float(trace.get("durationMs", 0) or 0),
                "startUnixNano": start_nano,
            }
        )
    traces.sort(key=lambda item: item["startUnixNano"], reverse=True)
    return traces


async def get_trace(settings: Settings, trace_id: str) -> dict[str, Any]:
    payload = await _get(settings, f"/api/traces/{trace_id}")
    return _build_trace(trace_id, payload)


async def search_traces_summarised(
    settings: Settings,
    limit: int,
    range_minutes: int,
    service: str | None = None,
    min_duration_ms: int = 0,
) -> list[dict[str, Any]]:
    """Search results plus the per-trace fields (error status, span count, the
    services involved) that only exist once the spans are read. Tempo's search
    response carries none of them, so each hit is expanded concurrently."""
    found = await search_traces(settings, limit, range_minutes, service, min_duration_ms)

    async def expand(trace: dict[str, Any]) -> dict[str, Any]:
        try:
            detail = await get_trace(settings, trace["id"])
        except TempoUnavailableError as exc:
            # One unreadable trace shouldn't blank the whole list.
            logger.info("could not expand trace %s: %s", trace["id"], exc)
            return {**trace, "status": "ok", "spanCount": 0, "services": []}
        return {
            **trace,
            "status": detail["status"],
            "spanCount": len(detail["spans"]),
            "services": sorted({span["service"] for span in detail["spans"]}),
        }

    return list(await asyncio.gather(*(expand(trace) for trace in found)))


async def list_services(settings: Settings) -> list[str]:
    payload = await _get(settings, "/api/search/tag/service.name/values")
    return sorted(payload.get("tagValues") or [])
