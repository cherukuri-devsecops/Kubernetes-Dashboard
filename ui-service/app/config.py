import os

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
KUBECONFIG_DIR = os.environ.get("KUBECONFIG_DIR", "/var/kubeconfigs")

AUTH_SERVICE_URL = os.environ.get("AUTH_SERVICE_URL", "")
AUTH_JWT_SECRET  = os.environ.get("AUTH_JWT_SECRET", "").strip()
ALLOWED_EMAILS   = {e.strip().lower() for e in
                    os.environ.get("ALLOWED_EMAILS", "").split(",") if e.strip()}

# Backend API service
BACKEND_SERVICE_URL = os.environ.get("BACKEND_SERVICE_URL", "http://backend-service:8000")

# Loki (log/event/audit storage) and SQLite (user config data)
LOKI_URL      = os.environ.get("LOKI_URL", "http://loki:3100").rstrip("/")
SQLITE_PATH   = os.environ.get("SQLITE_PATH", "/data/dashboard.db")
CLUSTER_SCOPE = os.environ.get("CLUSTER_SCOPE", "local")
