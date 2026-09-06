from typing import Any

import httpx

from app.config import Settings

# Physical network interfaces only - excludes veth/cni/cali/docker/flannel/lo,
# verified against a live cluster (Calico CNI: interfaces named cali*).
_PHYSICAL_IFACE_FILTER = 'device!~"lo|veth.*|cali.*|docker.*|flannel.*|cni.*"'

CLUSTER_CPU_QUERY = 'sum(rate(container_cpu_usage_seconds_total{container!=""}[5m]))'
CLUSTER_MEMORY_QUERY = 'sum(container_memory_working_set_bytes{container!=""})'
CLUSTER_NETWORK_RX_QUERY = 'sum(rate(container_network_receive_bytes_total{namespace!=""}[5m]))'
CLUSTER_NETWORK_TX_QUERY = 'sum(rate(container_network_transmit_bytes_total{namespace!=""}[5m]))'
CLUSTER_DISK_USED_QUERY = 'sum(node_filesystem_size_bytes{mountpoint="/"} - node_filesystem_avail_bytes{mountpoint="/"})'
CLUSTER_DISK_TOTAL_QUERY = 'sum(node_filesystem_size_bytes{mountpoint="/"})'
CLUSTER_DISK_READ_QUERY = "sum(rate(node_disk_read_bytes_total[5m]))"
CLUSTER_DISK_WRITE_QUERY = "sum(rate(node_disk_written_bytes_total[5m]))"
CLUSTER_CPU_TOTAL_QUERY = "count(count by (cpu, node) (node_cpu_seconds_total))"
CLUSTER_MEMORY_TOTAL_QUERY = "sum(node_memory_MemTotal_bytes)"

NODE_CPU_QUERY = '1 - avg by (node) (rate(node_cpu_seconds_total{mode="idle"}[5m]))'
NODE_MEMORY_USED_QUERY = "node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes"
NODE_MEMORY_TOTAL_QUERY = "avg by (node) (node_memory_MemTotal_bytes)"
NODE_NETWORK_RX_QUERY = f"sum by (node) (rate(node_network_receive_bytes_total{{{_PHYSICAL_IFACE_FILTER}}}[5m]))"
NODE_NETWORK_TX_QUERY = f"sum by (node) (rate(node_network_transmit_bytes_total{{{_PHYSICAL_IFACE_FILTER}}}[5m]))"
NODE_DISK_USED_QUERY = (
    'avg by (node) (node_filesystem_size_bytes{mountpoint="/"} - node_filesystem_avail_bytes{mountpoint="/"})'
)
NODE_DISK_TOTAL_QUERY = 'avg by (node) (node_filesystem_size_bytes{mountpoint="/"})'
NODE_DISK_READ_QUERY = "sum by (node) (rate(node_disk_read_bytes_total[5m]))"
NODE_DISK_WRITE_QUERY = "sum by (node) (rate(node_disk_written_bytes_total[5m]))"

NAMESPACE_CPU_QUERY = 'sum by (namespace) (rate(container_cpu_usage_seconds_total{container!="",namespace!=""}[5m]))'
NAMESPACE_MEMORY_QUERY = 'sum by (namespace) (container_memory_working_set_bytes{container!="",namespace!=""})'
NAMESPACE_NETWORK_RX_QUERY = 'sum by (namespace) (rate(container_network_receive_bytes_total{namespace!=""}[5m]))'
NAMESPACE_NETWORK_TX_QUERY = 'sum by (namespace) (rate(container_network_transmit_bytes_total{namespace!=""}[5m]))'


def _escape_label_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


class PrometheusUnavailableError(RuntimeError):
    """Raised when Prometheus cannot be reached or returns an error response."""


