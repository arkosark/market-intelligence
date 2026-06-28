import json
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import requests
from datetime import datetime
import warnings
import os
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
warnings.filterwarnings("ignore")

_anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
ai_client = Anthropic(api_key=_anthropic_key) if _anthropic_key else None

st.set_page_config(
    page_title="Market Intelligence",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
[data-testid="stMetricValue"] { font-size: 1.1rem; }
[data-testid="stMetricDelta"] { font-size: 0.8rem; }
/* Chat panel border */
div[data-testid="stVerticalBlock"] > div:has(div.chat-panel) {
    border-left: 1px solid rgba(255,255,255,0.12);
}
.chat-panel-header {
    font-size: 0.85rem;
    font-weight: 600;
    color: #aaa;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding-bottom: 6px;
    border-bottom: 1px solid rgba(255,255,255,0.1);
    margin-bottom: 8px;
}
/* Compact quick-prompt buttons */
div[data-testid="stButton"] button {
    font-size: 0.72rem !important;
    padding: 2px 6px !important;
}
</style>
""", unsafe_allow_html=True)

# ── Technical indicators ─────────────────────────────────────────────────────

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_g = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_l = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_g / avg_l.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def macd(series: pd.Series, fast=12, slow=26, signal=9):
    ema_f = series.ewm(span=fast, adjust=False).mean()
    ema_s = series.ewm(span=slow, adjust=False).mean()
    line = ema_f - ema_s
    sig = line.ewm(span=signal, adjust=False).mean()
    return line, sig, line - sig

def bollinger(series: pd.Series, period=20, mult=2):
    mid = series.rolling(period).mean()
    std = series.rolling(period).std()
    return mid + mult * std, mid, mid - mult * std

def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()

def cmf(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period=20) -> pd.Series:
    # Money Flow Multiplier: ((close-low) - (high-close)) / (high-low)
    hl = (high - low).replace(0, np.nan)
    mfm = ((close - low) - (high - close)) / hl
    mfv = mfm * volume
    return mfv.rolling(period).sum() / volume.rolling(period).sum()

def mfi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period=14) -> pd.Series:
    typical = (high + low + close) / 3
    raw_mf  = typical * volume
    pos_mf  = raw_mf.where(typical > typical.shift(1), 0)
    neg_mf  = raw_mf.where(typical < typical.shift(1), 0)
    mf_ratio = pos_mf.rolling(period).sum() / neg_mf.rolling(period).sum().replace(0, np.nan)
    return 100 - (100 / (1 + mf_ratio))

# ── Data fetchers ────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def fetch_fear_greed():
    try:
        r = requests.get("https://api.alternative.me/fng/", timeout=10)
        d = r.json()["data"][0]
        return int(d["value"]), d["value_classification"]
    except Exception:
        return None, None

@st.cache_data(ttl=300, show_spinner=False)
def fetch_vix():
    return yf.download("^VIX", period="3mo", interval="1d", progress=False, auto_adjust=True)

@st.cache_data(ttl=300, show_spinner=False)
def fetch_macro():
    tickers = {
        "S&P 500": "^GSPC", "Nasdaq": "^IXIC", "Dow Jones": "^DJI",
        "10Y Yield": "^TNX", "Gold": "GC=F", "Oil (WTI)": "CL=F", "VIX": "^VIX",
    }
    rows = []
    for name, t in tickers.items():
        try:
            d = yf.download(t, period="5d", interval="1d", progress=False, auto_adjust=True)
            if len(d) >= 2:
                c = d["Close"].squeeze()
                chg = (c.iloc[-1] / c.iloc[-2] - 1) * 100
                rows.append({"name": name, "value": round(float(c.iloc[-1]), 2), "chg": round(float(chg), 2)})
        except Exception:
            pass
    return rows

SECTORS = {
    "Technology": "XLK", "Healthcare": "XLV", "Energy": "XLE",
    "Financials": "XLF", "Industrials": "XLI", "Consumer Disc": "XLY",
    "Staples": "XLP", "Utilities": "XLU", "Materials": "XLB",
    "Real Estate": "XLRE", "Communication": "XLC", "Semiconductors": "SOXX",
}

@st.cache_data(ttl=300, show_spinner=False)
def fetch_sectors():
    rows = []
    for name, ticker in SECTORS.items():
        try:
            d = yf.download(ticker, period="3mo", interval="1d", progress=False, auto_adjust=True)
            if len(d) < 20:
                continue
            c = d["Close"].squeeze()
            r = float(rsi(c).iloc[-1])
            rows.append({
                "Sector": name, "Ticker": ticker,
                "Price": round(float(c.iloc[-1]), 2),
                "RSI": round(r, 1),
                "1W %": round(float((c.iloc[-1] / c.iloc[-5] - 1) * 100), 2) if len(c) >= 5 else 0,
                "1M %": round(float((c.iloc[-1] / c.iloc[-21] - 1) * 100), 2) if len(c) >= 21 else 0,
                "Signal": "🔴 Overbought" if r > 70 else ("🟢 Oversold" if r < 30 else "⚪ Neutral"),
            })
        except Exception:
            pass
    return pd.DataFrame(rows)

SCREENER_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "META", "AMZN", "NVDA", "AMD", "INTC", "QCOM", "AVGO",
    "TSM", "ASML", "MU", "AMAT", "LRCX", "KLAC", "TXN", "MRVL", "ON", "ARM",
    "TSLA", "NFLX", "CRM", "SNOW", "PLTR", "DDOG", "ZS", "CRWD", "NET", "PANW",
    "JPM", "V", "MA", "UNH", "XOM", "CVX", "LLY", "ABBV",
]

SECTOR_TICKER_MAP = {
    "Healthcare":             ["JNJ","UNH","LLY","ABBV","MRK","TMO","ABT","DHR","BMY","AMGN","GILD","VRTX","REGN","ISRG","CVS","HUM","CI","ELV","ZBH","BSX"],
    "Technology":             ["AAPL","MSFT","NVDA","AMD","GOOGL","META","AVGO","QCOM","INTC","TXN","AMAT","LRCX","KLAC","NOW","ADBE","INTU","SNPS","CDNS"],
    "Semiconductors":         ["NVDA","AMD","INTC","QCOM","AVGO","TSM","ASML","MU","AMAT","LRCX","KLAC","TXN","MRVL","ON","ARM","WOLF","SWKS","MPWR"],
    "Energy":                 ["XOM","CVX","COP","EOG","SLB","MPC","VLO","PSX","OXY","PXD","HAL","BKR","DVN","FANG","MRO"],
    "Financials":             ["JPM","BAC","WFC","GS","MS","C","BLK","V","MA","AXP","SCHW","CB","PGR","MET","TRV"],
    "Industrials":            ["CAT","DE","HON","UPS","FDX","RTX","LMT","NOC","BA","GE","MMM","ETN","EMR","PH","ROK"],
    "Consumer Discretionary": ["AMZN","TSLA","HD","NKE","SBUX","MCD","TGT","LOW","BKNG","CMG","ABNB","F","GM","RCL","CCL"],
    "Consumer Staples":       ["WMT","PG","KO","PEP","COST","PM","MO","MDLZ","CL","GIS","KHC","HSY","STZ","SYY"],
    "Communication":          ["GOOGL","META","NFLX","DIS","CMCSA","T","VZ","TMUS","SNAP","PINS","EA","TTWO","WBD"],
    "Real Estate":            ["AMT","PLD","CCI","EQIX","PSA","O","DLR","SPG","WELL","AVB","EQR","VICI","WY"],
    "Utilities":              ["NEE","DUK","SO","D","AEP","EXC","SRE","XEL","WEC","ES","ETR","PPL","AEE"],
    "Materials":              ["LIN","APD","SHW","ECL","NEM","FCX","NUE","VMC","MLM","DOW","DD","ALB","MOS"],
}

@st.cache_data(ttl=900, show_spinner=False)
def fetch_screener():
    rows = []
    for ticker in SCREENER_TICKERS:
        try:
            info = yf.Ticker(ticker).info
            d = yf.download(ticker, period="3mo", interval="1d", progress=False, auto_adjust=True)
            if len(d) < 20:
                continue
            c = d["Close"].squeeze()
            r = float(rsi(c).iloc[-1])
            price = float(c.iloc[-1])
            ma50 = float(c.rolling(50).mean().iloc[-1])
            ret1m = float((c.iloc[-1] / c.iloc[-21] - 1) * 100) if len(c) >= 21 else 0
            pe = info.get("trailingPE")
            fwd_pe = info.get("forwardPE")
            eps_g = info.get("earningsGrowth")
            rev_g = info.get("revenueGrowth")
            gm = info.get("grossMargins")
            mcap = info.get("marketCap", 0)
            score = 0
            if pe and 0 < pe < 45: score += 1
            if eps_g and eps_g > 0.10: score += 2
            if rev_g and rev_g > 0.10: score += 1
            if 40 < r < 60: score += 1
            if price > ma50: score += 1
            rows.append({
                "Ticker": ticker, "Sector": info.get("sector", "N/A"),
                "Price": round(price, 2), "RSI": round(r, 1),
                "P/E": round(pe, 1) if pe else None,
                "Fwd P/E": round(fwd_pe, 1) if fwd_pe else None,
                "EPS Grwth%": round(eps_g * 100, 1) if eps_g else None,
                "Rev Grwth%": round(rev_g * 100, 1) if rev_g else None,
                "Gross Mgn%": round(gm * 100, 1) if gm else None,
                "1M %": round(ret1m, 2),
                ">MA50": "✅" if price > ma50 else "❌",
                "Score": score, "_mcap": mcap,
            })
        except Exception:
            pass
    return pd.DataFrame(rows)

@st.cache_data(ttl=900, show_spinner=False)
def fetch_stock(ticker: str, period: str):
    hist = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=True)
    info = yf.Ticker(ticker).info
    return hist, info

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_earnings_calendar():
    watch = ["AAPL", "MSFT", "GOOGL", "META", "AMZN", "NVDA", "AMD", "TSLA",
             "NFLX", "CRM", "SNOW", "PLTR", "DDOG", "CRWD", "NET", "MU", "AVGO",
             "QCOM", "TSM", "PANW", "ZS", "INTC", "ARM", "ON"]
    rows = []
    for ticker in watch:
        try:
            cal = yf.Ticker(ticker).calendar
            if cal is None:
                continue
            dates = cal.get("Earnings Date", [])
            if dates:
                rows.append({
                    "Ticker": ticker,
                    "Date": pd.to_datetime(dates[0]),
                    "EPS Est": cal.get("EPS Estimate", "—"),
                    "Rev Est ($B)": round(cal.get("Revenue Estimate", 0) / 1e9, 2) if cal.get("Revenue Estimate") else "—",
                })
        except Exception:
            pass
    return pd.DataFrame(rows)

# ── Helpers ──────────────────────────────────────────────────────────────────

def rsi_color(v):
    if pd.isna(v): return ""
    if v > 70: return "background-color:#5c2020; color:white"
    if v < 30: return "background-color:#1a4d2e; color:white"
    return ""

def score_color(v):
    if pd.isna(v): return ""
    if v >= 5: return "background-color:#1a4d2e; color:white; font-weight:bold"
    if v >= 3: return "background-color:#4d3c00; color:white"
    return ""

AI_TOOLS = [
    {
        "name": "get_stock_analysis",
        "description": "Fetch live technical and fundamental data for any stock ticker. Use this whenever the user asks about a specific stock not already in the dashboard snapshot.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol e.g. AAPL, LLY, JPM"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_sector_stocks",
        "description": "Fetch and rank stocks within a specific sector by opportunity score. Use when user asks about a sector not fully covered in the snapshot (e.g. Healthcare, Energy, Financials).",
        "input_schema": {
            "type": "object",
            "properties": {
                "sector": {"type": "string", "description": "Sector name e.g. Healthcare, Energy, Financials, Semiconductors"},
                "top_n": {"type": "integer", "description": "How many top stocks to return (default 8)"},
            },
            "required": ["sector"],
        },
    },
    {
        "name": "get_flow_and_institutional",
        "description": "Fetch volume flow indicators (OBV trend, CMF, MFI) and institutional ownership data for a stock. Use when user asks about smart money, institutional buying/selling, or entry/exit timing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "screen_stocks",
        "description": "Custom stock screen across all sectors. Filter by RSI, P/E, EPS growth, revenue growth to find opportunities.",
        "input_schema": {
            "type": "object",
            "properties": {
                "max_rsi":        {"type": "number", "description": "Maximum RSI (e.g. 60)"},
                "min_eps_growth": {"type": "number", "description": "Minimum EPS growth % (e.g. 15)"},
                "max_pe":         {"type": "number", "description": "Maximum trailing P/E (e.g. 30)"},
                "min_rev_growth": {"type": "number", "description": "Minimum revenue growth % (e.g. 10)"},
                "sectors":        {"type": "array", "items": {"type": "string"}, "description": "List of sectors to search (empty = all)"},
                "top_n":          {"type": "integer", "description": "Number of results (default 10)"},
            },
            "required": [],
        },
    },
]


def _analyze_ticker(ticker: str) -> dict:
    ticker = ticker.upper().strip()
    d = yf.download(ticker, period="3mo", interval="1d", progress=False, auto_adjust=True)
    info = yf.Ticker(ticker).info
    c = d["Close"].squeeze().astype(float)
    o = d["Open"].squeeze().astype(float)
    price  = float(c.iloc[-1])
    r_val  = float(rsi(c).iloc[-1])
    ml, ms, _ = macd(c)
    bu, _, bl  = bollinger(c)
    ma50v  = float(c.rolling(50).mean().iloc[-1])
    ma200v = float(c.rolling(200).mean().iloc[-1]) if len(c) >= 200 else None
    ret1m  = float((c.iloc[-1] / c.iloc[-21] - 1) * 100) if len(c) >= 21 else 0
    macd_sig = ("Bullish crossover"  if float(ml.iloc[-1]) > float(ms.iloc[-1]) and float(ml.iloc[-2]) <= float(ms.iloc[-2]) else
                "Bearish crossover"  if float(ml.iloc[-1]) < float(ms.iloc[-1]) and float(ml.iloc[-2]) >= float(ms.iloc[-2]) else
                "Above signal line"  if float(ml.iloc[-1]) > float(ms.iloc[-1]) else "Below signal line")
    bb_pos = ("above upper band" if price > float(bu.iloc[-1]) else
              "below lower band" if price < float(bl.iloc[-1]) else "within bands")
    pe     = info.get("trailingPE")
    fwd_pe = info.get("forwardPE")
    eps_g  = info.get("earningsGrowth")
    rev_g  = info.get("revenueGrowth")
    gm     = info.get("grossMargins")
    target = info.get("targetMeanPrice")
    mcap   = info.get("marketCap")
    score  = 0
    if pe and 0 < pe < 45:          score += 1
    if eps_g and eps_g > 0.10:      score += 2
    if rev_g and rev_g > 0.10:      score += 1
    if 40 < r_val < 60:             score += 1
    if price > ma50v:               score += 1
    return {
        "ticker": ticker, "price": price, "rsi": round(r_val, 1),
        "ret1m": round(ret1m, 1), "ma50_above": price > ma50v,
        "ma200_above": (price > ma200v) if ma200v else None,
        "macd": macd_sig, "bollinger": bb_pos,
        "pe": round(pe, 1) if pe else None,
        "fwd_pe": round(fwd_pe, 1) if fwd_pe else None,
        "eps_growth": round(eps_g * 100, 1) if eps_g else None,
        "rev_growth": round(rev_g * 100, 1) if rev_g else None,
        "gross_margin": round(gm * 100, 1) if gm else None,
        "analyst_target": round(target, 2) if target else None,
        "upside": round((target / price - 1) * 100, 1) if target else None,
        "mcap_b": round(mcap / 1e9, 1) if mcap else None,
        "sector": info.get("sector", ""),
        "score": score,
    }


def _fmt_analysis(a: dict) -> str:
    lines = [
        f"{a['ticker']} | ${a['price']} | RSI {a['rsi']} | 1M {a['ret1m']:+.1f}%",
        f"  MACD: {a['macd']} | Bollinger: {a['bollinger']}",
        f"  vs MA50: {'above' if a['ma50_above'] else 'below'}" +
        (f" | vs MA200: {'above' if a['ma200_above'] else 'below'}" if a['ma200_above'] is not None else ""),
    ]
    funds = []
    if a["pe"]:          funds.append(f"P/E {a['pe']}")
    if a["fwd_pe"]:      funds.append(f"Fwd P/E {a['fwd_pe']}")
    if a["eps_growth"]:  funds.append(f"EPS {a['eps_growth']:+.1f}%")
    if a["rev_growth"]:  funds.append(f"Rev {a['rev_growth']:+.1f}%")
    if a["gross_margin"]:funds.append(f"GM {a['gross_margin']:.1f}%")
    if a["analyst_target"]: funds.append(f"Target ${a['analyst_target']} ({a['upside']:+.1f}% upside)")
    if funds:
        lines.append("  " + " | ".join(funds))
    lines.append(f"  Opportunity Score: {a['score']}/6")
    return "\n".join(lines)


def run_tool(name: str, inputs: dict) -> str:
    try:
        if name == "get_stock_analysis":
            a = _analyze_ticker(inputs["ticker"])
            return _fmt_analysis(a)

        elif name == "get_flow_and_institutional":
            ticker = inputs["ticker"].upper()
            d = yf.download(ticker, period="3mo", interval="1d", progress=False, auto_adjust=True)
            c = d["Close"].squeeze().astype(float)
            h = d["High"].squeeze().astype(float)
            l = d["Low"].squeeze().astype(float)
            v = d["Volume"].squeeze().astype(float)
            obv_s  = obv(c, v)
            cmf_s  = cmf(h, l, c, v)
            mfi_s  = mfi(h, l, c, v)
            cur_cmf = float(cmf_s.iloc[-1]) if not pd.isna(cmf_s.iloc[-1]) else 0
            cur_mfi = float(mfi_s.iloc[-1]) if not pd.isna(mfi_s.iloc[-1]) else 50
            obv_chg = float(obv_s.iloc[-1]) - float(obv_s.iloc[-5])
            avg_vol = float(v.rolling(20).mean().iloc[-1])
            cur_vol = float(v.iloc[-1])
            lines = [f"FLOW & INSTITUTIONAL DATA: {ticker}"]
            lines.append(f"  CMF (20): {cur_cmf:.3f} → {'Accumulation (smart money buying)' if cur_cmf>0.05 else ('Distribution (smart money selling)' if cur_cmf<-0.05 else 'Neutral')}")
            lines.append(f"  MFI (14): {cur_mfi:.1f} → {'Overbought — selling pressure' if cur_mfi>80 else ('Oversold — buying pressure' if cur_mfi<20 else 'Neutral')}")
            lines.append(f"  OBV 5-day change: {'+' if obv_chg>=0 else ''}{obv_chg:,.0f} → {'Accumulating' if obv_chg>0 else 'Distributing'}")
            lines.append(f"  Volume vs 20-day avg: {cur_vol/avg_vol:.1f}x ({'above average — conviction' if cur_vol>avg_vol*1.5 else 'normal'})")
            try:
                t_obj = yf.Ticker(ticker)
                ih = t_obj.institutional_holders
                mh = t_obj.major_holders
                if mh is not None and not mh.empty:
                    mh.columns = ["Value","Description"]
                    lines.append("\nOWNERSHIP:")
                    for _, row in mh.iterrows():
                        lines.append(f"  {row['Description']}: {row['Value']}")
                if ih is not None and not ih.empty:
                    lines.append("\nTOP INSTITUTIONAL HOLDERS (13F, quarterly):")
                    for _, row in ih.head(8).iterrows():
                        pct = row.get("pctHeld", 0)
                        shares = row.get("Shares", 0)
                        lines.append(f"  {row.get('Holder','?')}: {shares:,.0f} shares ({pct*100:.2f}%)")
            except Exception:
                lines.append("\nInstitutional data unavailable.")
            return "\n".join(lines)

        elif name == "get_sector_stocks":
            sector = inputs.get("sector", "")
            top_n  = inputs.get("top_n", 8)
            tickers = None
            for k, v in SECTOR_TICKER_MAP.items():
                if k.lower() in sector.lower() or sector.lower() in k.lower():
                    tickers = v
                    break
            if tickers is None:
                return f"Unknown sector '{sector}'. Available: {', '.join(SECTOR_TICKER_MAP.keys())}"
            results = []
            for t in tickers:
                try:
                    results.append(_analyze_ticker(t))
                except Exception:
                    pass
            results.sort(key=lambda x: x["score"], reverse=True)
            lines = [f"TOP {sector.upper()} STOCKS (ranked by opportunity score):"]
            for a in results[:top_n]:
                lines.append(_fmt_analysis(a))
                lines.append("")
            return "\n".join(lines)

        elif name == "screen_stocks":
            max_rsi    = inputs.get("max_rsi", 100)
            min_eps    = inputs.get("min_eps_growth", 0)
            max_pe     = inputs.get("max_pe", 9999)
            min_rev    = inputs.get("min_rev_growth", 0)
            sectors    = [s.lower() for s in inputs.get("sectors", [])]
            top_n      = inputs.get("top_n", 10)
            all_tickers = []
            for k, v in SECTOR_TICKER_MAP.items():
                if not sectors or any(s in k.lower() for s in sectors):
                    all_tickers.extend(v)
            all_tickers = list(dict.fromkeys(all_tickers))
            results = []
            for t in all_tickers:
                try:
                    a = _analyze_ticker(t)
                    if a["rsi"] > max_rsi: continue
                    if a["eps_growth"] is not None and a["eps_growth"] < min_eps: continue
                    if a["pe"] is not None and a["pe"] > max_pe: continue
                    if a["rev_growth"] is not None and a["rev_growth"] < min_rev: continue
                    results.append(a)
                except Exception:
                    pass
            results.sort(key=lambda x: x["score"], reverse=True)
            if not results:
                return "No stocks matched the criteria."
            lines = [f"SCREEN RESULTS (top {min(top_n, len(results))} of {len(results)} matches):"]
            for a in results[:top_n]:
                lines.append(_fmt_analysis(a))
                lines.append("")
            return "\n".join(lines)

        return "Unknown tool."
    except Exception as e:
        return f"Tool error: {e}"


def build_market_context() -> str:
    lines = [f"MARKET SNAPSHOT — {datetime.now().strftime('%Y-%m-%d %H:%M')}"]
    fg_score, fg_rating = fetch_fear_greed()
    if fg_score:
        lines.append(f"Fear & Greed: {fg_score}/100 ({fg_rating})")
    vix_df = fetch_vix()
    if not vix_df.empty:
        lines.append(f"VIX: {float(vix_df['Close'].squeeze().iloc[-1]):.1f}")
    macro = fetch_macro()
    if macro:
        lines.append("\nMACRO:")
        for m in macro:
            lines.append(f"  {m['name']}: {m['value']} ({m['chg']:+.2f}%)")
    try:
        df_sec = fetch_sectors()
        if not df_sec.empty:
            lines.append("\nSECTORS (RSI | 1W% | 1M%):")
            for _, row in df_sec.iterrows():
                lines.append(f"  {row['Sector']}: RSI {row['RSI']} {row['Signal']} | 1W {row['1W %']:+.1f}% | 1M {row['1M %']:+.1f}%")
    except Exception:
        pass
    try:
        df_sc = fetch_screener()
        if not df_sc.empty:
            top = df_sc.nlargest(8, "Score")
            lines.append("\nTOP OPPORTUNITIES:")
            for _, r in top.iterrows():
                eps = f"{r['EPS Grwth%']:.1f}%" if pd.notna(r['EPS Grwth%']) else "—"
                rev = f"{r['Rev Grwth%']:.1f}%" if pd.notna(r['Rev Grwth%']) else "—"
                pe  = f"{r['P/E']:.1f}"          if pd.notna(r['P/E'])        else "—"
                lines.append(f"  {r['Ticker']}: Score {r['Score']}/6 | RSI {r['RSI']} | P/E {pe} | EPS {eps} | Rev {rev} | 1M {r['1M %']:+.1f}%")
    except Exception:
        pass
    dd_ticker = st.session_state.get("dd_ticker", "")
    if dd_ticker:
        try:
            h, inf = fetch_stock(dd_ticker, "3mo")
            c = h["Close"].squeeze().astype(float)
            r_val = float(rsi(c).iloc[-1])
            ml, ms, _ = macd(c)
            bu, _, bl = bollinger(c)
            price = float(c.iloc[-1])
            ma50v = float(c.rolling(50).mean().iloc[-1])
            macd_sig = ("Bullish crossover" if float(ml.iloc[-1]) > float(ms.iloc[-1]) and float(ml.iloc[-2]) <= float(ms.iloc[-2])
                        else "Bearish crossover" if float(ml.iloc[-1]) < float(ms.iloc[-1]) and float(ml.iloc[-2]) >= float(ms.iloc[-2])
                        else "Above signal" if float(ml.iloc[-1]) > float(ms.iloc[-1]) else "Below signal")
            bb_pos = ("above upper band" if price > float(bu.iloc[-1])
                      else "below lower band" if price < float(bl.iloc[-1]) else "within bands")
            lines.append(f"\nCURRENT DEEP DIVE: {dd_ticker}")
            lines.append(f"  Price: ${price:.2f} | RSI: {r_val:.1f} | vs MA50: {'above' if price > ma50v else 'below'}")
            lines.append(f"  MACD: {macd_sig} | Bollinger: {bb_pos}")
            for key in ["trailingPE", "forwardPE", "earningsGrowth", "revenueGrowth",
                        "grossMargins", "marketCap", "beta", "targetMeanPrice"]:
                v = inf.get(key)
                if v:
                    label = {"trailingPE": "P/E", "forwardPE": "Fwd P/E", "earningsGrowth": "EPS Growth",
                             "revenueGrowth": "Rev Growth", "grossMargins": "Gross Margin",
                             "marketCap": "Mkt Cap", "beta": "Beta", "targetMeanPrice": "Analyst Target"}.get(key, key)
                    if key in ("earningsGrowth", "revenueGrowth", "grossMargins"):
                        lines.append(f"  {label}: {v*100:.1f}%")
                    elif key == "marketCap":
                        lines.append(f"  {label}: ${v/1e9:.1f}B")
                    else:
                        lines.append(f"  {label}: {round(v, 2)}")
        except Exception:
            pass
    return "\n".join(lines)

SYSTEM_PROMPT = """You are a sharp, concise market analyst assistant embedded in a live trading dashboard.

You have two sources of data:
1. A live market snapshot injected below (Fear & Greed, VIX, macro, sectors, top opportunities, current deep-dive stock)
2. Tools you can call ON DEMAND to fetch live data for ANY stock or sector not already in the snapshot

Use tools proactively — if the user asks about a stock or sector not in the snapshot, fetch it immediately rather than saying you don't have the data.

Your job:
- Answer questions about any stock, sector, or macro condition
- Give clear entry/exit insights, flag risks, identify opportunities
- Explain technical signals (RSI, MACD, Bollinger) in plain English with actionable context
- Be direct and concise — bullet points preferred over paragraphs
- Always ground recommendations in actual fetched data
- Add a brief risk disclaimer for specific trade recommendations"""

# ── Page header ──────────────────────────────────────────────────────────────

st.title("📈 Market Intelligence Dashboard")
st.caption(f"Data: Yahoo Finance (15-min delayed) · Fear & Greed: CNN · {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# ── Two-column layout: charts (left) + AI chat (right, narrow) ───────────────

if "chat_expanded" not in st.session_state:
    st.session_state.chat_expanded = False

_ratio = [2, 2] if st.session_state.chat_expanded else [4, 1]
main_col, chat_col = st.columns(_ratio)

# ════════════════════════════════════════════════════════════════
# LEFT — MAIN CONTENT (4 tabs)
# ════════════════════════════════════════════════════════════════
with main_col:
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🌡️ Market Pulse", "🔍 Screener", "📊 Deep Dive", "📅 Earnings", "🔭 Intelligence Feed"])

    # ── TAB 1: MARKET PULSE ──────────────────────────────────────
    with tab1:
        col_fg, col_vix, col_macro = st.columns([1, 1.5, 2.5])

        with col_fg:
            st.markdown("#### Fear & Greed")
            score, rating = fetch_fear_greed()
            if score is not None:
                needle_color = "#e74c3c" if score > 65 else ("#2ecc71" if score < 35 else "#f39c12")
                fig_fg = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=score,
                    title={"text": rating or "", "font": {"size": 13}},
                    number={"font": {"size": 36}},
                    gauge={
                        "axis": {"range": [0, 100], "tickwidth": 1},
                        "bar": {"color": needle_color, "thickness": 0.25},
                        "steps": [
                            {"range": [0, 25],   "color": "#1a4d2e"},
                            {"range": [25, 45],  "color": "#2d6e46"},
                            {"range": [45, 55],  "color": "#404040"},
                            {"range": [55, 75],  "color": "#6e3d2d"},
                            {"range": [75, 100], "color": "#5c2020"},
                        ],
                        "threshold": {"line": {"color": "white", "width": 3},
                                      "thickness": 0.8, "value": score},
                    },
                ))
                fig_fg.update_layout(height=220, margin=dict(t=20, b=0, l=10, r=10),
                                     paper_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_fg, use_container_width=True)
            else:
                st.warning("Unavailable")

        with col_vix:
            st.markdown("#### VIX — Volatility Index")
            vix_df = fetch_vix()
            if not vix_df.empty:
                vc = vix_df["Close"].squeeze()
                cur_vix = float(vc.iloc[-1])
                prev_vix = float(vc.iloc[-2])
                vix_col = "#e74c3c" if cur_vix > 25 else ("#f39c12" if cur_vix > 18 else "#2ecc71")
                st.metric("Current", f"{cur_vix:.1f}", f"{cur_vix-prev_vix:+.2f}", delta_color="inverse")
                fig_vix = go.Figure()
                fig_vix.add_trace(go.Scatter(x=vix_df.index, y=vc, fill="tozeroy",
                                             line=dict(color=vix_col, width=2), name="VIX"))
                fig_vix.add_hline(y=20, line_dash="dash", line_color="orange",
                                  annotation_text="20 – Fear", annotation_position="top left")
                fig_vix.add_hline(y=30, line_dash="dash", line_color="red",
                                  annotation_text="30 – Extreme Fear")
                fig_vix.update_layout(height=180, margin=dict(t=5, b=5, l=0, r=0),
                                      showlegend=False, paper_bgcolor="rgba(0,0,0,0)",
                                      plot_bgcolor="rgba(0,0,0,0)",
                                      yaxis=dict(gridcolor="rgba(128,128,128,0.15)"),
                                      xaxis=dict(gridcolor="rgba(128,128,128,0.15)"))
                st.plotly_chart(fig_vix, use_container_width=True)

        with col_macro:
            st.markdown("#### Macro Snapshot")
            macro = fetch_macro()
            if macro:
                cols = st.columns(len(macro))
                for i, m in enumerate(macro):
                    dc = "inverse" if m["name"] == "10Y Yield" else "normal"
                    cols[i].metric(m["name"], m["value"], f"{m['chg']:+.2f}%", delta_color=dc)

        st.divider()
        st.markdown("#### Sector Heatmap — RSI + Performance")
        with st.spinner("Loading sector data…"):
            df_sec = fetch_sectors()

        if not df_sec.empty:
            bar_colors = ["#e74c3c" if r > 70 else ("#2ecc71" if r < 30 else "#3498db")
                          for r in df_sec["RSI"]]
            fig_bar = go.Figure(go.Bar(
                x=df_sec["Sector"], y=df_sec["RSI"],
                marker_color=bar_colors,
                customdata=df_sec[["Signal", "1W %", "1M %", "Price"]].values,
                hovertemplate=(
                    "<b>%{x}</b><br>RSI: %{y}<br>%{customdata[0]}<br>"
                    "1W: %{customdata[1]}%  1M: %{customdata[2]}%<br>"
                    "Price: $%{customdata[3]}<extra></extra>"
                ),
            ))
            fig_bar.add_hline(y=70, line_dash="dash", line_color="#e74c3c",
                              annotation_text="Overbought 70", annotation_position="top left")
            fig_bar.add_hline(y=30, line_dash="dash", line_color="#2ecc71",
                              annotation_text="Oversold 30", annotation_position="bottom left")
            fig_bar.update_layout(height=320, margin=dict(t=10, b=10),
                                  paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                  yaxis=dict(title="RSI", gridcolor="rgba(128,128,128,0.15)"),
                                  xaxis=dict(gridcolor="rgba(128,128,128,0.15)"))
            st.plotly_chart(fig_bar, use_container_width=True)

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**1-Week Returns**")
                fig1w = px.bar(df_sec.sort_values("1W %"), x="1W %", y="Sector", orientation="h",
                               color="1W %", color_continuous_scale=["#e74c3c", "#333", "#2ecc71"],
                               color_continuous_midpoint=0)
                fig1w.update_layout(height=320, margin=dict(t=5, b=5),
                                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                    coloraxis_showscale=False)
                st.plotly_chart(fig1w, use_container_width=True)
            with c2:
                st.markdown("**1-Month Returns**")
                fig1m = px.bar(df_sec.sort_values("1M %"), x="1M %", y="Sector", orientation="h",
                               color="1M %", color_continuous_scale=["#e74c3c", "#333", "#2ecc71"],
                               color_continuous_midpoint=0)
                fig1m.update_layout(height=320, margin=dict(t=5, b=5),
                                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                    coloraxis_showscale=False)
                st.plotly_chart(fig1m, use_container_width=True)

    # ── TAB 2: SCREENER ──────────────────────────────────────────
    with tab2:
        st.markdown("#### Stock Screener — Fundamentals + Technicals")
        with st.spinner("Loading screener (~30s first load)…"):
            df_sc = fetch_screener()

        if not df_sc.empty:
            f1, f2, f3, f4 = st.columns(4)
            with f1:
                opts = ["All"] + sorted(df_sc["Sector"].dropna().unique().tolist())
                sel_sec = st.selectbox("Sector", opts)
            with f2:
                rsi_min, rsi_max = st.slider("RSI", 0, 100, (20, 80))
            with f3:
                min_score = st.slider("Min Opportunity Score", 0, 6, 2)
            with f4:
                sort_col = st.selectbox("Sort by", ["Score", "RSI", "1M %", "P/E", "EPS Grwth%"])

            filtered = df_sc.copy()
            if sel_sec != "All":
                filtered = filtered[filtered["Sector"] == sel_sec]
            filtered = filtered[filtered["RSI"].between(rsi_min, rsi_max)]
            filtered = filtered[filtered["Score"] >= min_score]
            filtered = filtered.sort_values(sort_col, ascending=(sort_col not in ["Score", "EPS Grwth%", "1M %"]))

            display_cols = ["Ticker", "Sector", "Price", "RSI", "P/E", "Fwd P/E",
                            "EPS Grwth%", "Rev Grwth%", "Gross Mgn%", "1M %", ">MA50", "Score"]
            styled = (
                filtered[display_cols].style
                .map(rsi_color, subset=["RSI"])
                .map(score_color, subset=["Score"])
                .format({"Price": "${:.2f}", "1M %": "{:+.2f}%",
                         "EPS Grwth%": lambda x: f"{x:.1f}%" if pd.notna(x) else "—",
                         "Rev Grwth%": lambda x: f"{x:.1f}%" if pd.notna(x) else "—",
                         "Gross Mgn%": lambda x: f"{x:.1f}%" if pd.notna(x) else "—",
                         "P/E": lambda x: f"{x:.1f}" if pd.notna(x) else "—",
                         "Fwd P/E": lambda x: f"{x:.1f}" if pd.notna(x) else "—"}, na_rep="—")
            )
            st.dataframe(styled, use_container_width=True, height=420)

            st.divider()
            st.markdown("#### Opportunity Map — P/E vs EPS Growth")
            bubble = df_sc.dropna(subset=["P/E", "EPS Grwth%"]).copy()
            bubble = bubble[(bubble["P/E"] > 0) & (bubble["P/E"] < 100)]
            bubble["Cap_B"] = (bubble["_mcap"].fillna(0) / 1e9).clip(upper=3000)
            if not bubble.empty:
                fig_bub = px.scatter(
                    bubble, x="P/E", y="EPS Grwth%", size="Cap_B", color="RSI",
                    color_continuous_scale=["#2ecc71", "#f39c12", "#e74c3c"],
                    range_color=[20, 80], hover_name="Ticker",
                    hover_data={"Sector": True, "Price": True, "1M %": True,
                                "Cap_B": False, "_mcap": False},
                    labels={"EPS Grwth%": "EPS Growth %", "P/E": "Trailing P/E"},
                )
                fig_bub.add_vline(x=25, line_dash="dash", line_color="gray", annotation_text="P/E 25")
                fig_bub.add_hline(y=10, line_dash="dash", line_color="gray", annotation_text="10% EPS Growth")
                fig_bub.update_layout(height=480, paper_bgcolor="rgba(0,0,0,0)",
                                      plot_bgcolor="rgba(0,0,0,0)",
                                      yaxis=dict(gridcolor="rgba(128,128,128,0.15)"),
                                      xaxis=dict(gridcolor="rgba(128,128,128,0.15)"))
                st.plotly_chart(fig_bub, use_container_width=True)

    # ── TAB 3: DEEP DIVE ─────────────────────────────────────────
    with tab3:
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            ticker_in = st.text_input("Ticker", value="NVDA").upper().strip()
            st.session_state["dd_ticker"] = ticker_in
        with c2:
            PERIOD_MAP = {
                "1 Week":   ("5d",  None),
                "3 Weeks":  ("1mo", 15),
                "1 Month":  ("1mo", None),
                "3 Months": ("3mo", None),
                "6 Months": ("6mo", None),
                "1 Year":   ("1y",  None),
                "2 Years":  ("2y",  None),
            }
            period_label = st.selectbox("Period", list(PERIOD_MAP.keys()), index=4)
            yf_period, slice_rows = PERIOD_MAP[period_label]
        with c3:
            st.markdown("<br>", unsafe_allow_html=True)
            st.button("Load", type="primary", use_container_width=True)

        if ticker_in:
            with st.spinner(f"Loading {ticker_in}…"):
                hist, info = fetch_stock(ticker_in, yf_period)
            if slice_rows:
                hist = hist.tail(slice_rows)

            if hist.empty:
                st.error(f"No data for {ticker_in}")
            else:
                close = hist["Close"].squeeze().astype(float)
                open_ = hist["Open"].squeeze().astype(float)
                high  = hist["High"].squeeze().astype(float)
                low   = hist["Low"].squeeze().astype(float)
                vol   = hist["Volume"].squeeze().astype(float)

                price = float(close.iloc[-1])
                chg_pct = (price / float(close.iloc[-2]) - 1) * 100

                m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
                m1.metric("Price", f"${price:.2f}", f"{chg_pct:+.2f}%")
                mcap = info.get("marketCap")
                m2.metric("Mkt Cap", f"${mcap/1e9:.1f}B" if mcap else "—")
                m3.metric("P/E (TTM)", f"{info.get('trailingPE'):.1f}" if info.get("trailingPE") else "—")
                m4.metric("Fwd P/E",  f"{info.get('forwardPE'):.1f}"  if info.get("forwardPE")  else "—")
                m5.metric("52W High", f"${info.get('fiftyTwoWeekHigh','—')}")
                m6.metric("52W Low",  f"${info.get('fiftyTwoWeekLow','—')}")
                m7.metric("Beta",     f"{info.get('beta','—')}")

                rsi_vals = rsi(close)
                macd_l, macd_sig, macd_hist = macd(close)
                bb_up, bb_mid, bb_lo = bollinger(close)
                ma50  = close.rolling(50).mean()
                ma200 = close.rolling(200).mean()
                obv_vals = obv(close, vol)
                cmf_vals = cmf(high, low, close, vol)
                mfi_vals = mfi(high, low, close, vol)

                fig = make_subplots(
                    rows=6, cols=1, shared_xaxes=True,
                    row_heights=[0.38, 0.10, 0.13, 0.13, 0.13, 0.13],
                    vertical_spacing=0.018,
                    subplot_titles=(
                        f"{ticker_in} · Price",
                        "Volume + OBV",
                        "RSI (14)",
                        "MFI — Money Flow Index (14)",
                        "CMF — Chaikin Money Flow (20)  |  +ve = Accumulation  |  −ve = Distribution",
                        "MACD (12/26/9)",
                    ),
                )

                # Row 1 — Candlestick + overlays
                fig.add_trace(go.Candlestick(
                    x=hist.index, open=open_, high=high, low=low, close=close, name="Price",
                    increasing_line_color="#2ecc71", decreasing_line_color="#e74c3c",
                    increasing_fillcolor="#2ecc71", decreasing_fillcolor="#e74c3c",
                ), row=1, col=1)
                fig.add_trace(go.Scatter(x=hist.index, y=bb_up,  line=dict(color="rgba(100,149,237,0.5)", dash="dot", width=1), showlegend=False), row=1, col=1)
                fig.add_trace(go.Scatter(x=hist.index, y=bb_lo,  line=dict(color="rgba(100,149,237,0.5)", dash="dot", width=1), fill="tonexty", fillcolor="rgba(100,149,237,0.06)", showlegend=False), row=1, col=1)
                fig.add_trace(go.Scatter(x=hist.index, y=bb_mid, line=dict(color="rgba(100,149,237,0.35)", width=1), showlegend=False), row=1, col=1)
                fig.add_trace(go.Scatter(x=hist.index, y=ma50,  line=dict(color="orange", width=1.5), name="MA 50"), row=1, col=1)
                fig.add_trace(go.Scatter(x=hist.index, y=ma200, line=dict(color="#9b59b6", width=1.5), name="MA 200"), row=1, col=1)

                # Row 2 — Volume bars + OBV line (secondary y)
                vol_colors = ["#2ecc71" if c >= o else "#e74c3c" for c, o in zip(close, open_)]
                fig.add_trace(go.Bar(x=hist.index, y=vol, marker_color=vol_colors, opacity=0.5,
                                     name="Volume", showlegend=False), row=2, col=1)
                fig.add_trace(go.Scatter(x=hist.index, y=obv_vals, line=dict(color="#f39c12", width=1.5),
                                         name="OBV", yaxis="y7"), row=2, col=1)

                # Row 3 — RSI
                fig.add_trace(go.Scatter(x=hist.index, y=rsi_vals, line=dict(color="#9b59b6", width=2), name="RSI"), row=3, col=1)
                fig.add_hline(y=70, line_dash="dash", line_color="#e74c3c", row=3, col=1)
                fig.add_hline(y=30, line_dash="dash", line_color="#2ecc71", row=3, col=1)
                fig.add_hrect(y0=70, y1=100, fillcolor="red",   opacity=0.05, row=3, col=1)
                fig.add_hrect(y0=0,  y1=30,  fillcolor="green", opacity=0.05, row=3, col=1)

                # Row 4 — MFI
                mfi_colors = ["#e74c3c" if v > 80 else ("#2ecc71" if v < 20 else "#3498db") for v in mfi_vals.fillna(50)]
                fig.add_trace(go.Scatter(x=hist.index, y=mfi_vals, line=dict(color="#3498db", width=2),
                                         name="MFI", fill="tozeroy", fillcolor="rgba(52,152,219,0.08)"), row=4, col=1)
                fig.add_hline(y=80, line_dash="dash", line_color="#e74c3c", row=4, col=1)
                fig.add_hline(y=20, line_dash="dash", line_color="#2ecc71", row=4, col=1)
                fig.add_hrect(y0=80, y1=100, fillcolor="red",   opacity=0.05, row=4, col=1)
                fig.add_hrect(y0=0,  y1=20,  fillcolor="green", opacity=0.05, row=4, col=1)

                # Row 5 — CMF
                cmf_colors = ["#2ecc71" if v >= 0 else "#e74c3c" for v in cmf_vals.fillna(0)]
                fig.add_trace(go.Bar(x=hist.index, y=cmf_vals, marker_color=cmf_colors, opacity=0.7,
                                     name="CMF", showlegend=False), row=5, col=1)
                fig.add_hline(y=0,    line_color="white",   line_width=0.8, row=5, col=1)
                fig.add_hline(y=0.05, line_dash="dot", line_color="#2ecc71", row=5, col=1)
                fig.add_hline(y=-0.05,line_dash="dot", line_color="#e74c3c", row=5, col=1)

                # Row 6 — MACD
                hist_colors = ["#2ecc71" if v >= 0 else "#e74c3c" for v in macd_hist.fillna(0)]
                fig.add_trace(go.Bar(x=hist.index, y=macd_hist, marker_color=hist_colors, opacity=0.7,
                                     showlegend=False), row=6, col=1)
                fig.add_trace(go.Scatter(x=hist.index, y=macd_l,   line=dict(color="#3498db", width=1.5), name="MACD"), row=6, col=1)
                fig.add_trace(go.Scatter(x=hist.index, y=macd_sig, line=dict(color="#e74c3c", width=1.5), name="Signal"), row=6, col=1)
                fig.add_hline(y=0, line_color="gray", line_width=0.8, row=6, col=1)

                fig.update_layout(
                    height=980, xaxis_rangeslider_visible=False,
                    legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0),
                    margin=dict(t=40, b=10, l=0, r=0),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                )
                for i in range(1, 7):
                    fig.update_yaxes(gridcolor="rgba(128,128,128,0.15)", row=i, col=1)
                    fig.update_xaxes(gridcolor="rgba(128,128,128,0.15)", row=i, col=1)
                st.plotly_chart(fig, use_container_width=True)

                # ── Signal summary ───────────────────────────────────────
                st.markdown("#### Flow Signal Summary")
                sig_cols = st.columns(4)
                cur_rsi = float(rsi_vals.iloc[-1])
                cur_mfi = float(mfi_vals.iloc[-1]) if not pd.isna(mfi_vals.iloc[-1]) else 50
                cur_cmf = float(cmf_vals.iloc[-1]) if not pd.isna(cmf_vals.iloc[-1]) else 0
                obv_trend = "Rising ↑" if float(obv_vals.iloc[-1]) > float(obv_vals.iloc[-5]) else "Falling ↓"
                sig_cols[0].metric("RSI", f"{cur_rsi:.1f}", "Overbought" if cur_rsi>70 else ("Oversold" if cur_rsi<30 else "Neutral"))
                sig_cols[1].metric("MFI (Volume RSI)", f"{cur_mfi:.1f}", "Sell pressure" if cur_mfi>80 else ("Buy pressure" if cur_mfi<20 else "Neutral"))
                sig_cols[2].metric("CMF (Smart Money)", f"{cur_cmf:.3f}", "Accumulating ✅" if cur_cmf>0.05 else ("Distributing ⚠️" if cur_cmf<-0.05 else "Neutral"))
                sig_cols[3].metric("OBV Trend", obv_trend, "Confirms price ✅" if (obv_trend=="Rising ↑" and chg_pct>0) or (obv_trend=="Falling ↓" and chg_pct<0) else "Divergence ⚠️")

                st.divider()
                st.markdown("#### Fundamentals")
                fa, fb = st.columns(2)
                with fa:
                    left = {
                        "EPS Growth (YoY)":  f"{info['earningsGrowth']*100:.1f}%"   if info.get("earningsGrowth")   else "—",
                        "Revenue Growth":    f"{info['revenueGrowth']*100:.1f}%"    if info.get("revenueGrowth")    else "—",
                        "Gross Margin":      f"{info['grossMargins']*100:.1f}%"     if info.get("grossMargins")     else "—",
                        "Operating Margin":  f"{info['operatingMargins']*100:.1f}%" if info.get("operatingMargins") else "—",
                        "Net Margin":        f"{info['profitMargins']*100:.1f}%"    if info.get("profitMargins")    else "—",
                        "Debt / Equity":     f"{info.get('debtToEquity','—')}",
                    }
                    st.table(pd.DataFrame.from_dict(left, orient="index", columns=["Value"]))
                with fb:
                    right = {
                        "Return on Equity": f"{info['returnOnEquity']*100:.1f}%"  if info.get("returnOnEquity")  else "—",
                        "Return on Assets": f"{info['returnOnAssets']*100:.1f}%"  if info.get("returnOnAssets")  else "—",
                        "Free Cash Flow":   f"${info['freeCashflow']/1e9:.2f}B"   if info.get("freeCashflow")    else "—",
                        "Current Ratio":    f"{info.get('currentRatio','—')}",
                        "Analyst Target":   f"${info.get('targetMeanPrice','—')}",
                        "Dividend Yield":   f"{info['dividendYield']*100:.2f}%"   if info.get("dividendYield")   else "—",
                    }
                    st.table(pd.DataFrame.from_dict(right, orient="index", columns=["Value"]))

                try:
                    eq = yf.Ticker(ticker_in).quarterly_earnings
                    if eq is not None and not eq.empty:
                        st.markdown("#### Quarterly EPS — Actual vs Estimate")
                        eq = eq.tail(8)
                        fig_eq = go.Figure()
                        fig_eq.add_trace(go.Bar(x=eq.index.astype(str), y=eq["Actual"],
                                                name="Actual EPS", marker_color="#3498db"))
                        if "Estimate" in eq.columns:
                            fig_eq.add_trace(go.Scatter(x=eq.index.astype(str), y=eq["Estimate"],
                                                        name="Estimate", mode="markers+lines",
                                                        marker=dict(color="orange", size=9),
                                                        line=dict(color="orange", dash="dot")))
                        fig_eq.update_layout(height=280, margin=dict(t=10, b=10),
                                             paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                             yaxis=dict(gridcolor="rgba(128,128,128,0.15)"),
                                             legend=dict(orientation="h"))
                        st.plotly_chart(fig_eq, use_container_width=True)
                except Exception:
                    pass

                # ── Institutional Holders ────────────────────────────────
                st.divider()
                st.markdown("#### Institutional Holders *(13F filings — quarterly, ~45 day delay)*")
                ic1, ic2 = st.columns(2)
                try:
                    t_obj = yf.Ticker(ticker_in)
                    mh = t_obj.major_holders
                    ih = t_obj.institutional_holders
                    with ic1:
                        st.markdown("**Ownership Breakdown**")
                        if mh is not None and not mh.empty:
                            mh.columns = ["Value", "Description"]
                            st.dataframe(mh[["Description","Value"]], use_container_width=True, hide_index=True)
                    with ic2:
                        st.markdown("**Top Institutional Holders**")
                        if ih is not None and not ih.empty:
                            ih_disp = ih.copy()
                            if "Date Reported" in ih_disp.columns:
                                ih_disp["Date Reported"] = pd.to_datetime(ih_disp["Date Reported"]).dt.strftime("%Y-%m-%d")
                            if "Value" in ih_disp.columns:
                                ih_disp["Value ($B)"] = (ih_disp["Value"] / 1e9).round(2)
                                ih_disp = ih_disp.drop(columns=["Value"])
                            if "pctHeld" in ih_disp.columns:
                                ih_disp["% Held"] = (ih_disp["pctHeld"] * 100).round(2)
                                ih_disp = ih_disp.drop(columns=["pctHeld"])
                            st.dataframe(ih_disp, use_container_width=True, hide_index=True)
                except Exception:
                    st.info("Institutional data unavailable for this ticker.")

    # ── TAB 4: EARNINGS CALENDAR ─────────────────────────────────
    with tab4:
        st.markdown("#### Upcoming Earnings Calendar")
        with st.spinner("Loading earnings data…"):
            df_cal = fetch_earnings_calendar()

        if not df_cal.empty:
            today = pd.Timestamp.now().normalize()
            df_fut = df_cal[df_cal["Date"] >= today].sort_values("Date").copy()
            df_fut["Days Away"] = (df_fut["Date"] - today).dt.days
            df_fut["Date"] = df_fut["Date"].dt.strftime("%Y-%m-%d")
            st.dataframe(df_fut[["Ticker", "Date", "Days Away", "EPS Est", "Rev Est ($B)"]],
                         use_container_width=True, height=420)
            if not df_fut.empty:
                st.markdown("#### Earnings Timeline")
                fig_tl = go.Figure()
                fig_tl.add_trace(go.Scatter(
                    x=df_fut["Date"], y=df_fut["Ticker"],
                    mode="markers+text",
                    marker=dict(size=14, symbol="diamond",
                                color=df_fut["Days Away"],
                                colorscale=["#e74c3c", "#f39c12", "#2ecc71"],
                                colorbar=dict(title="Days Away"), showscale=True),
                    text=df_fut["Ticker"], textposition="middle right",
                ))
                fig_tl.update_layout(
                    height=max(300, len(df_fut) * 28),
                    margin=dict(t=10, b=10, l=0, r=80),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    xaxis=dict(gridcolor="rgba(128,128,128,0.15)"),
                    yaxis=dict(gridcolor="rgba(128,128,128,0.15)"),
                    showlegend=False,
                )
                st.plotly_chart(fig_tl, use_container_width=True)
        else:
            st.info("No upcoming earnings data found.")

    # ── TAB 5: INTELLIGENCE FEED ──────────────────────────────────
    with tab5:
        DEEPSTACK_DB = r"C:\deepstack\data\knowledge_graph.duckdb"
        DEEPSTACK_SOCIAL = r"C:\deepstack\agent\tools\social.py"

        @st.cache_data(ttl=300)
        def _load_feed():
            import sys, importlib, duckdb as _ddb
            from pathlib import Path
            if not Path(DEEPSTACK_DB).exists():
                return None
            con = _ddb.connect(DEEPSTACK_DB, read_only=True)

            # Social pulls
            try:
                social = con.execute("""
                    SELECT source, author, subreddit, url, content, tickers,
                           relevance, pulled_at, status
                    FROM social_pulls
                    ORDER BY relevance DESC, pulled_at DESC
                    LIMIT 100
                """).fetchdf()
            except Exception:
                social = pd.DataFrame()

            # Signal queue
            try:
                signals = con.execute("""
                    SELECT signal_type, hypothesis, final_score, status,
                           tickers, created_at
                    FROM signals
                    ORDER BY final_score DESC
                    LIMIT 30
                """).fetchdf()
            except Exception:
                signals = pd.DataFrame()

            # Agent log
            try:
                agent_log = con.execute("""
                    SELECT ts, action, entity, detail, model_tier
                    FROM agent_log
                    ORDER BY ts DESC
                    LIMIT 50
                """).fetchdf()
            except Exception:
                agent_log = pd.DataFrame()

            # Cycle cost
            try:
                cost = con.execute("""
                    SELECT SUM(cost_usd) as total_usd,
                           SUM(api_calls) as total_calls,
                           MAX(cycle_ts) as last_run
                    FROM cycle_cost_log
                """).fetchone()
            except Exception:
                cost = None

            # Ingest status
            try:
                ingest = con.execute("""
                    SELECT source_key, last_ingested, item_count
                    FROM ingest_status
                    ORDER BY last_ingested DESC
                    LIMIT 20
                """).fetchdf()
            except Exception:
                ingest = pd.DataFrame()

            con.close()
            return {
                "social": social,
                "signals": signals,
                "agent_log": agent_log,
                "cost": cost,
                "ingest": ingest,
            }

        feed = _load_feed()

        if feed is None:
            st.info("DeepStack pipeline not initialised. Run the pipeline once to populate the feed.")
            st.code("cd C:\\deepstack && python run.py --cached --no-news --no-transcripts")
        else:
            social_df  = feed["social"]
            signals_df = feed["signals"]
            log_df     = feed["agent_log"]
            cost_row   = feed["cost"]
            ingest_df  = feed["ingest"]

            # ── Stats bar ──────────────────────────────────────────
            s1, s2, s3, s4, s5 = st.columns(5)
            reddit_n = len(social_df[social_df["source"] == "reddit"]) if not social_df.empty else 0
            x_n      = len(social_df[social_df["source"] == "x"])      if not social_df.empty else 0
            sig_n    = len(signals_df[signals_df["status"] == "queued"]) if not signals_df.empty else 0
            total_cost = round(cost_row[0] or 0, 4) if cost_row else 0
            last_run   = str(cost_row[2])[:16] if cost_row and cost_row[2] else "—"

            s1.metric("Reddit Pulls", reddit_n)
            s2.metric("X Pulls", x_n, help="Requires TWITTER_BEARER_TOKEN")
            s3.metric("Signals Queued", sig_n)
            s4.metric("Pipeline Cost", f"${total_cost}")
            s5.metric("Last Run", last_run)

            st.divider()

            # ── Row 1: Social + Signal Queue ───────────────────────
            col_r, col_x, col_sig = st.columns([2, 2, 2])

            with col_r:
                st.markdown("##### 🔴 Reddit Signals")
                if not social_df.empty:
                    rdf = social_df[social_df["source"] == "reddit"]
                    if not rdf.empty:
                        for _, row in rdf.head(8).iterrows():
                            relevance_bar = "█" * int(row["relevance"] * 10)
                            tickers_str = ", ".join(json.loads(row["tickers"] or "[]"))
                            with st.expander(f"{row['content'][:80]}…" if len(str(row['content'])) > 80 else str(row['content'])):
                                st.caption(f"r/{row['subreddit']} · u/{row['author']}")
                                if tickers_str:
                                    st.caption(f"Tickers: `{tickers_str}`")
                                st.caption(f"Relevance: {relevance_bar} {row['relevance']:.0%}")
                                if row["url"]:
                                    st.markdown(f"[Open in Reddit]({row['url']})")
                    else:
                        st.caption("No Reddit pulls yet. Run social ingest.")
                        st.code("cd C:\\deepstack && python -c \"from agent.tools.social import run_social_ingest; print(run_social_ingest())\"")
                else:
                    st.caption("No social data yet.")

            with col_x:
                st.markdown("##### 🐦 X Timeline")
                if not social_df.empty:
                    xdf = social_df[social_df["source"] == "x"]
                    if not xdf.empty:
                        for _, row in xdf.head(8).iterrows():
                            tickers_str = ", ".join(json.loads(row["tickers"] or "[]"))
                            with st.expander(f"{row['content'][:80]}…" if len(str(row['content'])) > 80 else str(row['content'])):
                                st.caption(f"@{row['author']}")
                                if tickers_str:
                                    st.caption(f"Tickers: `{tickers_str}`")
                                if row["url"]:
                                    st.markdown(f"[Open on X]({row['url']})")
                    else:
                        st.caption("X reader not yet configured.")
                        st.markdown("Add `TWITTER_BEARER_TOKEN` to `.env` to enable.")
                else:
                    st.caption("No X data yet.")

            with col_sig:
                st.markdown("##### 🎯 Signal Queue")
                if not signals_df.empty:
                    queued = signals_df[signals_df["status"] == "queued"]
                    if not queued.empty:
                        for _, row in queued.head(8).iterrows():
                            score = float(row["final_score"]) if row["final_score"] else 0
                            badge = "🟢" if score >= 0.8 else "🟡" if score >= 0.6 else "🔴"
                            with st.expander(f"{badge} [{score:.2f}] {str(row['hypothesis'])[:70]}"):
                                st.caption(f"Type: {row['signal_type']}")
                                tickers_str = str(row.get("tickers", "")).replace("[", "").replace("]", "").replace('"', "")
                                if tickers_str:
                                    st.caption(f"Tickers: `{tickers_str}`")
                    else:
                        st.caption("No signals queued.")
                else:
                    st.caption("Signal queue empty.")

            st.divider()

            # ── Row 2: Ingest Status + Agent Log ──────────────────
            col_ing, col_log = st.columns([1, 1])

            with col_ing:
                st.markdown("##### 📡 Ingest Status")
                if not ingest_df.empty:
                    ingest_df["last_ingested"] = pd.to_datetime(
                        ingest_df["last_ingested"], errors="coerce"
                    ).dt.strftime("%m-%d %H:%M")
                    st.dataframe(
                        ingest_df.rename(columns={
                            "source_key": "Source",
                            "last_ingested": "Last Pull",
                            "item_count": "Items",
                        }),
                        use_container_width=True,
                        hide_index=True,
                        height=300,
                    )
                else:
                    st.caption("No ingest records yet.")

            with col_log:
                st.markdown("##### 🤖 Agent Activity")
                if not log_df.empty:
                    log_df["ts"] = pd.to_datetime(log_df["ts"], errors="coerce").dt.strftime("%m-%d %H:%M")
                    st.dataframe(
                        log_df[["ts", "action", "entity", "model_tier"]].rename(columns={
                            "ts": "Time", "action": "Action",
                            "entity": "Entity", "model_tier": "Model",
                        }),
                        use_container_width=True,
                        hide_index=True,
                        height=300,
                    )
                else:
                    st.caption("No agent activity yet.")

            # ── Refresh button ─────────────────────────────────────
            st.divider()
            rc1, rc2 = st.columns([1, 5])
            if rc1.button("🔄 Refresh Feed", use_container_width=True):
                st.cache_data.clear()
                st.rerun()
            rc2.caption("Feed updates every 5 min. Reddit ingest runs automatically with the pipeline.")

# ════════════════════════════════════════════════════════════════
# RIGHT — AI CHAT PANEL (narrow, always visible)
# ════════════════════════════════════════════════════════════════
with chat_col:
    st.markdown('<div class="chat-panel">', unsafe_allow_html=True)

    # Header row: title + expand/collapse toggle
    h1, h2 = st.columns([3, 1])
    h1.markdown("**🤖 AI Analyst**")
    expand_label = "◀ Less" if st.session_state.chat_expanded else "More ▶"
    if h2.button(expand_label, key="expand_chat", use_container_width=True):
        st.session_state.chat_expanded = not st.session_state.chat_expanded
        st.rerun()

    if not ai_client:
        st.warning("Add ANTHROPIC_API_KEY to .env")
    else:
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

        st.divider()

        # Scrollable message history
        msg_box = st.container(height=520)
        with msg_box:
            for msg in st.session_state.chat_history:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

        # Input + quick trigger
        user_input = st.chat_input("Ask about any stock or sector…")
        quick = st.session_state.pop("quick", None)
        user_input = user_input or quick

        if user_input:
            st.session_state.chat_history.append({"role": "user", "content": user_input})
            with msg_box:
                with st.chat_message("user"):
                    st.markdown(user_input)

            context = build_market_context()
            system_with_data = f"{SYSTEM_PROMPT}\n\n---\nLIVE SNAPSHOT:\n{context}\n---"
            api_messages = [{"role": m["role"], "content": m["content"]}
                            for m in st.session_state.chat_history]

            with msg_box:
                with st.chat_message("assistant"):
                    status = st.empty()

                    # Tool-use agent loop (max 4 tool calls)
                    for _ in range(4):
                        resp = ai_client.messages.create(
                            model="claude-haiku-4-5-20251001",
                            max_tokens=2048,
                            system=system_with_data,
                            messages=api_messages,
                            tools=AI_TOOLS,
                        )
                        if resp.stop_reason != "tool_use":
                            break
                        tool_results = []
                        for block in resp.content:
                            if block.type == "tool_use":
                                label = block.input.get("ticker") or block.input.get("sector") or "data"
                                status.caption(f"🔍 Fetching {label}…")
                                result = run_tool(block.name, block.input)
                                tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": result,
                                })
                        api_messages = api_messages + [
                            {"role": "assistant", "content": resp.content},
                            {"role": "user",      "content": tool_results},
                        ]

                    status.empty()

                    # Stream final answer
                    def _stream():
                        with ai_client.messages.stream(
                            model="claude-haiku-4-5-20251001",
                            max_tokens=2048,
                            system=system_with_data,
                            messages=api_messages,
                        ) as stream:
                            for text in stream.text_stream:
                                yield text
                    response = st.write_stream(_stream())

            st.session_state.chat_history.append({"role": "assistant", "content": response})

        if st.session_state.get("chat_history"):
            if st.button("🗑️ Clear", use_container_width=True):
                st.session_state.chat_history = []
                st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Controls")
    if st.button("🔄 Refresh All Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.markdown("## 👁️ Quick Watchlist")
    wl = st.text_area("Tickers (comma-separated)", value="NVDA, AAPL, MSFT, AMD, TSLA, CRWD")
    for t in [x.strip().upper() for x in wl.split(",") if x.strip()]:
        try:
            d = yf.download(t, period="2d", interval="1d", progress=False, auto_adjust=True)
            if len(d) >= 2:
                c = d["Close"].squeeze()
                p = float(c.iloc[-1])
                chg = (p / float(c.iloc[-2]) - 1) * 100
                icon = "🟢" if chg >= 0 else "🔴"
                st.markdown(f"{icon} **{t}** &nbsp; `${p:.2f}` &nbsp; `{chg:+.1f}%`",
                            unsafe_allow_html=True)
        except Exception:
            pass

    st.divider()
    st.markdown("## 🏆 Top Opportunities")
    with st.spinner(""):
        try:
            df_top = fetch_screener()
            if not df_top.empty:
                top5 = df_top.nlargest(5, "Score")[["Ticker", "Score", "RSI", "EPS Grwth%"]]
                st.dataframe(top5, use_container_width=True, hide_index=True)
        except Exception:
            pass

    st.caption("Data: Yahoo Finance · Alternative.me · Anthropic")
