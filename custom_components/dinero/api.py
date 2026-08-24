"""Async client for Dinero's personal integration API."""

from __future__ import annotations

import calendar
from base64 import b64encode
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from aiohttp import ClientError
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
            await _raise_for_status(response, authentication_request=True)
            payload = await response.json()
        except DineroApiError:
            raise
        except ClientError as err:
            raise DineroApiError(f"Network error while contacting Dinero: {err}") from err

        self._access_token = payload["access_token"]
        # Keep a safety margin so an update never starts with an expiring token.
        self._token_expires_at = now + timedelta(
            seconds=max(0, int(payload.get("expires_in", 3600)) - 60)
        )
        return self._access_token

    async def async_year_to_date_revenue(self) -> dict[str, Any]:
        """Return current year/month P&L values and inventory balance."""
        now = dt_util.now()
        start_date = now.date().replace(month=1, day=1).isoformat()
        month_start = now.date().replace(day=1).isoformat()
        end_date = now.date().isoformat()
        ltm_start = _ltm_start(now.date()).isoformat()
        entries = await self._async_entries(start_date, end_date, include_primo=False)
        # Dinero's entries endpoint only accepts dates from one accounting year.
        # Reuse this year's entries and fetch the prior-year part separately.
        prior_year_end = now.date().replace(
            year=now.year - 1, month=12, day=31
        ).isoformat()
        prior_year_ltm_entries = await self._async_entries(
            ltm_start, prior_year_end, include_primo=False
        )
        ltm_entries = prior_year_ltm_entries + entries
        balance_entries = await self._async_entries(start_date, end_date, include_primo=True)

        ytd_revenue, ytd_expenses, ytd_revenue_entries = _profit_and_loss(entries)
        month_entries = [
            entry for entry in entries
            if str(_get_value(entry, "date", ""))[:10] >= month_start
        ]
        month_revenue, month_expenses, month_revenue_entries = _profit_and_loss(month_entries)
        ltm_revenue, ltm_expenses, ltm_revenue_entries = _profit_and_loss(ltm_entries)
        inventory_value = sum(
            (
                Decimal(str(_get_value(entry, "amount", 0)))
                for entry in balance_entries
                if int(_get_value(entry, "accountNumber", 0)) == 52000
            ),
            Decimal("0"),
        )

        return {
            "year_to_date_revenue": float(ytd_revenue),
            "year_to_date_expenses": float(ytd_expenses),
            "year_to_date_result": float(ytd_revenue - ytd_expenses),
            "current_month_revenue": float(month_revenue),
            "current_month_expenses": float(month_expenses),
            "current_month_result": float(month_revenue - month_expenses),
            "ltm_revenue": float(ltm_revenue),
            "ltm_expenses": float(ltm_expenses),
            "ltm_result": float(ltm_revenue - ltm_expenses),
            "inventory_value": float(inventory_value),
            "entry_count": len(entries),
            "revenue_entry_count": ytd_revenue_entries,
            "month_revenue_entry_count": month_revenue_entries,
            "ltm_revenue_entry_count": ltm_revenue_entries,
            "currency": "DKK",
            "start_date": start_date,
            "month_start": month_start,
            "ltm_start": ltm_start,
            "end_date": end_date,
            "year": now.year,
        }

    async def _async_entries(
        self, from_date: str, to_date: str, *, include_primo: bool
    ) -> list[dict[str, Any]]:
        """Fetch general-ledger entries for a period."""
        token = await self._async_access_token()
        try:
            response = await self._session.get(
                f"{API_BASE_URL}/{self.organization_id}/entries",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "fromDate": from_date,
                    "toDate": to_date,
                    "includePrimo": str(include_primo).lower(),
                },
            )
            await _raise_for_status(response)
            payload = await response.json()
        except DineroApiError:
            raise
        except ClientError as err:
            raise DineroApiError(f"Network error while contacting Dinero: {err}") from err

        return _extract_entries(payload)


async def _raise_for_status(response: Any, *, authentication_request: bool = False) -> None:
    """Raise a useful error containing Dinero's HTTP status and response."""
    if response.status < 400:
        return

    response_text = (await response.text()).strip().replace("\n", " ")
    detail = response_text[:500] or response.reason or "No response details"
    message = f"Dinero HTTP {response.status}: {detail}"
    if response.status in (401, 403) or (
        authentication_request and response.status == 400
    ):
        raise DineroAuthenticationError(message)
    raise DineroApiError(message)


def _get_value(item: dict[str, Any], key: str, default: Any = None) -> Any:
    """Read a Dinero field regardless of JSON property capitalization."""
    wanted = key.casefold()
    return next(
        (value for name, value in item.items() if name.casefold() == wanted),
        default,
    )


def _extract_entries(payload: Any) -> list[dict[str, Any]]:
    """Extract and validate Dinero's general-ledger entry list."""
    if isinstance(payload, list):
        collection = payload
    elif isinstance(payload, dict):
        collection = _get_value(payload, "collection")
    else:
        collection = None

    if not isinstance(collection, list) or not all(
        isinstance(item, dict) for item in collection
    ):
        raise DineroApiError("Dinero returned an unexpected entries response")
    return collection


def _profit_and_loss(entries: list[dict[str, Any]]) -> tuple[Decimal, Decimal, int]:
    """Calculate revenue and net expenses from Dinero P&L accounts."""
    revenue = Decimal("0")
    expenses = Decimal("0")
    revenue_entry_count = 0
    for entry in entries:
        account_number = int(_get_value(entry, "accountNumber", 0))
        amount = Decimal(str(_get_value(entry, "amount", 0)))
        if 1000 <= account_number <= 1999:
            revenue -= amount
            revenue_entry_count += 1
        elif 2000 <= account_number <= 9999:
            expenses += amount
    return revenue, expenses, revenue_entry_count


def _ltm_start(today: date) -> date:
    """Return the first date in the trailing twelve-month period."""
    prior_year_day = min(
        today.day, calendar.monthrange(today.year - 1, today.month)[1]
    )
    return today.replace(year=today.year - 1, day=prior_year_day) + timedelta(days=1)