async def _get(settings: Settings, path: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{settings.prometheus_url}{path}", params=params)
    except httpx.HTTPError as exc:
        raise PrometheusUnavailableError(str(exc)) from exc

    if response.status_code >= 400:
        raise PrometheusUnavailableError(f"Prometheus returned {response.status_code}")

    body = response.json()
    if body.get("status") != "success":
        raise PrometheusUnavailableError(body.get("error", "Prometheus query failed"))
    return body["data"]


async def query(settings: Settings, promql: str) -> dict[str, Any]:
    return await _get(settings, "/api/v1/query", {"query": promql})


async def query_range(
    settings: Settings, promql: str, start: float, end: float, step: str
) -> dict[str, Any]:
    return await _get(
        settings,
        "/api/v1/query_range",
        {"query": promql, "start": start, "end": end, "step": step},
    )


def _scalar(data: dict[str, Any]) -> float:
    result = data.get("result") or []
    if not result:
        return 0.0
    return float(result[0]["value"][1])


def _series(data: dict[str, Any]) -> list[dict[str, Any]]:
    result = data.get("result") or []
    points: list[dict[str, Any]] = []
    if not result:
        return points
    for timestamp, value in result[0]["values"]:
        points.append({"time": timestamp, "value": float(value)})
    return points


def _by_label(data: dict[str, Any], label: str) -> dict[str, float]:
    result = data.get("result") or []
    return {item["metric"].get(label, "unknown"): float(item["value"][1]) for item in result}


async def cluster_usage(settings: Settings) -> dict[str, float]:
    cpu = await query(settings, CLUSTER_CPU_QUERY)
    memory = await query(settings, CLUSTER_MEMORY_QUERY)
    net_rx = await query(settings, CLUSTER_NETWORK_RX_QUERY)
    net_tx = await query(settings, CLUSTER_NETWORK_TX_QUERY)
    disk_used = await query(settings, CLUSTER_DISK_USED_QUERY)
    disk_total = await query(settings, CLUSTER_DISK_TOTAL_QUERY)
    cpu_total = await query(settings, CLUSTER_CPU_TOTAL_QUERY)
    memory_total = await query(settings, CLUSTER_MEMORY_TOTAL_QUERY)
    return {
        "cpuCores": _scalar(cpu),
        "cpuTotalCores": _scalar(cpu_total),
        "memoryBytes": _scalar(memory),
        "memoryTotalBytes": _scalar(memory_total),
        "networkRxBytesPerSec": _scalar(net_rx),
        "networkTxBytesPerSec": _scalar(net_tx),
        "diskUsedBytes": _scalar(disk_used),
        "diskTotalBytes": _scalar(disk_total),
    }


async def cluster_usage_range(
    settings: Settings, start: float, end: float, step: str
) -> dict[str, list[dict[str, Any]]]:
    cpu = await query_range(settings, CLUSTER_CPU_QUERY, start, end, step)
    memory = await query_range(settings, CLUSTER_MEMORY_QUERY, start, end, step)
    net_rx = await query_range(settings, CLUSTER_NETWORK_RX_QUERY, start, end, step)
    net_tx = await query_range(settings, CLUSTER_NETWORK_TX_QUERY, start, end, step)
    disk_read = await query_range(settings, CLUSTER_DISK_READ_QUERY, start, end, step)
    disk_write = await query_range(settings, CLUSTER_DISK_WRITE_QUERY, start, end, step)
    return {
        "cpu": _series(cpu),
        "memory": _series(memory),
        "networkRx": _series(net_rx),
        "networkTx": _series(net_tx),
        "diskRead": _series(disk_read),
        "diskWrite": _series(disk_write),
    }


async def node_usage(settings: Settings) -> list[dict[str, Any]]:
    cpu = await query(settings, NODE_CPU_QUERY)
    memory_used = await query(settings, NODE_MEMORY_USED_QUERY)
    memory_total = await query(settings, NODE_MEMORY_TOTAL_QUERY)
    net_rx = await query(settings, NODE_NETWORK_RX_QUERY)
    net_tx = await query(settings, NODE_NETWORK_TX_QUERY)
    disk_used = await query(settings, NODE_DISK_USED_QUERY)
    disk_total = await query(settings, NODE_DISK_TOTAL_QUERY)

    cpu_by_node = _by_label(cpu, "node")
    memory_used_by_node = _by_label(memory_used, "node")
    memory_total_by_node = _by_label(memory_total, "node")
    net_rx_by_node = _by_label(net_rx, "node")
    net_tx_by_node = _by_label(net_tx, "node")
    disk_used_by_node = _by_label(disk_used, "node")
    disk_total_by_node = _by_label(disk_total, "node")

    nodes: list[dict[str, Any]] = []
    for name in sorted(set(cpu_by_node) | set(memory_total_by_node)):
        total = memory_total_by_node.get(name, 0.0)
        used = memory_used_by_node.get(name, 0.0)
        disk_total_bytes = disk_total_by_node.get(name, 0.0)
        disk_used_bytes = disk_used_by_node.get(name, 0.0)
        nodes.append(
            {
                "name": name,
                "cpuPercent": round(cpu_by_node.get(name, 0.0) * 100, 1),
                "memoryPercent": round((used / total) * 100, 1) if total else 0.0,
                "memoryBytes": used,
                "memoryTotalBytes": total,
                "networkRxBytesPerSec": net_rx_by_node.get(name, 0.0),
                "networkTxBytesPerSec": net_tx_by_node.get(name, 0.0),
                "diskPercent": round((disk_used_bytes / disk_total_bytes) * 100, 1) if disk_total_bytes else 0.0,
                "diskUsedBytes": disk_used_bytes,
                "diskTotalBytes": disk_total_bytes,
            }
        )
    return nodes


async def node_usage_range(
    settings: Settings, node: str, start: float, end: float, step: str
) -> dict[str, list[dict[str, Any]]]:
    escaped = _escape_label_value(node)
    cpu_q = f'1 - avg(rate(node_cpu_seconds_total{{mode="idle",node="{escaped}"}}[5m]))'
    mem_used_q = f'node_memory_MemTotal_bytes{{node="{escaped}"}} - node_memory_MemAvailable_bytes{{node="{escaped}"}}'
    net_rx_q = f'sum(rate(node_network_receive_bytes_total{{{_PHYSICAL_IFACE_FILTER},node="{escaped}"}}[5m]))'
    net_tx_q = f'sum(rate(node_network_transmit_bytes_total{{{_PHYSICAL_IFACE_FILTER},node="{escaped}"}}[5m]))'
    disk_read_q = f'sum(rate(node_disk_read_bytes_total{{node="{escaped}"}}[5m]))'
    disk_write_q = f'sum(rate(node_disk_written_bytes_total{{node="{escaped}"}}[5m]))'

    cpu = await query_range(settings, cpu_q, start, end, step)
    memory = await query_range(settings, mem_used_q, start, end, step)
    net_rx = await query_range(settings, net_rx_q, start, end, step)
    net_tx = await query_range(settings, net_tx_q, start, end, step)
    disk_read = await query_range(settings, disk_read_q, start, end, step)
    disk_write = await query_range(settings, disk_write_q, start, end, step)
    return {
        "cpu": _series(cpu),
        "memory": _series(memory),
        "networkRx": _series(net_rx),
        "networkTx": _series(net_tx),
        "diskRead": _series(disk_read),
        "diskWrite": _series(disk_write),
    }


async def namespace_usage(settings: Settings) -> list[dict[str, Any]]:
    cpu = await query(settings, NAMESPACE_CPU_QUERY)
    memory = await query(settings, NAMESPACE_MEMORY_QUERY)
    net_rx = await query(settings, NAMESPACE_NETWORK_RX_QUERY)
    net_tx = await query(settings, NAMESPACE_NETWORK_TX_QUERY)

    cpu_by_ns = _by_label(cpu, "namespace")
    memory_by_ns = _by_label(memory, "namespace")
    net_rx_by_ns = _by_label(net_rx, "namespace")
    net_tx_by_ns = _by_label(net_tx, "namespace")

    names = sorted(set(cpu_by_ns) | set(memory_by_ns) | set(net_rx_by_ns) | set(net_tx_by_ns))
    return [
        {
            "namespace": name,
            "cpuCores": round(cpu_by_ns.get(name, 0.0), 4),
            "memoryBytes": memory_by_ns.get(name, 0.0),
            "networkRxBytesPerSec": net_rx_by_ns.get(name, 0.0),
            "networkTxBytesPerSec": net_tx_by_ns.get(name, 0.0),
        }
        for name in names
    ]


async def namespace_usage_range(
    settings: Settings, namespace: str, start: float, end: float, step: str
) -> dict[str, list[dict[str, Any]]]:
    escaped = _escape_label_value(namespace)
    cpu_q = f'sum(rate(container_cpu_usage_seconds_total{{container!="",namespace="{escaped}"}}[5m]))'
    mem_q = f'sum(container_memory_working_set_bytes{{container!="",namespace="{escaped}"}})'
    net_rx_q = f'sum(rate(container_network_receive_bytes_total{{namespace="{escaped}"}}[5m]))'
    net_tx_q = f'sum(rate(container_network_transmit_bytes_total{{namespace="{escaped}"}}[5m]))'

    cpu = await query_range(settings, cpu_q, start, end, step)
    memory = await query_range(settings, mem_q, start, end, step)
    net_rx = await query_range(settings, net_rx_q, start, end, step)
    net_tx = await query_range(settings, net_tx_q, start, end, step)
    return {
        "cpu": _series(cpu),
        "memory": _series(memory),
        "networkRx": _series(net_rx),
        "networkTx": _series(net_tx),
    }


async def pod_usage(settings: Settings, namespace: str) -> list[dict[str, Any]]:
    escaped = _escape_label_value(namespace)
    cpu_q = f'sum by (pod) (rate(container_cpu_usage_seconds_total{{container!="",namespace="{escaped}"}}[5m]))'
    mem_q = f'sum by (pod) (container_memory_working_set_bytes{{container!="",namespace="{escaped}"}})'
    net_rx_q = f'sum by (pod) (rate(container_network_receive_bytes_total{{namespace="{escaped}"}}[5m]))'
    net_tx_q = f'sum by (pod) (rate(container_network_transmit_bytes_total{{namespace="{escaped}"}}[5m]))'

    cpu = await query(settings, cpu_q)
    memory = await query(settings, mem_q)
    net_rx = await query(settings, net_rx_q)
    net_tx = await query(settings, net_tx_q)

    cpu_by_pod = _by_label(cpu, "pod")
    memory_by_pod = _by_label(memory, "pod")
    net_rx_by_pod = _by_label(net_rx, "pod")
    net_tx_by_pod = _by_label(net_tx, "pod")

    names = sorted(set(cpu_by_pod) | set(memory_by_pod) | set(net_rx_by_pod) | set(net_tx_by_pod))
    return [
        {
            "pod": name,
            "cpuCores": round(cpu_by_pod.get(name, 0.0), 4),
            "memoryBytes": memory_by_pod.get(name, 0.0),
            "networkRxBytesPerSec": net_rx_by_pod.get(name, 0.0),
            "networkTxBytesPerSec": net_tx_by_pod.get(name, 0.0),
        }
        for name in names
    ]


async def pod_usage_range(
    settings: Settings, namespace: str, pod: str, start: float, end: float, step: str
) -> dict[str, list[dict[str, Any]]]:
    ns = _escape_label_value(namespace)
    pod_name = _escape_label_value(pod)
    cpu_q = f'sum(rate(container_cpu_usage_seconds_total{{container!="",namespace="{ns}",pod="{pod_name}"}}[5m]))'
    mem_q = f'sum(container_memory_working_set_bytes{{container!="",namespace="{ns}",pod="{pod_name}"}})'
    net_rx_q = f'sum(rate(container_network_receive_bytes_total{{namespace="{ns}",pod="{pod_name}"}}[5m]))'
    net_tx_q = f'sum(rate(container_network_transmit_bytes_total{{namespace="{ns}",pod="{pod_name}"}}[5m]))'

    cpu = await query_range(settings, cpu_q, start, end, step)
    memory = await query_range(settings, mem_q, start, end, step)
    net_rx = await query_range(settings, net_rx_q, start, end, step)
    net_tx = await query_range(settings, net_tx_q, start, end, step)
    return {
        "cpu": _series(cpu),
        "memory": _series(memory),
        "networkRx": _series(net_rx),
        "networkTx": _series(net_tx),
    }
