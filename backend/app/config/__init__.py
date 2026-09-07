from functools import lru_cache
from urllib.parse import urljoin

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Kubernetes Dashboard"
    environment: str = "development"
    log_level: str = "INFO"
    # When set, logs are also written as JSON lines here for Fluent Bit to tail.
    log_file: str = ""
    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    database_url: str = "postgresql://dashboard:dashboard@localhost:5432/dashboard"
    redis_url: str = "redis://localhost:6379/0"

    kubeconfig_path: str = ""
    kubeconfig_context: str = ""

    prometheus_url: str = "http://localhost:9090"
    loki_url: str = "http://localhost:3100"
    tempo_url: str = "http://localhost:3200"
    otel_enabled: bool = True
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "kubernetes-dashboard-backend"

    jwt_secret: str = "change-this-stage-1-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    auth_provider: str = "demo"
    auth_api_base_url: str = ""
    auth_api_login_path: str = "/auth/login"
    auth_api_me_path: str = "/auth/me"
    auth_api_timeout_seconds: float = 5
    auth_jwt_secret: str = ""
    auth_jwt_algorithm: str = "HS256"
    # How long a verified token is trusted without re-asking the auth API. A page
    # load fans out into ~10 API calls, and one /auth/me per call both hammers the
    # provider and turns any blip into blank panels.
    auth_cache_ttl_seconds: int = 60
    # How long a previously verified token keeps working while the auth API is
    # failing (5xx/unreachable). Explicit 401/403 rejections ignore this.
    auth_cache_stale_seconds: int = 300

    # Interactive pod exec. This is the only write path the dashboard has: it
    # needs create on pods/exec, which is enough to read any secret mounted into
    # a reachable pod, so it is off unless a deployment turns it on.
    exec_enabled: bool = False
    # Comma-separated. Empty means every namespace the ServiceAccount can reach.
    exec_allowed_namespaces: str = ""
    # Tried in order; the first shell present in the image wins.
    exec_shells: str = "/bin/bash,/bin/sh"

    # Writes sample incidents into an empty database. Dev stacks only.
    seed_demo_data: bool = False

    demo_user_email: str = "admin@example.com"
    demo_user_password: str = "admin123"
    demo_user_name: str = "Platform Admin"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def exec_allowed_namespace_list(self) -> list[str]:
        return [ns.strip() for ns in self.exec_allowed_namespaces.split(",") if ns.strip()]

    @property
    def exec_shell_list(self) -> list[str]:
        return [shell.strip() for shell in self.exec_shells.split(",") if shell.strip()]

    @property
    def use_external_auth(self) -> bool:
        return self.auth_provider.lower() == "external"

    def auth_api_url(self, path: str) -> str:
        return urljoin(f"{self.auth_api_base_url.rstrip('/')}/", path.lstrip("/"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
