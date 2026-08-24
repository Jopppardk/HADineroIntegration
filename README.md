# Dinero for Home Assistant

Unofficial HACS integration that connects Home Assistant to Dinero. The first
release follows the structure and dashboard-oriented purpose of the Shopify Home
Assistant integration and exposes one monetary sensor:

- **Omsætning år til dato** — net revenue posted from 1 January through today on
  Dinero's revenue accounts 1000–1999. This includes invoices, manual vouchers,
  webshop/POS imports, credit notes and reversals, excluding VAT.

The integration refreshes every 15 minutes and automatically renews Dinero's
one-hour access token.

## Requirements

- Home Assistant 2024.12 or newer
- A Dinero Pro or Total subscription
- A Dinero personal integration: Client ID, Client Secret and API key
- Your Dinero organization ID

Create the credentials under **Integrationer → Se og opret API-nøgler → Personlig
Integration** in Dinero. Credentials are stored in Home Assistant's config entry
and are never exposed as sensor attributes.

## Installation with HACS

1. In HACS, open **Custom repositories**.
2. Add `https://github.com/Jopppardk/HADineroIntegration` as **Integration**.
3. Install **Dinero** and restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration → Dinero**.
5. Enter your organization ID and personal integration credentials.

## Manual installation

Copy `custom_components/dinero` to Home Assistant's `custom_components` folder,
restart Home Assistant, and add Dinero from **Devices & services**.

## Sensor

`sensor.<name>_omsaetning_ar_til_dato` uses DKK, device class `monetary`, and
state class `total`. Attributes include the period, year, invoice count, dates,
and the `excluding_vat` amount basis.

## Disclaimer

This is an unofficial integration and is not affiliated with or endorsed by
Dinero or Visma.

