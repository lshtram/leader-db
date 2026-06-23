"""Local Superset config for the Leaders DB visualization increment.

This config is intentionally local-only. Secrets are read from
``infra/superset/superset.env`` through Docker Compose and are never committed.
"""

from __future__ import annotations

import os

SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]
SQLALCHEMY_DATABASE_URI = os.environ["SUPERSET_METADATA_DB_URI"]

DEBUG = False
ENABLE_PROXY_FIX = True
WTF_CSRF_ENABLED = True

SUPERSET_WEBSERVER_PROTOCOL = "http"
SUPERSET_WEBSERVER_ADDRESS = "0.0.0.0"
SUPERSET_WEBSERVER_PORT = 8088
SUPERSET_WEBSERVER_BASEURL = os.environ.get(
    "SUPERSET_WEBSERVER_BASEURL",
    "http://localhost:8088",
)

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_DEFAULT_TIMEOUT": 300,
    "CACHE_KEY_PREFIX": "leaders_db_superset_",
    "CACHE_REDIS_HOST": os.environ.get("REDIS_HOST", "superset-redis"),
    "CACHE_REDIS_PORT": 6379,
    "CACHE_REDIS_DB": 1,
}

DATA_CACHE_CONFIG = CACHE_CONFIG
