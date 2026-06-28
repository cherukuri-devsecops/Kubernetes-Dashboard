# CLAUDE.md — Kubernetes Observability Dashboard

## What this project is

A self-hosted Kubernetes observability dashboard with two Python microservices and a full observability stack. Users upload a kubeconfig (or use in-cluster auth) and get a browser UI for pods, nodes, logs, metrics, and traces.

**Two deployment modes:**
- `docker compose up` — local development and single-node self-hosting
- `helm install` — production Kubernetes deployment with NFS-backed persistent storage

---

## Repository layout

```
.
├── ui-service/               # Flask + Gunicorn/Gevent — browser UI (port 5000)
│   ├── app/
│   │   ├── main.py           # Flask app factory, blueprint registration, context_processor
│   │   ├── config.py         # All env-var reads (single source of truth)
│   │   ├── auth_utils.py     # CSRF protection, request logging
│   │   ├── backend_client.py # HTTP client that calls backend-service
│   │   ├── database.py       # Public DB API (delegates to storage.py + loki_client.py)
│   │   ├── storage.py        # SQLite read/write (kubeconfigs, annotations, query history)
│   │   ├── loki_client.py    # Loki log push client
│   │   ├── cache.py          # In-process TTL cache
│   │   ├── formatters.py     # Jinja2 filter helpers
│   │   ├── k8s_obj.py        # Wrapper that makes K8s dicts attribute-accessible
│   │   ├── plugin_loader.py  # Discovers and registers plugins at startup
│   │   ├── routes/           # Flask blueprints (one file per feature area)
│   │   │   ├── auth.py       # Google OAuth flow
│   │   │   ├── dashboard.py  # Main views + pod_exec_ws WebSocket handler
│   │   │   ├── resources.py  # Generic K8s resource views
│   │   │   ├── query.py      # PromQL/LogQL ad-hoc console
│   │   │   ├── history.py    # SQLite query history
│   │   │   ├── apm.py        # Trace explorer
│   │   │   ├── health.py     # /health endpoint
│   │   │   ├── setup.py      # Cluster setup / kubeconfig upload
│   │   │   └── users.py      # User management
│   │   ├── plugins/          # Drop-in extension packages
│   │   └── templates/        # Jinja2 HTML (dark monospace theme)
│   │       └── partials/     # HTMX partial fragments
│   └── Dockerfile
│
├── backend-service/          # FastAPI + Uvicorn — K8s/observability API (port 8000)
│   ├── app/
│   │   ├── main.py           # FastAPI app, CORS, OTEL, Prometheus instrumentator
│   │   ├── k8s_client.py     # ApiClient factory — reads auth from X-* request headers
│   │   ├── prom_client.py    # PromQL query helper
│   │   ├── loki_client.py    # LogQL query helper
│   │   ├── pollers.py        # Background asyncio tasks (event/metric polling → SQLite)
│   │   ├── utils.py          # Shared utilities
│   │   └── routers/          # FastAPI routers (one file per resource type)
│   │       ├── clusters.py, nodes.py, pods.py, deployments.py
│   │       ├── logs.py, metrics.py, traces.py, events.py
│   │       ├── rbac.py, query.py, resources.py, streaming.py, raw.py
│   └── Dockerfile
│
├── helm/kube-dashboard/      # Helm chart (Kubernetes deployment)
│   ├── Chart.yaml
│   ├── values.yaml           # All tunable defaults
│   └── templates/            # 22 Kubernetes manifests
│
├── docker-compose.yml        # Local stack (UI, Backend, Loki, Prometheus, Tempo)
├── loki-config.yaml          # Loki configuration (S3 backend)
├── prometheus.yml            # Prometheus scrape config
├── tempo-config.yaml         # Tempo configuration (local storage)
└── fluent-bit.conf           # Fluent Bit (Linux profile only)
```

---

## Running locally

```bash
# Core stack (all platforms)
docker compose up -d

# With log/metric collectors (Linux only)
docker compose --profile linux up -d

# Rebuild after code changes
docker compose build && docker compose up -d
```

| Service | Local URL |
|---|---|
| UI | http://localhost:5002 |
| Backend API + Swagger | http://localhost:8001/docs |
| Prometheus | http://localhost:9090 |
| Loki | http://localhost:3100 |
| Tempo | http://localhost:3200 |

