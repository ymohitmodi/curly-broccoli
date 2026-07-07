"""Google Trends (free) via pytrends — optional, degrades gracefully.

pip install 'darkfactory[trends]' to enable. Returns 0-1 momentum score per
keyword: >0.5 rising interest, <0.5 declining. Skills treat {} as "no data".
"""

from __future__ import annotations


def trend_scores(keywords: list[str]) -> dict[str, float]:
    try:
        from pytrends.request import TrendReq
    except ImportError:
        return {}
    scores: dict[str, float] = {}
    try:
        pt = TrendReq(hl="en-US", tz=360)
        for i in range(0, len(keywords), 5):  # pytrends max 5 per request
            batch = keywords[i:i + 5]
            pt.build_payload(batch, timeframe="today 12-m", geo="US")
            df = pt.interest_over_time()
            if df.empty:
                continue
            for kw in batch:
                if kw in df:
                    series = df[kw]
                    half = len(series) // 2
                    early, late = series[:half].mean(), series[half:].mean()
                    total = early + late
                    scores[kw] = round(float(late / total), 3) if total else 0.5
    except Exception:
        return scores  # rate limits etc. — partial data is fine
    return scores
