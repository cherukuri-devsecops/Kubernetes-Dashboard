from typing import Any

import httpx

from app.config import Settings


class LokiUnavailableError(RuntimeError):
    """Raised when Loki cannot be reached or returns an error response."""


def pod_logql(namespace: str | None, pod: str | None, container: str | None, query: str | None) -> str:
    # Fluent Bit's loki output flattens the nested `kubernetes` record field into
    # labels prefixed with "kubernetes_" (verified against a live cluster: the actual
    # labels are kubernetes_namespace_name / kubernetes_pod_name / kubernetes_container_name).
    selectors: list[str] = []
    if namespace:
        selectors.append(f'kubernetes_namespace_name="{namespace}"')
    if pod:
        selectors.append(f'kubernetes_pod_name="{pod}"')
    if container:
        selectors.append(f'kubernetes_container_name="{container}"')

    stream_selector = "{" + ",".join(selectors) + "}" if selectors else '{job="fluent-bit"}'
    if query:
        escaped = query.replace('"', '\\"')
        return f'{stream_selector} |= "{escaped}"'
    return stream_selector


async def query_range(
    settings: Settings,
    logql: str,
    start_ns: int,
    end_ns: int,
    limit: int,
    direction: str = "backward",
) -> list[dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{settings.loki_url}/loki/api/v1/query_range",
                params={
                    "query": logql,
                    "start": start_ns,
                    "end": end_ns,
                    "limit": limit,
                    "direction": direction,
                },
            )
    except httpx.HTTPError as exc:
        raise LokiUnavailableError(str(exc)) from exc

    if response.status_code >= 400:
        raise LokiUnavailableError(f"Loki returned {response.status_code}: {response.text}")

    body = response.json()
    if body.get("status") != "success":
        raise LokiUnavailableError(body.get("error", "Loki query failed"))

    entries: list[dict[str, Any]] = []
    for stream in body["data"]["result"]:
        labels = stream["stream"]
        for timestamp_ns, line in stream["values"]:
            entries.append(
                {
                    "timestamp": timestamp_ns,
                    "namespace": labels.get("kubernetes_namespace_name", ""),
                    "pod": labels.get("kubernetes_pod_name", ""),
                    "container": labels.get("kubernetes_container_name", ""),
                    "line": line,
                }
            )
    entries.sort(key=lambda e: e["timestamp"])
    return entries
