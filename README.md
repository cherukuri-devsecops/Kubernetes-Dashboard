# Kubernetes Dashboard - Stage 3

Stage 3 adds live Kubernetes integration on top of the Stage 1 foundation and Stage 2 dashboard shell.

## What Is Included

- React, TypeScript, Vite, Tailwind CSS, and React Router frontend
- Dark application shell with sidebar, top navigation, footer, login, and protected routes
- FastAPI backend with Swagger/OpenAPI, health checks, configuration, logging, CORS, and token auth
- PostgreSQL and Redis wiring for local development
- Helm chart with Kubernetes namespace, NGINX Ingress, cert-manager issuer, External Secrets scaffold, and app workloads
- **Kubernetes Explorer**: live cluster info, nodes, namespaces, pods, deployments, services, statefulsets, daemonsets, jobs, and PVCs, read via the Kubernetes Python client
- **No mock data**: every panel — alerts, traces, events, reports, RBAC, search, notifications, and the assistant — is served from the live cluster

## Kubernetes Explorer (Stage 3)

The backend talks to the Kubernetes API using the official [Python client](https://github.com/kubernetes-client/python). It loads credentials in this order:

1. In-cluster config (when the backend runs as a pod — this is how the Helm chart deploys it)
2. Local kubeconfig (`KUBECONFIG` env var, or `~/.kube/config` by default) — used for local development

Endpoints (all under `/api/k8s`, all require a bearer token): `cluster`, `nodes`, `namespaces`, `pods`, `deployments`, `services`, `statefulsets`, `daemonsets`, `jobs`, `pvcs`, `serviceaccounts`, `roles`, `rolebindings`, `subjects`. The namespaced endpoints accept an optional `?namespace=` query parameter.

For `docker compose`, the backend container mounts `~/.kube` (override with `KUBECONFIG_HOST_PATH`) so it can reach whatever cluster your host kubeconfig points at (e.g. a local Kind/Minikube cluster). If the cluster's API server address isn't reachable from inside the container network, point your kubeconfig's `server:` at `host.docker.internal` instead of `127.0.0.1`.

In the cluster, the Helm chart creates a dedicated `ServiceAccount` bound to a read-only `ClusterRole` (get/list/watch on nodes, namespaces, pods, services, PVCs, deployments, statefulsets, daemonsets, jobs, service accounts, and RBAC roles/bindings) — no extra setup needed.

## Where Each Panel's Data Comes From

The dashboard holds no fixtures or generated sample data. Every figure on screen is read at request time:

| Area | Endpoint | Source |
| --- | --- | --- |
| Overview, Kubernetes explorer | `/api/k8s/*` | Kubernetes API |
| Metrics, gauges, top pods/namespaces | `/api/metrics/*` | Prometheus (cAdvisor, node-exporter, kube-state-metrics) |
| Logs | `/api/logs/search`, `/api/logs/stream` | Loki, and the Kubernetes API for live pod tailing |
| Events | `/api/events` | Kubernetes API |
| Alerts | `/api/alerts` | Prometheus alerting rules and active alerts |
| Traces | `/api/traces` | Tempo |
| Reports | `/api/reports/*` | Kubernetes API + Prometheus, computed per request |
| Admin (subjects, roles, bindings, service accounts) | `/api/k8s/*` | Kubernetes RBAC |
| Global search | `/api/search` | Kubernetes API |
| Notifications | `/api/alerts` + `/api/events` | Firing alerts and Warning events |
| Assistant | `/api/ai/query` | Whichever of the above answers the question, named in the reply |
| Terminal | `/api/exec/pod` | An interactive shell in the pod, over the Kubernetes exec API |

### Alerting rules

Prometheus ships with no alerting rules of its own, so the chart installs a rule set (`alert-rules.yml` in the Prometheus ConfigMap) covering node readiness and pressure, crash-looping and non-running pods, degraded deployments, pending PVCs, and dead scrape targets. The same rules are mounted into the `docker compose` Prometheus from `monitoring/prometheus/alert-rules.yml`. Without them the Alerts page correctly shows that nothing is configured.

### Pod terminal

The Terminal page opens a real shell inside a running container over a WebSocket, the same thing `kubectl exec -it` does. It is **enabled by default** (`exec.enabled` in the chart's values).

Understand what that grants before leaving it on: the backend gets `create` on `pods/exec`, so **anyone who can sign in to the dashboard can run commands in any pod the backend can reach**, including reading any secret mounted into those pods. Dashboard login is the only thing standing in front of that, so it should not be left on the demo credentials on a reachable address.

To constrain it:

- `exec.enabled: false` removes both the terminal and the RBAC grant
- `exec.allowedNamespaces: [observability]` confines the terminal to named namespaces
- `exec.shells` sets the shell fallback order (first one present in the image wins)

Every session is written to the backend log with the user, namespace, pod, and container.

### Assistant

`/api/ai/query` matches a question to an intent, runs the real queries for it, and answers with what they returned — each reply names the data sources behind it. There is no language model in the loop, so it cannot invent a number that the cluster did not report.

## Local Development

Backend:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn app.main:app --reload --app-dir backend
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open the frontend at `http://localhost:5173`. The default development login is:

- Email: `admin@example.com`
- Password: `admin123`

The backend OpenAPI docs are available at `http://localhost:8000/docs`.

## Existing Auth API

Set these values to use your own auth API instead of the built-in demo login:

```bash
AUTH_PROVIDER=external
AUTH_API_BASE_URL=https://auth.example.com
AUTH_API_LOGIN_PATH=/auth/login
AUTH_API_ME_PATH=/auth/me
```

The dashboard backend posts login requests to your auth API as:

```json
{"email":"user@example.com","password":"password"}
```

It accepts this response shape:

```json
{"access_token":"token","token_type":"bearer","user":{"email":"user@example.com","name":"User","role":"admin"}}
```

For protected routes, the dashboard backend calls `AUTH_API_ME_PATH` with `Authorization: Bearer <token>`. If your auth API does not have a `/me` endpoint, set `AUTH_API_ME_PATH=` and provide `AUTH_JWT_SECRET` so the backend can verify the token locally.

## Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

Services:

- Frontend: `http://localhost:8080`
- Backend: `http://localhost:8000`
- Backend docs: `http://localhost:8000/docs`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`

## Helm Deployment

Install these controllers first:

- NGINX Ingress Controller
- cert-manager
- External Secrets Operator

Install or upgrade with Helm:

```bash
helm upgrade --install kubernetes-dashboard ./helm/kubernetes-dashboard \
  --namespace kubernetes-dashboard
```

Render the chart before applying it:

```bash
helm template kubernetes-dashboard ./helm/kubernetes-dashboard \
  --namespace kubernetes-dashboard
```

The default chart values use the External Secrets fake provider so the stage is self-contained for development. Replace `externalSecrets.secretStore.spec` in `helm/kubernetes-dashboard/values.yaml` with your real provider before production.

For a local cluster without External Secrets installed, disable it and let Helm create a plain Kubernetes Secret:

```bash
helm upgrade --install kubernetes-dashboard ./helm/kubernetes-dashboard \
  --namespace kubernetes-dashboard \
  --set externalSecrets.enabled=false
```

If you prefer Helm to create the namespace outside the chart, add `--create-namespace` and set `namespace.create=false`.
