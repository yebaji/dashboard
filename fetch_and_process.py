"""
fetch_and_process.py
--------------------
Fetches the latest NSE CM bhavcopy, processes it with in-depth analysis,
and writes data.json for the dashboard (index.html) to consume.

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

COLUMN_ALIASES = {
    # New camelCase format (2025/26+)
    "PrvsClsgPric":    "PREV_CL_PR",
    "OpnPric":         "OPEN_PRICE",
    "HghPric":         "HIGH_PRICE",
    "LwPric":          "LOW_PRICE",
    "ClsPric":         "CLOSE_PRICE",
    "LastPric":        "LAST_PRICE",
    "TtlTrfVal":       "NET_TRDVAL",
    "TtlTradgVol":     "NET_TRDQTY",
    "TtlNbOfTxsExctd": "TRADES",
    "TckrSymb":        "SECURITY",
    "SctySrs":         "MKT",
    # Old ALL_CAPS format (pre-2025)
    "PREVCLOSE":       "PREV_CL_PR",
    "PREV_CLOSE":      "PREV_CL_PR",
    "PREVCLOSE_PR":    "PREV_CL_PR",
    "OPEN":            "OPEN_PRICE",
    "OPENPRICE":       "OPEN_PRICE",
    "HIGH":            "HIGH_PRICE",
    "HIGHPRICE":       "HIGH_PRICE",
    "LOW":             "LOW_PRICE",
    "LOWPRICE":        "LOW_PRICE",
    "CLOSE":           "CLOSE_PRICE",
    "CLOSEPRICE":      "CLOSE_PRICE",
    "LAST":            "CLOSE_PRICE",
    "LAST_PRICE":      "CLOSE_PRICE",
    "TOTTRDVAL":       "NET_TRDVAL",
    "TOTALTRDVAL":     "NET_TRDVAL",
    "TOTTRDQTY":       "NET_TRDQTY",
    "TOTALTRDQTY":     "NET_TRDQTY",
    "52WH":            "HI_52_WK",
    "52WL":            "LO_52_WK",
    "HIGH52":          "HI_52_WK",
    "LOW52":           "LO_52_WK",
    "SYMBOL":          "SECURITY",
    "SCRIP_NM":        "SECURITY",
    "SERIES":          "MKT",
    "TOTALTRADES":     "TRADES",
    "TOTTRADES":       "TRADES",
    "NO_OF_TRADES":    "TRADES",
}


def normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = df.columns.str.strip()
    rename_map = {}
    for col in df.columns:
        if col in COLUMN_ALIASES:
            canonical = COLUMN_ALIASES[col]
            if canonical not in df.columns and canonical not in rename_map.values():
                rename_map[col] = canonical
    if rename_map:
        print(f"  Column rename: {rename_map}")
    df = df.rename(columns=rename_map)
    if "CLOSE_PRICE" not in df.columns and "LAST_PRICE" in df.columns:
        df = df.rename(columns={"LAST_PRICE": "CLOSE_PRICE"})
        print("  Used LAST_PRICE as CLOSE_PRICE fallback")
    return df


def bhavcopy_urls(d: date) -> list:
    ds = d.strftime("%Y%m%d")
    base = "https://nsearchives.nseindia.com/content/cm/"
    return [
        f"{base}BhavCopy_NSE_CM_0_0_0_{ds}_F_0000.csv.zip",
        f"{base}BhavCopy_NSE_CM_0_0_0_{ds}_F.CSV.zip",
    ]


def fetch_latest_bhavcopy() -> tuple[pd.DataFrame, date]:
    session = requests.Session()
    session.get("https://www.nseindia.com/all-reports", headers=NSE_HEADERS, timeout=10)

    for days_back in range(1, 11):
        trade_date = date.today() - timedelta(days=days_back)
        for url in bhavcopy_urls(trade_date):
            print(f"Trying {url} ...")
            try:
                resp = session.get(url, headers=NSE_HEADERS, timeout=30)
                if resp.status_code == 200:
                    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
                        csv_name = z.namelist()[0]
                        with z.open(csv_name) as f:
                            df = pd.read_csv(f)
                    df = normalise_columns(df)
                    print(f"✓ Fetched bhavcopy for {trade_date} ({len(df)} rows)")
                    print(f"  Columns after normalisation: {list(df.columns)}")
                    return df, trade_date
                else:
                    print(f"  HTTP {resp.status_code} — skipping")
            except Exception as e:
                print(f"  Error: {e} — skipping")

    raise RuntimeError("Could not fetch bhavcopy for the last 10 days.")


# ── Processing ─────────────────────────────────────────────────────────────────

def safe_float(val):
    try:
        return round(float(val), 2)
    except (TypeError, ValueError):
        return None


def process(df: pd.DataFrame) -> dict:
    num_cols = [
        "PREV_CL_PR", "OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE",
        "CLOSE_PRICE", "NET_TRDVAL", "NET_TRDQTY", "TRADES",
        "HI_52_WK", "LO_52_WK",
    ]
    missing = [c for c in num_cols if c not in df.columns]
    if missing:
        print(f"  WARNING: columns still missing after normalisation: {missing}")
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # Active rows
    if "TRADES" in df.columns:
        active = df[df["TRADES"] > 0].copy()
    else:
        print("  WARNING: TRADES column missing; using all rows as active")
        active = df.copy()

    active["CHANGE"]      = active["CLOSE_PRICE"] - active["PREV_CL_PR"]
    active["CHANGE_PCT"]  = (active["CHANGE"] / active["PREV_CL_PR"]) * 100

    # Intraday range % as volatility proxy
    if "HIGH_PRICE" in active.columns and "LOW_PRICE" in active.columns:
        active["HL_RANGE_PCT"] = (
            (active["HIGH_PRICE"] - active["LOW_PRICE"]) / active["CLOSE_PRICE"] * 100
        )

    # ── Nifty 50 ──────────────────────────────────────────────────────────────
    nifty = {}
    if "SECURITY" in df.columns:
        nifty_row = df[df["SECURITY"] == "Nifty 50"]
        if not nifty_row.empty:
            r = nifty_row.iloc[0]
            c, p = float(r["CLOSE_PRICE"]), float(r["PREV_CL_PR"])
            nifty = {
                "close":     round(c, 2),
                "prev":      round(p, 2),
                "change":    round(c - p, 2),
                "changePct": round((c - p) / p * 100, 2),
            }

    # ── Summary breadth stats ─────────────────────────────────────────────────
    gainers   = int((active["CHANGE_PCT"] > 0).sum())
    losers    = int((active["CHANGE_PCT"] < 0).sum())
    unchanged = int((active["CHANGE_PCT"] == 0).sum())
    total_active = gainers + losers + unchanged

    ad_ratio     = round(gainers / losers, 2) if losers else None
    breadth_pct  = round(gainers / total_active * 100, 1) if total_active else None
    total_value  = float(active["NET_TRDVAL"].sum()) if "NET_TRDVAL" in active.columns else None
    mean_chg     = round(float(active["CHANGE_PCT"].mean()),   2)
    median_chg   = round(float(active["CHANGE_PCT"].median()), 2)
    std_chg      = round(float(active["CHANGE_PCT"].std()),    2)
    p10_chg      = round(float(active["CHANGE_PCT"].quantile(0.10)), 2)
    p90_chg      = round(float(active["CHANGE_PCT"].quantile(0.90)), 2)

    summary = {
        "totalRows":            len(df),
        "activeRows":           len(active),
        "gainers":              gainers,
        "losers":               losers,
        "unchanged":            unchanged,
        "advanceDeclineRatio":  ad_ratio,
        "breadthPct":           breadth_pct,
        "totalMarketValue":     round(total_value, 0) if total_value else None,
        "meanChangePct":        mean_chg,
        "medianChangePct":      median_chg,
        "stdChangePct":         std_chg,
        "p10Change":            p10_chg,
        "p90Change":            p90_chg,
    }

    # ── Circuit breakers ──────────────────────────────────────────────────────
    upper_circuit = pd.DataFrame()
    lower_circuit = pd.DataFrame()
    if "HIGH_PRICE" in active.columns and "LOW_PRICE" in active.columns:
        upper_circuit = active[
            (active["CLOSE_PRICE"] == active["HIGH_PRICE"]) &
            (active["CLOSE_PRICE"] > active["PREV_CL_PR"])
        ]
        lower_circuit = active[
            (active["CLOSE_PRICE"] == active["LOW_PRICE"]) &
            (active["CLOSE_PRICE"] < active["PREV_CL_PR"])
        ]

    def circuit_rows(frame):
        if "SECURITY" not in frame.columns:
            return []
        return [
            {
                "security":  str(r["SECURITY"]),
                "close":     safe_float(r["CLOSE_PRICE"]),
                "changePct": safe_float(r["CHANGE_PCT"]),
            }
            for _, r in frame.iterrows()
        ]

    circuits = {
        "upperCircuitCount":  len(upper_circuit),
        "lowerCircuitCount":  len(lower_circuit),
        "upperCircuitStocks": circuit_rows(upper_circuit),
        "lowerCircuitStocks": circuit_rows(lower_circuit),
    }

    # ── Volatility ────────────────────────────────────────────────────────────
    volatility = {}
    if "HL_RANGE_PCT" in active.columns:
        valid_vol = active[active["HL_RANGE_PCT"].notna() & (active["HL_RANGE_PCT"] > 0)]
        most_volatile = [
            {
                "security":  str(r["SECURITY"]) if "SECURITY" in active.columns else "",
                "close":     safe_float(r["CLOSE_PRICE"]),
                "changePct": safe_float(r["CHANGE_PCT"]),
                "rangePct":  safe_float(r["HL_RANGE_PCT"]),
                "tradeValue": round(float(r["NET_TRDVAL"]), 0) if "NET_TRDVAL" in active.columns else None,
            }
            for _, r in valid_vol.nlargest(15, "HL_RANGE_PCT").iterrows()
        ]
        volatility = {
            "medianRangePct": round(float(valid_vol["HL_RANGE_PCT"].median()), 2),
            "highVolatility": int((valid_vol["HL_RANGE_PCT"] > 5).sum()),
            "lowVolatility":  int((valid_vol["HL_RANGE_PCT"] < 1).sum()),
            "mostVolatile":   most_volatile,
        }

    # ── Return distribution ───────────────────────────────────────────────────
    bins_coarse   = [-100, -10, -5, -2, 0, 2, 5, 10, 100]
    labels_coarse = ["<-10%", "-10 to -5%", "-5 to -2%", "-2 to 0%",
                     "0 to 2%", "2 to 5%", "5 to 10%", ">10%"]
    active["bucket"] = pd.cut(active["CHANGE_PCT"], bins=bins_coarse, labels=labels_coarse)
    dist_coarse = active["bucket"].value_counts().sort_index()

    bins_fine   = [-100, -15, -10, -7, -5, -3, -2, -1, 0, 1, 2, 3, 5, 7, 10, 15, 100]
    labels_fine = [
        "<-15%", "-15 to -10%", "-10 to -7%", "-7 to -5%", "-5 to -3%",
        "-3 to -2%", "-2 to -1%", "-1 to 0%",
        "0 to 1%", "1 to 2%", "2 to 3%", "3 to 5%", "5 to 7%", "7 to 10%", "10 to 15%", ">15%",
    ]
    active["fine_bucket"] = pd.cut(active["CHANGE_PCT"], bins=bins_fine, labels=labels_fine)
    dist_fine = active["fine_bucket"].value_counts().sort_index()

    # ── 52-week proximity ─────────────────────────────────────────────────────
    near52High = []
    near52Low  = []
    if "HI_52_WK" in active.columns and "LO_52_WK" in active.columns:
        nh = active[
            (active["CLOSE_PRICE"] > 0) & (active["HI_52_WK"] > 0) &
            (active["CLOSE_PRICE"] >= active["HI_52_WK"] * 0.97)
        ]
        nl = active[
            (active["CLOSE_PRICE"] > 0) & (active["LO_52_WK"] > 0) &
            (active["CLOSE_PRICE"] <= active["LO_52_WK"] * 1.03)
        ]
        near52High = [
            {
                "security":    str(r["SECURITY"]) if "SECURITY" in active.columns else "",
                "close":       safe_float(r["CLOSE_PRICE"]),
                "high52":      safe_float(r["HI_52_WK"]),
                "pctFromHigh": round((float(r["CLOSE_PRICE"]) / float(r["HI_52_WK"]) - 1) * 100, 2),
            }
            for _, r in nh.nlargest(20, "CLOSE_PRICE").iterrows()
        ]
        near52Low = [
            {
                "security":   str(r["SECURITY"]) if "SECURITY" in active.columns else "",
                "close":      safe_float(r["CLOSE_PRICE"]),
                "low52":      safe_float(r["LO_52_WK"]),
                "pctFromLow": round((float(r["CLOSE_PRICE"]) / float(r["LO_52_WK"]) - 1) * 100, 2),
            }
            for _, r in nl.nsmallest(20, "CLOSE_PRICE").iterrows()
        ]

    # ── Top gainers / losers ──────────────────────────────────────────────────
    def top_rows(frame, col, n=10, ascending=False):
        fn = frame.nsmallest if ascending else frame.nlargest
        rows = []
        for _, r in fn(n, col).iterrows():
            if pd.isna(r.get("CLOSE_PRICE")):
                continue
            rows.append({
                "security":   str(r["SECURITY"]) if "SECURITY" in frame.columns else "",
                "prevClose":  safe_float(r["PREV_CL_PR"]),
                "close":      safe_float(r["CLOSE_PRICE"]),
                "changePct":  safe_float(r["CHANGE_PCT"]),
                "tradeValue": round(float(r["NET_TRDVAL"]), 0) if "NET_TRDVAL" in frame.columns else None,
            })
        return rows

    # ── Most traded (equity series) ───────────────────────────────────────────
    if "MKT" in active.columns:
        equity = active[active["MKT"].isin(["N", "EQ"])]
    else:
        equity = active

    most_traded_val = [
        {
            "security":   str(r["SECURITY"]) if "SECURITY" in equity.columns else "",
            "close":      safe_float(r["CLOSE_PRICE"]),
            "changePct":  safe_float(r["CHANGE_PCT"]),
            "tradeValue": round(float(r["NET_TRDVAL"]), 0),
            "trades":     int(r["TRADES"]) if "TRADES" in equity.columns and pd.notna(r["TRADES"]) else None,
        }
        for _, r in equity.nlargest(15, "NET_TRDVAL").iterrows()
        if "NET_TRDVAL" in equity.columns
    ]

    most_traded_qty = []
    if "NET_TRDQTY" in equity.columns:
        most_traded_qty = [
            {
                "security":  str(r["SECURITY"]) if "SECURITY" in equity.columns else "",
                "close":     safe_float(r["CLOSE_PRICE"]),
                "changePct": safe_float(r["CHANGE_PCT"]),
                "tradeQty":  int(r["NET_TRDQTY"]) if pd.notna(r["NET_TRDQTY"]) else None,
            }
            for _, r in equity.nlargest(15, "NET_TRDQTY").iterrows()
        ]

    return {
        "nifty":            nifty,
        "summary":          summary,
        "circuits":         circuits,
        "volatility":       volatility,
        "distribution": {
            "labels": labels_coarse,
            "values": [int(dist_coarse.get(l, 0)) for l in labels_coarse],
        },
        "fineDistribution": {
            "labels": labels_fine,
            "values": [int(dist_fine.get(l, 0)) for l in labels_fine],
        },
        "topGainers":       top_rows(active, "CHANGE_PCT"),
        "topLosers":        top_rows(active, "CHANGE_PCT", ascending=True),
        "mostTradedByValue": most_traded_val,
        "mostTradedByQty":  most_traded_qty,
        "near52High":       near52High,
        "near52Low":        near52Low,
    }


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    df, trade_date = fetch_latest_bhavcopy()
    data = process(df)
    data["date"] = trade_date.strftime("%d %b %Y")

    with open("data.json", "w") as f:
        json.dump(data, f, indent=2)

    print(f"✓ data.json written — {trade_date}")
