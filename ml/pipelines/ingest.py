"""
Load and normalise the raw CSVs in ml/data/raw/.

This module is the ONLY place that knows about the messiness of the source
files. Everything downstream receives clean, consistently-typed DataFrames.

THE MESS IT CLEANS UP
---------------------
* Photographer IDs appear as "P001" in three files and as bare integers in two.
* service_monitoring.csv is missing the Portfolio_Interactions column that its
  four sibling files have.
* Prices are USD-scale (109-1992) while the platform trades in PKR.
* reviews_feedback.csv Sentiment labels are randomly assigned and MUST NOT be
  used as training labels (see `load_reviews_feedback` for the evidence).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

PKR_MULTIPLIER = 100

CANONICAL_CATEGORIES = ["Wedding", "Corporate", "Fashion", "Birthday", "Graduation"]

MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11,
    "December": 12,
}


def _read(name: str) -> pd.DataFrame:
    path = RAW_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Missing dataset: {path}")
    return pd.read_csv(path)


def normalise_photographer_id(series: pd.Series) -> pd.Series:
    """"P001" and "1" both become the integer 1."""
    return (
        series.astype(str)
        .str.replace(r"^P0*", "", regex=True)
        .str.strip()
        .replace("", np.nan)
        .astype(float)
        .astype("Int64")
    )


# ═══════════════════════════════════════════════════════════════════════════
# CORE TABLES
# ═══════════════════════════════════════════════════════════════════════════
def load_photographers() -> pd.DataFrame:
    """200 photographers with the eight raw ranking features."""
    df = _read("photographer_profiles.csv")
    df = df.rename(
        columns={
            "Photographer_ID": "photographer_id",
            "Event_Type": "category",
            "Years_Experience": "years_experience",
            "Avg_Rating": "avg_rating",
            "Reviews_Count": "reviews_count",
            "Bookings_Success_Rate": "success_rate",
            "Response_Time": "response_time_hours",
            "Portfolio_Score": "portfolio_score",
            "Price": "price_usd",
        }
    )
    df["photographer_id"] = normalise_photographer_id(df["photographer_id"])
    df["price_pkr"] = (df["price_usd"] * PKR_MULTIPLIER).round(-2)
    df = df[df["category"].isin(CANONICAL_CATEGORIES)]
    return df.reset_index(drop=True)


def load_interactions() -> pd.DataFrame:
    """500 buyer↔photographer sessions — the collaborative-filtering source."""
    df = _read("buyer_interactions.csv")
    df = df.rename(
        columns={
            "Interaction_ID": "interaction_id",
            "Buyer_ID": "buyer_id",
            "Photographer_ID": "photographer_id",
            "Search_Keyword": "category",
            "Profile_View": "profile_view",
            "Clicks": "clicks",
            "Portfolio_Interactions": "portfolio_interactions",
            "Inquiry_Made": "inquiry_made",
            "Booking_Status": "booking_status",
            "Timestamp": "timestamp",
        }
    )
    df["photographer_id"] = normalise_photographer_id(df["photographer_id"])
    df["buyer_id"] = df["buyer_id"].astype(int)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["profile_view"] = df["profile_view"].eq("Yes")
    df["inquiry_made"] = df["inquiry_made"].eq("Yes")
    return df.reset_index(drop=True)


def load_seasonal_demand() -> pd.DataFrame:
    df = _read("seasonal_demand.csv")
    df = df.rename(
        columns={
            "Month": "month_name",
            "Event_Type": "category",
            "Avg_Bookings": "avg_bookings",
            "Avg_Price": "avg_price_usd",
            "Demand_Score": "demand_score",
        }
    )
    df["month"] = df["month_name"].map(MONTHS)
    df["avg_price_pkr"] = (df["avg_price_usd"] * PKR_MULTIPLIER).round(-2)
    return df.reset_index(drop=True)


def load_service_metrics() -> pd.DataFrame:
    """
    Merge the five service_*.csv files into one daily-funnel table.

    They share a schema apart from service_monitoring.csv, which lacks
    Portfolio_Interactions — filled with 0 rather than dropped, because the
    other nine columns in those 400 rows are still useful.
    """
    files = [
        "service_engagement_dataset.csv",
        "service_revenue_dataset.csv",
        "service_general_dataset.csv",
        "service_monitoring_dataset.csv",
        "service_monitoring.csv",
    ]
    frames = []
    for name in files:
        try:
            df = _read(name)
        except FileNotFoundError:
            continue
        if "Portfolio_Interactions" not in df.columns:
            df["Portfolio_Interactions"] = 0
        df["source_file"] = name
        frames.append(df)

    merged = pd.concat(frames, ignore_index=True)
    merged = merged.rename(
        columns={
            "Photographer_ID": "photographer_id",
            "Date": "date",
            "Event_Type": "category",
            "Search_Visibility": "search_visibility",
            "Profile_Views": "profile_views",
            "Clicks": "clicks",
            "Portfolio_Interactions": "portfolio_interactions",
            "Bookings": "bookings",
            "Conversion_Rate": "conversion_rate",
            "Response_Rate": "response_rate",
            "Revenue": "revenue_usd",
        }
    )
    merged["photographer_id"] = normalise_photographer_id(merged["photographer_id"])
    merged["date"] = pd.to_datetime(merged["date"], errors="coerce")
    merged["revenue_pkr"] = merged["revenue_usd"] * PKR_MULTIPLIER
    merged = merged.dropna(subset=["photographer_id", "date"])
    return merged.reset_index(drop=True)


def load_product_interactions() -> pd.DataFrame:
    """
    data.csv — 1,000 implicit-feedback rows for the marketplace recommender.

    Columns are already clean; the useful work here is deriving an engagement
    score that combines the weak signals (clicks, dwell time, scroll depth)
    with the strong ones (add-to-cart, purchase).
    """
    df = _read("data.csv")
    df["engagement"] = (
        df["click_count"] * 0.5
        + np.log1p(df["view_time_sec"]) * 1.5
        + df["scroll_depth"] * 0.3
        + df["add_to_cart"] * 5.0
        + df["purchase"] * 10.0
    )
    return df


# ═══════════════════════════════════════════════════════════════════════════
# REVIEWS
# ═══════════════════════════════════════════════════════════════════════════
def load_reviews_feedback() -> pd.DataFrame:
    """
    reviews_feedback.csv — loaded for inspection only.

    DO NOT TRAIN ON THE `Sentiment` COLUMN. Run
    `python -m ml.pipelines.ingest --audit` to see why: the file contains 5
    distinct review sentences across 300 rows, and the labels do not agree
    with the text (e.g. "Amazing service and very professional." is labelled
    Negative). A classifier trained on it learns nothing above chance.

    The sentiment model is trained on yelp.csv instead.
    """
    df = _read("reviews_feedback.csv")
    return df.rename(
        columns={
            "Review_ID": "review_id",
            "Photographer_ID": "photographer_id",
            "Buyer_ID": "buyer_id",
            "Review_Text": "text",
            "Sentiment": "label_UNRELIABLE",
        }
    )


def load_yelp_reviews(limit: int | None = None) -> pd.DataFrame:
    """
    yelp.csv — 44,610 real reviews with trustworthy star ratings.

    Star ratings map to sentiment with a deliberate gap at 3 stars:
        1-2 → NEGATIVE      3 → NEUTRAL      4-5 → POSITIVE
    """
    df = pd.read_csv(RAW_DIR / "yelp.csv", nrows=limit)
    df = df[["stars", "text"]].dropna()
    df["stars"] = pd.to_numeric(df["stars"], errors="coerce")
    df = df.dropna(subset=["stars"])
    df["stars"] = df["stars"].astype(int)

    df["sentiment"] = pd.cut(
        df["stars"], bins=[0, 2, 3, 5], labels=["NEGATIVE", "NEUTRAL", "POSITIVE"]
    )
    df["text"] = df["text"].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    df = df[df["text"].str.len().between(20, 2000)]
    return df.reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════════
# AUDIT
# ═══════════════════════════════════════════════════════════════════════════
def audit() -> None:
    """Print the data-quality findings that shaped every decision downstream."""
    print("=" * 74)
    print("DATA QUALITY AUDIT — ml/data/raw")
    print("=" * 74)

    p = load_photographers()
    print(f"\nphotographer_profiles.csv          {len(p):>6} rows")
    print(f"  categories                       {sorted(p['category'].unique())}")
    print(f"  avg_rating         min/max/mean  {p.avg_rating.min():.2f} / "
          f"{p.avg_rating.max():.2f} / {p.avg_rating.mean():.2f}")
    print(f"  response_time_hrs  min/max/mean  {p.response_time_hours.min():.0f} / "
          f"{p.response_time_hours.max():.0f} / {p.response_time_hours.mean():.1f}"
          "   ← LOW IS GOOD, must be inverted")
    print(f"  portfolio_score    min/max       {p.portfolio_score.min()} / "
          f"{p.portfolio_score.max()}          ← 100× the rating scale, needs scaling")
    print(f"  price_usd          min/max       {p.price_usd.min()} / {p.price_usd.max()}")
    print(f"  price_pkr          min/max       {p.price_pkr.min():,.0f} / "
          f"{p.price_pkr.max():,.0f}")

    i = load_interactions()
    print(f"\nbuyer_interactions.csv             {len(i):>6} rows")
    print(f"  unique buyers / photographers    {i.buyer_id.nunique()} / "
          f"{i.photographer_id.nunique()}")
    print(f"  matrix density                   "
          f"{len(i) / (i.buyer_id.nunique() * i.photographer_id.nunique()) * 100:.2f}%"
          "   ← very sparse, CF needs care")
    print(f"  booking_status                   {i.booking_status.value_counts().to_dict()}")

    r = load_reviews_feedback()
    print(f"\nreviews_feedback.csv               {len(r):>6} rows")
    print(f"  DISTINCT review texts            {r.text.nunique()}"
          "        ← only 5 sentences in 300 rows")
    print("  label agreement check:")
    for text, group in r.groupby("text"):
        labels = group["label_UNRELIABLE"].value_counts().to_dict()
        verdict = "INCONSISTENT" if len(labels) > 1 else "ok"
        print(f'    {verdict:<13} "{text[:44]:<44}" → {labels}')
    print("\n  VERDICT: labels are noise. Training on them is impossible.")
    print("           Sentiment model uses yelp.csv instead.")

    y = load_yelp_reviews(limit=20000)
    print(f"\nyelp.csv (first 20k)               {len(y):>6} usable rows")
    print(f"  sentiment distribution           {y.sentiment.value_counts().to_dict()}")
    print(f"  mean review length               {y.text.str.len().mean():.0f} chars")

    s = load_service_metrics()
    print(f"\nservice_*.csv (5 files merged)     {len(s):>6} rows")
    print(f"  photographers covered            {s.photographer_id.nunique()}")
    print(f"  date range                       {s.date.min():%Y-%m-%d} → {s.date.max():%Y-%m-%d}")

    d = load_seasonal_demand()
    print(f"\nseasonal_demand.csv                {len(d):>6} rows  "
          f"({d.month.nunique()} months × {d.category.nunique()} categories)")

    prod = load_product_interactions()
    print(f"\ndata.csv                           {len(prod):>6} rows")
    print(f"  users / items                    {prod.user_id.nunique()} / "
          f"{prod.item_id.nunique()}")
    print(f"  purchase rate                    {prod.purchase.mean() * 100:.1f}%")
    print("\n" + "=" * 74)


if __name__ == "__main__":
    import sys

    if "--audit" in sys.argv:
        audit()
    else:
        print("Usage: python -m ml.pipelines.ingest --audit")