Health checks:
```bash
curl http://localhost:8001/health   # backend aggregated health
curl http://localhost:5002/health   # UI health
```

---

## Key architectural decisions

### Stateless backend
The backend-service holds **no session state**. Every request from the UI carries Kubernetes credentials in headers:

| Header | Value |
|---|---|
| `X-Auth-Mode` | `kubeconfig` \| `token` \| `incluster` \| `local` |
| `X-Kubeconfig-B64` | base64-encoded kubeconfig YAML |
| `X-K8s-Token` | bearer token (token mode) |
| `X-K8s-Server` | API server URL (token mode) |
| `X-K8s-Context` | active context name |

The `_api_client()` factory in `backend-service/app/k8s_client.py` reads these headers and returns a configured `ApiClient`. No kubeconfig is stored in the backend.

### SQLite as shared state
Both services mount the same volume at `/data/dashboard.db`. The UI writes kubeconfigs, annotations, and query history; the backend writes event/metric poll results. This file is the only stateful data that must persist.

### Loki for audit/logs
Audit events (login, kubeconfig upload, pod delete) are pushed to Loki via `ui-service/app/loki_client.py`. The UI queries them back via the backend's `/logs` router.

### HTMX for live updates
The UI uses HTMX polling (every 15 s) to refresh resource tables as partial HTML fragments. No JavaScript framework. Templates under `templates/partials/` are the HTMX targets.

### Gevent for concurrent SSE
The UI server uses Gunicorn + Gevent workers so many SSE log streams can run concurrently without blocking other requests. Never switch to sync Gunicorn workers.

---

## Adding a new backend route

1. Create `backend-service/app/routers/myfeature.py`:

```python
from fastapi import APIRouter, Depends
from ..k8s_client import _header_dep, core_v1
from kubernetes.client import ApiClient

router = APIRouter(prefix="/myfeature", tags=["myfeature"])

@router.get("/")
def list_things(ac: ApiClient = Depends(_header_dep)):
    v1 = core_v1(ac)
    return v1.list_something_for_all_namespaces().to_dict()
```

2. Import and register in `backend-service/app/main.py`:

```python
from .routers import myfeature
# ...
app.include_router(myfeature.router)
```

## Adding a new UI blueprint

1. Create `ui-service/app/routes/mypage.py` as a Flask Blueprint.
2. Register it in `ui-service/app/main.py` alongside the others.
3. Add the nav entry to the `nav` list in `inject_globals()` in `main.py`.
4. Create the Jinja2 template in `ui-service/app/templates/`.

## Adding a plugin

Drop a package into `ui-service/app/plugins/myplugin/__init__.py` that exports:

```python
name = "My Plugin"
nav_label = "My Page"
nav_icon = "ti-star"        # Tabler icon class
nav_url = "/myplugin"

def register(app):
    from flask import Blueprint
    bp = Blueprint("myplugin", __name__)
    # register routes on bp
    app.register_blueprint(bp)
```

The plugin loader calls `register(app)` at startup. No core changes needed.

---

## Environment variables

All env-var reads in the UI are centralised in `ui-service/app/config.py`. Never read `os.environ` directly in route files.

### UI Service
| Variable | Default | Notes |
|---|---|---|
| `SECRET_KEY` | `change-me-in-production` | Flask session key — must be set in production |
| `AUTH_SERVICE_URL` | `""` | Google OAuth initiation URL |
| `AUTH_JWT_SECRET` | `""` | JWT validation secret for OAuth callback |
| `OAUTH_REDIRECT_URI` | `http://localhost:5002/auth/callback` | Must match Google Cloud Console |
| `ALLOWED_EMAILS` | `""` | Comma-separated; empty = allow all |
| `SESSION_COOKIE_SECURE` | `0` | Set `1` behind HTTPS |
| `TRUST_PROXY_HEADERS` | `0` | Set `1` behind a reverse proxy |
| `BACKEND_SERVICE_URL` | `http://backend-service:8000` | Backend API base URL |
| `LOKI_URL` | `http://loki:3100` | Loki push endpoint |
| `SQLITE_PATH` | `/data/dashboard.db` | Shared SQLite path |
| `CLUSTER_SCOPE` | `local` | `local` or `incluster` |
| `DB_POLLER_ENABLED` | `1` | Background event/metric polling |
| `EVENT_POLL_INTERVAL` | `30` | Seconds between K8s event polls |
| `METRIC_POLL_INTERVAL` | `60` | Seconds between Prometheus metric polls |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `""` | OTLP gRPC endpoint; no-op when unset |

