"""Constants for the Dinero integration."""

from datetime import timedelta

DOMAIN = "dinero"
CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_API_KEY = "api_key"
CONF_ORGANIZATION_ID = "organization_id"
CONF_INVENTORY_ACCOUNT = "inventory_account"
CONF_INVENTORY_ADJUSTMENT_ACCOUNT = "inventory_adjustment_account"
CONF_INVENTORY_SOURCE_ENTITY = "inventory_source_entity"

DEFAULT_INVENTORY_ACCOUNT = 52000
DEFAULT_INVENTORY_ADJUSTMENT_ACCOUNT = 2450

API_BASE_URL = "https://api.dinero.dk/v1"
TOKEN_URL = "https://authz.dinero.dk/dineroapi/oauth/token"
DEFAULT_SCAN_INTERVAL = timedelta(minutes=15)

