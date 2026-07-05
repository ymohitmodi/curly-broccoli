"""Amazon SP-API / Ads API adapter (the real, free, ToS-compliant data feed
for a registered seller).

STATUS: wired skeleton. Flip harness.yaml datasources to "spapi" after:
  1. Register a developer application in Seller Central
     (Apps & Services → Develop Apps) — free for your own selling account.
  2. Put LWA credentials + refresh token in .env (see .env.example).
  3. pip install 'darkfactory[spapi]'  (installs python-amazon-sp-api)

Useful SP-API surfaces for each feed:
  market   — Product Pricing API (competitive prices), Catalog Items API
             (listing metadata), Product Fees API (exact FBA fee estimates —
             feed these into economics.py instead of the weight ladder),
             Sales & Traffic report (your own velocity).
  ads      — Amazon Ads API: campaign performance + search-term reports.
             Search-term reports are the highest-value free keyword data
             you can get; they power both keyword_seo and ad_optimizer.
  reviews  — Amazon provides no bulk review API. Use your own product
             reviews via the Solicitations/Reports APIs; for competitor
             review THEMES, paste exports from tools you already own into
             workspace/inbox/reviews.json (review_miner picks them up).
"""

from __future__ import annotations

import os


class NotConfigured(RuntimeError):
    pass


def _require_env(*keys: str):
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        raise NotConfigured(
            f"SP-API not configured — missing env: {', '.join(missing)}. "
            "See .env.example and darkfactory/datasources/spapi.py header.")


def market_snapshot(categories: list[str]) -> list[dict]:
    _require_env("SPAPI_REFRESH_TOKEN", "SPAPI_LWA_CLIENT_ID", "SPAPI_LWA_CLIENT_SECRET")
    # TODO(you): implement with python-amazon-sp-api:
    #   from sp_api.api import Products, CatalogItems, ProductFees
    # Return list[dict] shaped like datasources/fixtures/market.json:
    #   {category, niche, search_volume_monthly, avg_price, top10_avg_reviews,
    #    top10_min_reviews, est_monthly_revenue_usd, trend_12m, notes}
    raise NotConfigured("market_snapshot: implement SP-API calls (see header docstring)")


def campaigns() -> list[dict]:
    _require_env("ADS_API_CLIENT_ID", "ADS_API_CLIENT_SECRET", "ADS_API_REFRESH_TOKEN")
    # TODO(you): Amazon Ads API — campaign + search-term reports, shaped like
    # datasources/fixtures/campaigns.json.
    raise NotConfigured("campaigns: implement Ads API calls (see header docstring)")


def reviews(niche: str) -> list[dict]:
    # No bulk competitor-review API exists. Drop exports into workspace/inbox/reviews.json
    # shaped like datasources/fixtures/reviews.json and review_miner will use them.
    import json
    from pathlib import Path
    inbox = Path("workspace/inbox/reviews.json")
    if inbox.exists():
        data = json.loads(inbox.read_text(encoding="utf-8"))
        return [r for r in data if niche.lower() in r.get("niche", "").lower()] or data
    raise NotConfigured("reviews: place exports at workspace/inbox/reviews.json")
