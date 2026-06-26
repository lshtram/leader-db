"""Safety checks for Cloudflare visualization access templates."""

from __future__ import annotations

from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CF_DIR = PROJECT_ROOT / "infra" / "cloudflare"
SUPERSET_DIR = PROJECT_ROOT / "infra" / "superset"


def test_cloudflare_secret_files_are_gitignored() -> None:
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "infra/cloudflare/cloudflared.env" in gitignore
    assert "infra/cloudflare/*.json" in gitignore
    assert "infra/cloudflare/*.key" in gitignore


def test_local_managed_config_template_has_safe_ingress() -> None:
    config = yaml.safe_load((CF_DIR / "config.yml.template").read_text(encoding="utf-8"))

    ingress = config["ingress"]
    assert ingress[0]["hostname"] == "viz.chopsworkshop.com"
    assert ingress[0]["service"] == "http://localhost:8088"
    assert ingress[-1] == {"service": "http_status:404"}


def test_cloudflared_compose_uses_token_without_publishing_ports() -> None:
    compose = yaml.safe_load((CF_DIR / "docker-compose.yml").read_text(encoding="utf-8"))
    service = compose["services"]["cloudflared"]

    assert "cloudflare/cloudflared" in service["image"]
    assert "${TUNNEL_TOKEN" in service["command"]
    assert "cloudflared.env" in service["env_file"]
    assert "ports" not in service
    assert "host.docker.internal:host-gateway" in service["extra_hosts"]


def test_cloudflare_runbook_requires_access_before_route() -> None:
    guide = (PROJECT_ROOT / "docs" / "testing-guide-viz-cloudflare.md").read_text(
        encoding="utf-8"
    )

    assert "Do **not** create the public hostname route" in guide
    assert "explicit email allowlist" in guide
    assert "It must not show the Superset login page directly" in guide


def test_superset_config_allows_read_only_sqlite_viz_artifact() -> None:
    """Superset must allow the mounted SQLite viz artifact as a data source."""
    config = (SUPERSET_DIR / "superset_config.py").read_text(encoding="utf-8")

    assert "PREVENT_UNSAFE_DB_CONNECTIONS = False" in config
    assert "/leaders-db-viz:ro" in config
    assert "sqlite:////leaders-db-viz/superset_viz.sqlite" in config


def test_superset_compose_routes_through_nginx_proxy() -> None:
    compose = yaml.safe_load((SUPERSET_DIR / "docker-compose.yml").read_text(encoding="utf-8"))

    superset = compose["services"]["superset-app"]
    proxy = compose["services"]["superset-proxy"]

    assert "ports" not in superset
    assert proxy["image"] == "nginx:1.27-alpine"
    assert "superset" in proxy["networks"]["default"]["aliases"]
    assert proxy["ports"] == ["127.0.0.1:8088:8088"]
    assert "./nginx-conf:/etc/nginx/conf.d:ro" in proxy["volumes"]
    assert "./reports:/usr/share/nginx/html/reports:ro" in proxy["volumes"]
    assert any(
        "/reports/briefs/html:/usr/share/nginx/html/briefs:ro" in v for v in proxy["volumes"]
    )
    assert any(
        "/reports/visualizations:/usr/share/nginx/html/visualizations:ro" in v
        for v in proxy["volumes"]
    )


def test_nginx_proxy_serves_reports_briefs_and_visualizations() -> None:
    nginx_conf = (SUPERSET_DIR / "nginx-conf" / "default.conf").read_text(encoding="utf-8")

    assert "listen 8088" in nginx_conf
    assert "location /reports/" in nginx_conf
    assert "location /reports/briefs/" in nginx_conf
    assert "location /visualizations/" in nginx_conf
    assert "location /reports/visualizations/" in nginx_conf
    assert "proxy_pass http://superset-app:8088" in nginx_conf
    assert "Cache-Control \"no-store, must-revalidate\"" in nginx_conf


def test_reports_index_links_customer_pages() -> None:
    index = (SUPERSET_DIR / "reports" / "index.html").read_text(encoding="utf-8")

    assert "country-metrics-dashboard.html" in index
    assert "briefs/us-equity-ownership.html" in index
    assert "briefs/us-market-size-baseline.html" in index
