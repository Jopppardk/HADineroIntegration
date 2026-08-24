"""Constants for the Dinero integration."""

from datetime import timedelta

DOMAIN = "dinero"
CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_API_KEY = "api_key"
CONF_ORGANIZATION_ID = "organization_id"

API_BASE_URL = "https://api.dinero.dk/v1"
TOKEN_URL = "https://authz.dinero.dk/dineroapi/oauth/token"
DEFAULT_SCAN_INTERVAL = timedelta(minutes=15)

