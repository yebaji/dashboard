"""
fetch_and_process.py
--------------------
Fetches the latest NSE CM bhavcopy, processes it, and writes data.json
for the dashboard to consume.

Run manually:   python fetch_and_process.py
Run by CI:      same command, triggered by GitHub Actions on a schedule
"""

import io
import json
import zipfile
from datetime import date, timedelta

import pandas as pd
import requests

# ── NSE URL helpers ────────────────────────────────────────────────────────────

NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


def bhavcopy_url(d: date) -> str:
    """Return the CM-UDiFF bhavcopy zip URL for a given date (post Jul 2024)."""
    return (
        f"https://nsearchives.nseindia.com/content/cm/"
        f"BhavCopy_NSE_CM_0_0_0_{d.strftime('%Y%m%d')}_F.CSV.zip"
    )


def fetch_latest_bhavcopy() -> tuple[pd.DataFrame, date]:
    """
    Walk backwards from today until we find a trading day with data.
    Returns (DataFrame, trade_date).
    Raises RuntimeError if no data found in the last 10 calendar days.
    """
    session = requests.Session()
    # Warm up session cookie — NSE requires this
    session.get("https://www.nseindia.com", headers=NSE_HEADERS, timeout=10)

    for days_back in range(1, 11):
        trade_date = date.today() - timedelta(days=days_back)
        url = bhavcopy_url(trade_date)
        print(f"Trying {url} ...")
        try:
            resp = session.get(url, headers=NSE_HEADERS, timeout=30)
            if resp.status_code == 200:
                with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
                    csv_name = z.namelist()[0]
                    with z.open(csv_name) as f:
                        df = pd.read_csv(f)
                print(f"✓ Fetched bhavcopy for {trade_date} ({len(df)} rows)")
                return df, trade_date
            else:
                print(f"  HTTP {resp.status_code} — skipping")
        except Exception as e:
            print(f"  Error: {e} — skipping")

    raise RuntimeError("Could not fetch bhavcopy for the last 10 days.")


# ── Processing ─────────────────────────────────────────────────────────────────

def process(df: pd.DataFrame) -> dict:
    num_cols = [
        "PREV_CL_PR", "OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE",
        "CLOSE_PRICE", "NET_TRDVAL", "NET_TRDQTY", "TRADES",
        "HI_52_WK", "LO_52_WK",
    ]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    active = df[df["TRADES"] > 0].copy()
    active["CHANGE"]     = active["CLOSE_PRICE"] - active["PREV_CL_PR"]
    active["CHANGE_PCT"] = (active["CHANGE"] / active["PREV_CL_PR"]) * 100

    gainers   = int((active["CHANGE_PCT"] > 0).sum())
    losers    = int((active["CHANGE_PCT"] < 0).sum())
    unchanged = int((active["CHANGE_PCT"] == 0).sum())

    # Nifty 50
    nifty_row = df[df["SECURITY"] == "Nifty 50"]
    nifty = {}
    if not nifty_row.empty:
        r = nifty_row.iloc[0]
        nifty = {
            "close":    round(float(r["CLOSE_PRICE"]), 2),
            "prev":     round(float(r["PREV_CL_PR"]),  2),
            "change":   round(float(r["CLOSE_PRICE"]) - float(r["PREV_CL_PR"]), 2),
            "changePct":round((float(r["CLOSE_PRICE"]) - float(r["PREV_CL_PR"])) / float(r["PREV_CL_PR"]) * 100, 2),
        }

    # 52-week proximity
    near_high = active[
        (active["CLOSE_PRICE"] > 0) & (active["HI_52_WK"] > 0) &
        (active["CLOSE_PRICE"] >= active["HI_52_WK"] * 0.97)
    ]
    near_low = active[
        (active["CLOSE_PRICE"] > 0) & (active["LO_52_WK"] > 0) &
        (active["CLOSE_PRICE"] <= active["LO_52_WK"] * 1.03)
    ]

    # Distribution
    bins   = [-100, -10, -5, -2, 0, 2, 5, 10, 100]
    labels = ["<-10%", "-10 to -5%", "-5 to -2%", "-2 to 0%",
              "0 to 2%", "2 to 5%", "5 to 10%", ">10%"]
    active["bucket"] = pd.cut(active["CHANGE_PCT"], bins=bins, labels=labels)
    dist = active["bucket"].value_counts().sort_index()

    # Top gainers / losers
    def rows(frame, col):
        return [
            {
                "security":   str(r["SECURITY"]),
                "prevClose":  round(float(r["PREV_CL_PR"]),  2),
                "close":      round(float(r["CLOSE_PRICE"]), 2),
                "changePct":  round(float(r["CHANGE_PCT"]),  2),
                "tradeValue": round(float(r["NET_TRDVAL"]),  0),
            }
            for _, r in frame.nlargest(10, col).iterrows()
            if pd.notna(r["CLOSE_PRICE"])
        ]

    # Most traded (equity only)
    equity = active[active["MKT"] == "N"]
    most_traded = [
        {
            "security":   str(r["SECURITY"]),
            "close":      round(float(r["CLOSE_PRICE"]), 2),
            "changePct":  round(float(r["CHANGE_PCT"]),  2),
            "tradeValue": round(float(r["NET_TRDVAL"]),  0),
            "trades":     int(r["TRADES"]),
        }
        for _, r in equity.nlargest(15, "NET_TRDVAL").iterrows()
    ]

    return {
        "nifty":      nifty,
        "totalRows":  len(df),
        "activeRows": len(active),
        "gainers":    gainers,
        "losers":     losers,
        "unchanged":  unchanged,
        "nearHigh":   len(near_high),
        "nearLow":    len(near_low),
        "distribution": {
            "labels": labels,
            "values": [int(dist.get(l, 0)) for l in labels],
        },
        "topGainers":  rows(active, "CHANGE_PCT"),
        "topLosers":   [
            {
                "security":   str(r["SECURITY"]),
                "prevClose":  round(float(r["PREV_CL_PR"]),  2),
                "close":      round(float(r["CLOSE_PRICE"]), 2),
                "changePct":  round(float(r["CHANGE_PCT"]),  2),
                "tradeValue": round(float(r["NET_TRDVAL"]),  0),
            }
            for _, r in active.nsmallest(10, "CHANGE_PCT").iterrows()
        ],
        "mostTraded":  most_traded,
    }


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    df, trade_date = fetch_latest_bhavcopy()
    data = process(df)
    data["date"] = trade_date.strftime("%d %b %Y")

    with open("data.json", "w") as f:
        json.dump(data, f, indent=2)

    print(f"✓ data.json written — {trade_date}")
