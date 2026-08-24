"""Async client for Dinero's personal integration API."""

from __future__ import annotations

from base64 import b64encode
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from aiohttp import ClientResponseError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .const import API_BASE_URL, TOKEN_URL


class DineroApiError(Exception):
    """Base Dinero API error."""


class DineroAuthenticationError(DineroApiError):
    """Dinero rejected the supplied credentials."""


class DineroApiClient:
    """Small client containing only the calls needed by this integration."""

    def __init__(self, hass: HomeAssistant, *, client_id: str, client_secret: str,
                 api_key: str, organization_id: str) -> None:
        self._session = async_get_clientsession(hass)
        self._client_id = client_id
        self._client_secret = client_secret
        self._api_key = api_key
        self.organization_id = organization_id
        self._access_token: str | None = None
        self._token_expires_at: datetime | None = None

    async def async_validate(self) -> None:
        """Validate credentials without downloading invoice history."""
        await self._async_access_token()

    async def _async_access_token(self) -> str:
        now = dt_util.utcnow()
        if self._access_token and self._token_expires_at and now < self._token_expires_at:
            return self._access_token

        basic = b64encode(
            f"{self._client_id}:{self._client_secret}".encode()
        ).decode()
        try:
            response = await self._session.post(
                TOKEN_URL,
                headers={"Authorization": f"Basic {basic}"},
                data={
                    "grant_type": "password",
                    "scope": "read write",
                    "username": self._api_key,
                    "password": self._api_key,
                },
            )
            response.raise_for_status()
            payload = await response.json()
        except ClientResponseError as err:
            if err.status in (400, 401, 403):
                raise DineroAuthenticationError from err
            raise DineroApiError from err

        self._access_token = payload["access_token"]
        # Keep a safety margin so an update never starts with an expiring token.
        self._token_expires_at = now + timedelta(
            seconds=max(0, int(payload.get("expires_in", 3600)) - 60)
        )
        return self._access_token

    async def async_year_to_date_revenue(self) -> dict[str, Any]:
        """Return booked invoice revenue for the current calendar year, excl. VAT."""
        now = dt_util.now()
        start_date = now.date().replace(month=1, day=1).isoformat()
        end_date = now.date().isoformat()
        page = 0
        page_size = 1000
        total = Decimal("0")
        invoice_count = 0

        while True:
            token = await self._async_access_token()
            try:
                response = await self._session.get(
                    f"{API_BASE_URL}/{self.organization_id}/invoices",
                    headers={"Authorization": f"Bearer {token}"},
                    params={
                        "startDate": start_date,
                        "endDate": end_date,
                        "page": page,
                        "pageSize": page_size,
                        "fields": [
                            "Guid",
                            "Date",
                            "Status",
                            "Currency",
                            "TotalExclVat",
                            "TotalExclVatInDkk",
                        ],
                    },
                )
                response.raise_for_status()
                payload = await response.json()
            except ClientResponseError as err:
                if err.status in (401, 403):
                    raise DineroAuthenticationError from err
                raise DineroApiError from err

            invoices = payload.get("collection", payload) if isinstance(payload, dict) else payload
            for invoice in invoices:
                if invoice.get("status", "").casefold() == "draft":
                    continue
                amount = invoice.get("totalExclVatInDkk")
                if amount is None and invoice.get("currency", "DKK") == "DKK":
                    amount = invoice.get("totalExclVat", 0)
                if amount is not None:
                    total += Decimal(str(amount))
                    invoice_count += 1

            if len(invoices) < page_size:
                break
            page += 1

        return {
            "year_to_date_revenue": float(total),
            "invoice_count": invoice_count,
            "currency": "DKK",
            "start_date": start_date,
            "end_date": end_date,
            "year": now.year,
        }

