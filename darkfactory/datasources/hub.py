"""DataHub — one router for every external data feed.

Each feed (market, ads, reviews, trends) is independently switchable in
harness.yaml between providers. "sample" ships in the repo so the factory
runs end-to-end offline on day one; "spapi" activates once .env has real
Amazon credentials. Add providers (Keepa, Helium10 export CSVs, …) by
dropping a module here with the same method signatures.

Compliance note: do NOT scrape amazon.com — it violates the ToS you signed
as a seller and risks your account. SP-API and the Ads API are the free,
legitimate feeds for a registered seller; use those.
"""

from __future__ import annotations

from . import sample, spapi, trends


class DataHub:
    def __init__(self, cfg):
        self.cfg = cfg
        ds = cfg.harness.get("datasources", {})
        self.market_provider = ds.get("market", "sample")
        self.ads_provider = ds.get("ads", "sample")
        self.reviews_provider = ds.get("reviews", "sample")
        self.trends_provider = ds.get("trends", "auto")

    def market_snapshot(self, categories: list[str]) -> list[dict]:
        """Niche-level metrics: search volume, price band, top-10 review counts, revenue."""
        if self.market_provider == "spapi":
            return spapi.market_snapshot(categories)
        return sample.market_snapshot(categories)

    def campaigns(self) -> list[dict]:
        """PPC campaign performance: spend, sales, ACOS, search-term report rows."""
        if self.ads_provider == "spapi":
            return spapi.campaigns()
        return sample.campaigns()

    def reviews(self, niche: str) -> list[dict]:
        """Competitor/own product reviews for the given niche."""
        if self.reviews_provider == "spapi":
            return spapi.reviews(niche)
        return sample.reviews(niche)

    def trend_scores(self, keywords: list[str]) -> dict[str, float]:
        """0-1 interest trend per keyword (Google Trends, free). {} if unavailable."""
        if self.trends_provider in ("auto", "pytrends"):
            return trends.trend_scores(keywords)
        return {}