### Backend Service
| Variable | Default | Notes |
|---|---|---|
| `PROMETHEUS_URL` | `http://prometheus:9090` | Prometheus base URL |
| `LOKI_URL` | `http://loki:3100` | Loki base URL |
| `TEMPO_URL` | `http://tempo:3200` | Tempo HTTP base URL |
| `UI_ORIGIN` | `http://localhost:5002` | CORS allowed origin |
| `SQLITE_PATH` | `/data/dashboard.db` | Shared SQLite path |
| `CLUSTER_SCOPE` | `local` | `local` or `incluster` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `""` | OTLP gRPC endpoint; no-op when unset |

---

## Helm chart

Chart root: `helm/kube-dashboard/`

```bash
# Install with NFS storage
helm install kube-dash ./helm/kube-dashboard \
  --namespace kube-dashboard --create-namespace \
  --set nfs.server=<NFS_IP> \
  --set secrets.secretKey=<RANDOM_SECRET>

# Dry-run / template preview
helm template kube-dash ./helm/kube-dashboard --set nfs.server=1.2.3.4

# Lint
helm lint ./helm/kube-dashboard

# Upgrade
helm upgrade kube-dash ./helm/kube-dashboard --namespace kube-dashboard --reuse-values

# Uninstall (PVs are Retain — delete manually)
helm uninstall kube-dash --namespace kube-dashboard
```

### NFS volumes
| PV name | NFS path | Used by |
|---|---|---|
| `*-sqlite` | `/data/nfs/dashboard/sqlite` | ui-service + backend-service |
| `*-prometheus` | `/data/nfs/dashboard/prometheus` | prometheus |

Pre-create these directories on the NFS server before `helm install`:
```bash
mkdir -p /data/nfs/dashboard/{sqlite,prometheus}
chmod 777 /data/nfs/dashboard/{sqlite,prometheus}
```

### RBAC
The backend runs under its own ServiceAccount with a ClusterRole granting read-only access to pods, nodes, deployments, services, events, configmaps, ingresses, jobs, PVCs, and the metrics API. The ClusterRole rules are in `values.yaml` under `backendService.rbac.rules`.

### Key values knobs
| Key | Default |
|---|---|
| `nfs.server` | `""` (required) |
| `nfs.sqlitePath` | `/data/nfs/dashboard/sqlite` |
| `nfs.prometheusPath` | `/data/nfs/dashboard/prometheus` |
| `sqlite.persistence.size` | `1Gi` |
| `prometheus.persistence.size` | `10Gi` |
| `prometheus.retention` | `15d` |
| `ingress.enabled` | `false` |
| `ingress.host` | `kube-dashboard.local` |

---

## Docker images

| Image | Built from |
|---|---|
| `cherukuri1991/kube-dashboard-ui:latest` | `ui-service/Dockerfile` |
| `cherukuri1991/kube-dashboard-backend:latest` | `backend-service/Dockerfile` |

Both images run as non-root (`appuser`, UID 1000). The `/data` directory is created and owned by `appuser` in the Dockerfile.

```bash
docker compose build          # build both
docker compose push           # push to Docker Hub
```

---

## Conventions

- **No comments on obvious code.** Only add a comment when the *why* is non-obvious (workaround, hidden constraint, subtle invariant).
- **All env reads go through `config.py`** in the UI service. Don't scatter `os.environ.get()` calls in route files.
- **Backend is stateless.** Never store K8s credentials in the backend process. They always come from headers.
- **Gevent workers.** Don't add blocking I/O in UI route handlers without wrapping it — the gevent event loop will stall.
- **Jinja2 partials for HTMX.** Routes that serve HTMX targets return `render_template("partials/foo.html", ...)`, not full pages.
- **k8s_obj wrapper.** Use `k8s_obj(items)` from `ui-service/app/k8s_obj.py` to convert K8s API dicts into attribute-accessible objects before passing to templates.
- **Frontend is fully vendored.** Chart.js, CodeMirror, HTMX, and Tabler Icons are in `ui-service/app/static/vendor/`. Never add CDN links.
- **Helm chart lint before committing.** Run `helm lint ./helm/kube-dashboard` after any template change.
