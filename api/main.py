import os, json, asyncio, time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from cachetools import TTLCache
from dotenv import load_dotenv
from anthropic import Anthropic
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

# ── In-memory TTL cache (key → (timestamp, value)) ──────────────────────────
_cache: TTLCache = TTLCache(maxsize=256, ttl=300)   # 5-min default
_cache_long: TTLCache = TTLCache(maxsize=64, ttl=900)  # 15-min for screener
_executor = ThreadPoolExecutor(max_workers=12)

def _cached(cache, key, fn):
    if key in cache:
        return cache[key]
    val = fn()
    cache[key] = val
    return val
from sse_starlette.sse import EventSourceResponse

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

app = FastAPI(title="Market Intelligence API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ai_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

# ── Indicators ───────────────────────────────────────────────────────────────

def _rsi(s: pd.Series, p=14):
    d = s.diff(); g = d.clip(lower=0); l = -d.clip(upper=0)
    ag = g.ewm(alpha=1/p, min_periods=p).mean()
    al = l.ewm(alpha=1/p, min_periods=p).mean()
    return 100 - (100 / (1 + ag / al.replace(0, np.nan)))

def _macd(s: pd.Series, fast=12, slow=26, sig=9):
    f = s.ewm(span=fast, adjust=False).mean()
    sl = s.ewm(span=slow, adjust=False).mean()
    line = f - sl; signal = line.ewm(span=sig, adjust=False).mean()
    return line, signal, line - signal

def _bollinger(s: pd.Series, p=20, m=2):
    mid = s.rolling(p).mean(); std = s.rolling(p).std()
    return mid + m*std, mid, mid - m*std

def _obv(c: pd.Series, v: pd.Series):
    return (np.sign(c.diff()).fillna(0) * v).cumsum()

def _cmf(h, l, c, v, p=20):
    hl = (h - l).replace(0, np.nan)
    mfv = ((c - l) - (h - c)) / hl * v
    return mfv.rolling(p).sum() / v.rolling(p).sum()

def _mfi(h, l, c, v, p=14):
    tp = (h + l + c) / 3; rmf = tp * v
    pos = rmf.where(tp > tp.shift(1), 0)
    neg = rmf.where(tp < tp.shift(1), 0)
    r = pos.rolling(p).sum() / neg.rolling(p).sum().replace(0, np.nan)
    return 100 - (100 / (1 + r))

# ── Shared sector / screener data ────────────────────────────────────────────

SECTORS = {
    "Technology":"XLK","Healthcare":"XLV","Energy":"XLE","Financials":"XLF",
    "Industrials":"XLI","Consumer Disc":"XLY","Staples":"XLP","Utilities":"XLU",
    "Materials":"XLB","Real Estate":"XLRE","Communication":"XLC","Semiconductors":"SOXX",
}
SCREENER_TICKERS = [
    "AAPL","MSFT","GOOGL","META","AMZN","NVDA","AMD","INTC","QCOM","AVGO",
    "TSM","ASML","MU","AMAT","LRCX","KLAC","TXN","MRVL","ON","ARM",
    "TSLA","NFLX","CRM","SNOW","PLTR","DDOG","ZS","CRWD","NET","PANW",
    "JPM","V","MA","UNH","XOM","CVX","LLY","ABBV",
]

def _score(pe, eps_g, rev_g, rsi_v, price, ma50):
    s = 0
    if pe and 0 < pe < 45: s += 1
    if eps_g and eps_g > 0.10: s += 2
    if rev_g and rev_g > 0.10: s += 1
    if 40 < rsi_v < 60: s += 1
    if price > ma50: s += 1
    return s

# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/api/fear-greed")
def fear_greed():
    try:
        d = yf.download("SMH", period="3mo", interval="1d", progress=False, auto_adjust=True)
        c = d["Close"].squeeze()
        score = round(float(_rsi(c).iloc[-1]))
        if score >= 75:   rating = "Extreme Greed"
        elif score >= 60: rating = "Greed"
        elif score >= 40: rating = "Neutral"
        elif score >= 25: rating = "Fear"
        else:             rating = "Extreme Fear"
        return {"score": score, "rating": rating}
    except Exception:
        return {"score": None, "rating": None}

@app.get("/api/macro")
def macro():
    tickers = {
        "S&P 500":"^GSPC","Nasdaq":"^IXIC","Dow Jones":"^DJI",
        "10Y Yield":"^TNX","Gold":"GC=F","Oil (WTI)":"CL=F","VIX":"^VIX",
    }
    rows = []
    for name, t in tickers.items():
        try:
            d = yf.download(t, period="5d", interval="1d", progress=False, auto_adjust=True)
            if len(d) >= 2:
                c = d["Close"].squeeze()
                chg = float((c.iloc[-1]/c.iloc[-2]-1)*100)
                rows.append({"name":name,"value":round(float(c.iloc[-1]),2),"change":round(chg,2)})
        except Exception:
            pass
    return rows

@app.get("/api/sectors")
def sectors():
    rows = []
    for name, ticker in SECTORS.items():
        try:
            d = yf.download(ticker, period="3mo", interval="1d", progress=False, auto_adjust=True)
            if len(d) < 20: continue
            c = d["Close"].squeeze()
            r = float(_rsi(c).iloc[-1])
            rows.append({
                "sector": name, "ticker": ticker,
                "price": round(float(c.iloc[-1]),2),
                "rsi": round(r,1),
                "change1w": round(float((c.iloc[-1]/c.iloc[-5]-1)*100),2) if len(c)>=5 else 0,
                "change1m": round(float((c.iloc[-1]/c.iloc[-21]-1)*100),2) if len(c)>=21 else 0,
                "signal": "overbought" if r>70 else ("oversold" if r<30 else "neutral"),
            })
        except Exception:
            pass
    return rows

@app.get("/api/screener")
def screener():
    rows = []
    for ticker in SCREENER_TICKERS:
        try:
            info = yf.Ticker(ticker).info
            d = yf.download(ticker, period="3mo", interval="1d", progress=False, auto_adjust=True)
            if len(d) < 20: continue
            c = d["Close"].squeeze()
            r = float(_rsi(c).iloc[-1])
            price = float(c.iloc[-1])
            ma50 = float(c.rolling(50).mean().iloc[-1])
            ret1m = float((c.iloc[-1]/c.iloc[-21]-1)*100) if len(c)>=21 else 0
            pe = info.get("trailingPE"); fwd_pe = info.get("forwardPE")
            eps_g = info.get("earningsGrowth"); rev_g = info.get("revenueGrowth")
            gm = info.get("grossMargins"); mcap = info.get("marketCap",0)
            rows.append({
                "ticker": ticker, "sector": info.get("sector","N/A"),
                "price": round(price,2), "rsi": round(r,1),
                "pe": round(pe,1) if pe else None,
                "fwdPe": round(fwd_pe,1) if fwd_pe else None,
                "epsGrowth": round(eps_g*100,1) if eps_g else None,
                "revGrowth": round(rev_g*100,1) if rev_g else None,
                "grossMargin": round(gm*100,1) if gm else None,
                "change1m": round(ret1m,2),
                "aboveMa50": price > ma50,
                "score": _score(pe, eps_g, rev_g, r, price, ma50),
                "marketCap": mcap,
            })
        except Exception:
            pass
    return rows

@app.get("/api/stock/{ticker}")
def stock(ticker: str, period: str = "6mo"):
    ticker = ticker.upper()
    hist = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=True)
    info = yf.Ticker(ticker).info
    if hist.empty:
        return {"error": f"No data for {ticker}"}

    c = hist["Close"].squeeze().astype(float)
    o = hist["Open"].squeeze().astype(float)
    h = hist["High"].squeeze().astype(float)
    l = hist["Low"].squeeze().astype(float)
    v = hist["Volume"].squeeze().astype(float)

    rsi_s = _rsi(c); macd_l, macd_sig, macd_hist = _macd(c)
    bb_up, bb_mid, bb_lo = _bollinger(c)
    ma50 = c.rolling(50).mean(); ma200 = c.rolling(200).mean()
    obv_s = _obv(c, v); cmf_s = _cmf(h,l,c,v); mfi_s = _mfi(h,l,c,v)

    def ts(s): return [{"t": str(i.date()), "v": round(float(x),4) if not pd.isna(x) else None}
                       for i,x in s.items()]

    candles = [{"t": str(i.date()), "o": round(float(o_),2), "h": round(float(h_),2),
                "l": round(float(l_),2), "c": round(float(c_),2), "v": int(v_)}
               for i, o_, h_, l_, c_, v_ in zip(hist.index, o, h, l, c, v)]

    price = float(c.iloc[-1]); prev = float(c.iloc[-2])
    return {
        "ticker": ticker,
        "price": round(price,2),
        "change": round((price/prev-1)*100, 2),
        "info": {
            "marketCap": info.get("marketCap"),
            "trailingPE": info.get("trailingPE"),
            "forwardPE": info.get("forwardPE"),
            "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
            "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow"),
            "beta": info.get("beta"),
            "earningsGrowth": info.get("earningsGrowth"),
            "revenueGrowth": info.get("revenueGrowth"),
            "grossMargins": info.get("grossMargins"),
            "operatingMargins": info.get("operatingMargins"),
            "profitMargins": info.get("profitMargins"),
            "returnOnEquity": info.get("returnOnEquity"),
            "returnOnAssets": info.get("returnOnAssets"),
            "freeCashflow": info.get("freeCashflow"),
            "debtToEquity": info.get("debtToEquity"),
            "currentRatio": info.get("currentRatio"),
            "targetMeanPrice": info.get("targetMeanPrice"),
            "dividendYield": info.get("dividendYield"),
            "sector": info.get("sector"),
            "longName": info.get("longName"),
        },
        "candles": candles,
        "indicators": {
            "rsi": ts(rsi_s), "macd": ts(macd_l), "macdSignal": ts(macd_sig),
            "macdHist": ts(macd_hist), "bbUpper": ts(bb_up), "bbMid": ts(bb_mid),
            "bbLower": ts(bb_lo), "ma50": ts(ma50), "ma200": ts(ma200),
            "obv": ts(obv_s), "cmf": ts(cmf_s), "mfi": ts(mfi_s),
        },
    }

@app.get("/api/institutional/{ticker}")
def institutional(ticker: str):
    t = yf.Ticker(ticker.upper())
    result = {}
    try:
        mh = t.major_holders
        if mh is not None and not mh.empty:
            mh.columns = ["value","description"]
            result["majorHolders"] = mh.to_dict("records")
    except Exception:
        pass
    try:
        ih = t.institutional_holders
        if ih is not None and not ih.empty:
            ih = ih.copy()
            if "Date Reported" in ih.columns:
                ih["Date Reported"] = pd.to_datetime(ih["Date Reported"]).dt.strftime("%Y-%m-%d")
            result["institutionalHolders"] = ih.head(15).fillna("").to_dict("records")
    except Exception:
        pass
    return result

@app.get("/api/earnings")
def earnings():
    watch = ["AAPL","MSFT","GOOGL","META","AMZN","NVDA","AMD","TSLA",
             "NFLX","CRM","SNOW","PLTR","DDOG","CRWD","NET","MU","AVGO",
             "QCOM","TSM","PANW","ZS","INTC","ARM","ON"]
    rows = []
    today = pd.Timestamp.now().normalize()
    for ticker in watch:
        try:
            cal = yf.Ticker(ticker).calendar
            if cal is None: continue
            dates = cal.get("Earnings Date", [])
            if dates:
                dt = pd.to_datetime(dates[0])
                if dt >= today:
                    rows.append({
                        "ticker": ticker,
                        "date": dt.strftime("%Y-%m-%d"),
                        "daysAway": int((dt - today).days),
                        "epsEst": cal.get("EPS Estimate"),
                        "revEst": round(cal.get("Revenue Estimate",0)/1e9,2) if cal.get("Revenue Estimate") else None,
                    })
        except Exception:
            pass
    return sorted(rows, key=lambda x: x["daysAway"])

# ── AI Chat with streaming + tool use ────────────────────────────────────────

AI_TOOLS = [
    {"name":"get_stock_analysis","description":"Fetch live technical and fundamental data for any stock ticker.",
     "input_schema":{"type":"object","properties":{"ticker":{"type":"string"}},"required":["ticker"]}},
    {"name":"get_flow_and_institutional","description":"Fetch volume flow (OBV, CMF, MFI) and institutional holders for a stock.",
     "input_schema":{"type":"object","properties":{"ticker":{"type":"string"}},"required":["ticker"]}},
    {"name":"get_sector_stocks","description":"Rank stocks in a sector by opportunity score.",
     "input_schema":{"type":"object","properties":{"sector":{"type":"string"},"top_n":{"type":"integer"}},"required":["sector"]}},
]

SECTOR_TICKER_MAP = {
    "Healthcare":["JNJ","UNH","LLY","ABBV","MRK","TMO","ABT","DHR","BMY","AMGN","GILD","VRTX","REGN","ISRG","CVS"],
    "Technology":["AAPL","MSFT","NVDA","AMD","GOOGL","META","AVGO","QCOM","INTC","TXN","AMAT","LRCX","KLAC","NOW","ADBE"],
    "Semiconductors":["NVDA","AMD","INTC","QCOM","AVGO","TSM","ASML","MU","AMAT","LRCX","KLAC","TXN","MRVL","ON","ARM"],
    "Energy":["XOM","CVX","COP","EOG","SLB","MPC","VLO","PSX","OXY","PXD"],
    "Financials":["JPM","BAC","WFC","GS","MS","C","BLK","V","MA","AXP"],
    "Industrials":["CAT","DE","HON","UPS","FDX","RTX","LMT","NOC","BA","GE"],
    "Consumer Discretionary":["AMZN","TSLA","HD","NKE","SBUX","MCD","TGT","LOW","BKNG","CMG"],
    "Consumer Staples":["WMT","PG","KO","PEP","COST","PM","MO","MDLZ","CL","GIS"],
    "Communication":["GOOGL","META","NFLX","DIS","CMCSA","T","VZ","TMUS","SNAP","EA"],
    "Real Estate":["AMT","PLD","CCI","EQIX","PSA","O","DLR","SPG","WELL","AVB"],
    "Utilities":["NEE","DUK","SO","D","AEP","EXC","SRE","XEL","WEC","ES"],
    "Materials":["LIN","APD","SHW","ECL","NEM","FCX","NUE","VMC","MLM","DOW"],
}

def _run_tool(name, inputs):
    try:
        if name == "get_stock_analysis":
            t = inputs["ticker"].upper()
            d = yf.download(t, period="3mo", interval="1d", progress=False, auto_adjust=True)
            info = yf.Ticker(t).info
            c = d["Close"].squeeze().astype(float)
            price = float(c.iloc[-1]); r = float(_rsi(c).iloc[-1])
            ml,ms,_ = _macd(c); bu,_,bl = _bollinger(c)
            ma50v = float(c.rolling(50).mean().iloc[-1])
            ret1m = float((c.iloc[-1]/c.iloc[-21]-1)*100) if len(c)>=21 else 0
            msig = ("Bullish crossover" if float(ml.iloc[-1])>float(ms.iloc[-1]) and float(ml.iloc[-2])<=float(ms.iloc[-2]) else
                    "Bearish crossover" if float(ml.iloc[-1])<float(ms.iloc[-1]) and float(ml.iloc[-2])>=float(ms.iloc[-2]) else
                    "Above signal" if float(ml.iloc[-1])>float(ms.iloc[-1]) else "Below signal")
            bb = ("above upper band" if price>float(bu.iloc[-1]) else "below lower band" if price<float(bl.iloc[-1]) else "within bands")
            lines = [f"{t} | ${price:.2f} | RSI {r:.1f} | 1M {ret1m:+.1f}%",
                     f"  MACD: {msig} | BB: {bb} | vs MA50: {'above' if price>ma50v else 'below'}"]
            for k,lbl in [("trailingPE","P/E"),("forwardPE","Fwd P/E"),("earningsGrowth","EPS Growth"),
                          ("revenueGrowth","Rev Growth"),("grossMargins","Gross Margin"),("targetMeanPrice","Target")]:
                v = info.get(k)
                if v: lines.append(f"  {lbl}: {v*100:.1f}%" if k in ("earningsGrowth","revenueGrowth","grossMargins") else f"  {lbl}: {round(v,2)}")
            return "\n".join(lines)

        if name == "get_flow_and_institutional":
            t = inputs["ticker"].upper()
            d = yf.download(t, period="3mo", interval="1d", progress=False, auto_adjust=True)
            c=d["Close"].squeeze().astype(float); h=d["High"].squeeze().astype(float)
            l=d["Low"].squeeze().astype(float); v=d["Volume"].squeeze().astype(float)
            cur_cmf = float(_cmf(h,l,c,v).iloc[-1])
            cur_mfi = float(_mfi(h,l,c,v).iloc[-1])
            obv_s = _obv(c,v); obv_chg = float(obv_s.iloc[-1])-float(obv_s.iloc[-5])
            vol_ratio = float(v.iloc[-1])/float(v.rolling(20).mean().iloc[-1])
            lines = [f"FLOW: {t}",
                     f"  CMF: {cur_cmf:.3f} → {'Accumulation' if cur_cmf>0.05 else ('Distribution' if cur_cmf<-0.05 else 'Neutral')}",
                     f"  MFI: {cur_mfi:.1f} → {'Overbought' if cur_mfi>80 else ('Oversold/Buy pressure' if cur_mfi<20 else 'Neutral')}",
                     f"  OBV 5d: {'+' if obv_chg>=0 else ''}{obv_chg:,.0f}",
                     f"  Volume vs avg: {vol_ratio:.1f}x"]
            try:
                ih = yf.Ticker(t).institutional_holders
                if ih is not None and not ih.empty:
                    lines.append("TOP INSTITUTIONS:")
                    for _,row in ih.head(8).iterrows():
                        lines.append(f"  {row.get('Holder','?')}: {row.get('Shares',0):,.0f} ({row.get('pctHeld',0)*100:.2f}%)")
            except Exception: pass
            return "\n".join(lines)

        if name == "get_sector_stocks":
            sector = inputs.get("sector",""); top_n = inputs.get("top_n",8)
            tickers = next((v for k,v in SECTOR_TICKER_MAP.items() if sector.lower() in k.lower() or k.lower() in sector.lower()), None)
            if not tickers: return f"Unknown sector '{sector}'"
            results = []
            for tk in tickers:
                try:
                    d = yf.download(tk, period="3mo", interval="1d", progress=False, auto_adjust=True)
                    info = yf.Ticker(tk).info
                    c = d["Close"].squeeze().astype(float)
                    r = float(_rsi(c).iloc[-1]); price = float(c.iloc[-1])
                    ma50 = float(c.rolling(50).mean().iloc[-1])
                    eps_g = info.get("earningsGrowth"); rev_g = info.get("revenueGrowth")
                    pe = info.get("trailingPE")
                    sc = _score(pe, eps_g, rev_g, r, price, ma50)
                    results.append({"t":tk,"score":sc,"rsi":round(r,1),"price":round(price,2),
                                    "eps":f"{eps_g*100:.1f}%" if eps_g else "—","pe":f"{pe:.1f}" if pe else "—"})
                except Exception: pass
            results.sort(key=lambda x: x["score"], reverse=True)
            lines = [f"TOP {sector.upper()} STOCKS:"]
            for a in results[:top_n]:
                lines.append(f"  {a['t']}: Score {a['score']}/6 | RSI {a['rsi']} | P/E {a['pe']} | EPS {a['eps']}")
            return "\n".join(lines)
        return "Unknown tool."
    except Exception as e:
        return f"Tool error: {e}"

SYSTEM_PROMPT = """You are a sharp market analyst in a live trading dashboard. You have real-time data via tools.
Use tools proactively when asked about any stock, sector, or flow data not in the snapshot.
Be concise — bullet points preferred. Ground all recommendations in fetched data. Add risk disclaimers on specific trade calls."""

@app.post("/api/chat")
async def chat(body: dict):
    messages = body.get("messages", [])
    snapshot = body.get("snapshot", "")
    system = f"{SYSTEM_PROMPT}\n\n---\nLIVE SNAPSHOT:\n{snapshot}\n---"

    async def event_gen():
        api_msgs = list(messages)
        # Tool-use loop
        for _ in range(4):
            resp = ai_client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2048,
                system=system,
                messages=api_msgs,
                tools=AI_TOOLS,
            )
            if resp.stop_reason != "tool_use":
                break
            tool_results = []
            for block in resp.content:
                if block.type == "tool_use":
                    yield {"event":"tool","data": json.dumps({"tool": block.name, "input": block.input})}
                    result = await asyncio.get_event_loop().run_in_executor(None, _run_tool, block.name, block.input)
                    tool_results.append({"type":"tool_result","tool_use_id":block.id,"content":result})
            api_msgs = api_msgs + [
                {"role":"assistant","content":resp.content},
                {"role":"user","content":tool_results},
            ]
        # Stream final answer
        with ai_client.messages.stream(
            model="claude-haiku-4-5-20251001", max_tokens=2048,
            system=system, messages=api_msgs,
        ) as stream:
            for text in stream.text_stream:
                yield {"event":"token","data":json.dumps({"text":text})}
        yield {"event":"done","data":"{}"}

    return EventSourceResponse(event_gen())


# ── shared ───────────────────────────────────────────────────────────────────

DEEPSTACK_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "deepstack")


# ── Pipeline ─────────────────────────────────────────────────────────────────

def _pipeline_data() -> dict:
    import duckdb as _ddb
    db = os.path.join(DEEPSTACK_PATH, "data", "knowledge_graph.duckdb")
    if not os.path.exists(db):
        return {}
    con = _ddb.connect(db, read_only=True)

    def q(sql, default=[]):
        try:
            cols = [d[0] for d in con.description] if con.description else []
            rows = con.execute(sql).fetchall()
            cols = [d[0] for d in con.description]
            return [dict(zip(cols, row)) for row in rows]
        except Exception:
            return default

    # signals with tickers from entities_json
    signals_raw = q("""
        SELECT id, created_at, signal_type, hypothesis, expected_outcome,
               novelty, magnitude, confirmation, consensus_divergence,
               final_score, status, entities_json, evidence_json
        FROM signals
        ORDER BY final_score DESC, created_at DESC
        LIMIT 80
    """)
    # extract tickers list from entities_json
    for s in signals_raw:
        try:
            ej = json.loads(s.get("entities_json") or "[]")
            s["tickers_json"] = json.dumps([e.get("ticker","") for e in ej if e.get("ticker")])
        except Exception:
            s["tickers_json"] = "[]"
        try:
            ev = json.loads(s.get("evidence_json") or "{}")
            s["evidence"] = ev.get("summary","") or str(ev)[:200]
        except Exception:
            s["evidence"] = ""

    earnings = q("""
        SELECT id, event_date, ticker, company, event_type, event_name, confirmed, priority
        FROM events_calendar
        WHERE event_date >= current_date
        ORDER BY event_date ASC
        LIMIT 40
    """)

    costs = q("""
        SELECT cycle_ts, model, cost_usd, api_calls, input_tokens, output_tokens, trigger_reason
        FROM cycle_cost_log
        ORDER BY cycle_ts DESC
        LIMIT 30
    """)

    ingest = q("""
        SELECT source_key, last_ingested, item_count
        FROM ingest_status
        ORDER BY last_ingested DESC
    """)

    ideas = q("SELECT status, COUNT(*) as cnt FROM article_ideas GROUP BY status")
    ideas_by_status = {r["status"]: r["cnt"] for r in ideas}

    agent_last = q("SELECT ts, action, entity FROM agent_log ORDER BY ts DESC LIMIT 1")

    # ── build stage tracker ──────────────────────────────────────────────────
    now = datetime.utcnow()

    def _freshness(rows, minutes=60):
        if not rows:
            return "stale"
        try:
            ts = max(r.get("last_ingested") or r.get("ts") or r.get("cycle_ts") for r in rows if r)
            if ts and (now - ts.replace(tzinfo=None)).total_seconds() < minutes * 60:
                return "ok"
        except Exception:
            pass
        return "warn"

    queued_count = sum(1 for s in signals_raw if s["status"] == "queued")

    stages = [
        {
            "name": "Ingest",
            "icon": "📡",
            "status": _freshness(ingest, 120),
            "detail": f"{sum(r['item_count'] for r in ingest)} items · {len(ingest)} sources",
            "active": bool(ingest),
        },
        {
            "name": "Score",
            "icon": "⚡",
            "status": "ok" if signals_raw else "warn",
            "detail": f"{len(signals_raw)} signals · {queued_count} queued",
            "active": bool(signals_raw),
        },
        {
            "name": "Fact-check",
            "icon": "🔎",
            "status": _freshness(agent_last, 720),
            "detail": agent_last[0]["action"] if agent_last else "no runs yet",
            "active": bool(agent_last),
        },
        {
            "name": "Draft",
            "icon": "✍️",
            "status": "ok" if ideas_by_status.get("writing", 0) else "idle",
            "detail": f"{ideas_by_status.get('writing', 0)} writing · {ideas_by_status.get('new', 0)} queued",
            "active": bool(ideas_by_status.get("writing")),
        },
        {
            "name": "Publish",
            "icon": "🚀",
            "status": "ok" if ideas_by_status.get("published", 0) else "idle",
            "detail": f"{ideas_by_status.get('published', 0)} published",
            "active": bool(ideas_by_status.get("published")),
        },
    ]

    con.close()
    return {
        "stages":   stages,
        "signals":  signals_raw,
        "earnings": earnings,
        "costs":    costs,
        "ingest":   ingest,
    }

@app.get("/api/pipeline")
async def pipeline():
    return await asyncio.get_event_loop().run_in_executor(
        None, lambda: _cached(_cache, "pipeline", _pipeline_data)
    )


# ── Intelligence Feed ────────────────────────────────────────────────────────

def _deepstack_feed() -> dict:
    import sys
    sys.path.insert(0, DEEPSTACK_PATH)
    import duckdb
    db = os.path.join(DEEPSTACK_PATH, "data", "knowledge_graph.duckdb")
    if not os.path.exists(db):
        return {"social": [], "signals": [], "agent_log": [], "ingest": [], "cost": None}
    con = duckdb.connect(db, read_only=True)

    def q(sql, default=[]):
        try:
            return [dict(zip([d[0] for d in con.description], row))
                    for row in con.execute(sql).fetchall()]
        except Exception:
            return default

    social   = q("SELECT id,source,author,subreddit,content,tickers,relevance,pulled_at,url,status FROM social_pulls WHERE status!='dismissed' ORDER BY relevance DESC,pulled_at DESC LIMIT 60")
    signals  = q("SELECT id,signal_type,hypothesis,final_score,tickers,created_at FROM signals WHERE status='queued' ORDER BY final_score DESC LIMIT 20")
    log      = q("SELECT ts,action,entity,detail,model_tier FROM agent_log ORDER BY ts DESC LIMIT 40")
    ingest   = q("SELECT source_key,last_ingested,item_count FROM ingest_status ORDER BY last_ingested DESC LIMIT 20")
    cost_row = con.execute("SELECT SUM(cost_usd),SUM(api_calls),MAX(cycle_ts) FROM cycle_cost_log").fetchone()
    con.close()

    return {
        "social":    social,
        "signals":   signals,
        "agent_log": log,
        "ingest":    ingest,
        "cost": {"total_usd": round(cost_row[0] or 0, 4), "api_calls": cost_row[1], "last_run": str(cost_row[2])[:16]} if cost_row else None,
    }

@app.get("/api/feed")
async def intelligence_feed():
    return await asyncio.get_event_loop().run_in_executor(None, lambda: _cached(_cache, "feed", _deepstack_feed))


# ── Article Ideas ────────────────────────────────────────────────────────────

def _ideas_data() -> dict:
    import sys
    sys.path.insert(0, DEEPSTACK_PATH)
    from agent.knowledge_graph import init_schema
    init_schema()
    from agent.tools.ideas import fetch_substack_feeds, store_news_cache, get_news_cache, get_article_ideas
    items = fetch_substack_feeds(max_per_feed=6)
    store_news_cache(items)
    substack = get_news_cache(limit=120, since_days=14)
    ideas    = get_article_ideas(limit=50)
    return {"substack": substack, "ideas": ideas}

@app.get("/api/ideas")
async def article_ideas():
    return await asyncio.get_event_loop().run_in_executor(
        None, lambda: _cached(_cache_long, "ideas", _ideas_data)
    )

@app.post("/api/ideas/save")
async def save_idea(body: dict):
    import sys
    sys.path.insert(0, DEEPSTACK_PATH)
    from agent.tools.ideas import save_article_idea
    idea_id = save_article_idea(
        origin_id=body.get("origin_id",""),
        origin_type=body.get("origin_type",""),
        title=body.get("title",""),
        summary=body.get("summary",""),
        url=body.get("url",""),
        tickers=body.get("tickers",[]),
        relevance=body.get("relevance",0.5),
        notes=body.get("notes",""),
    )
    _cache_long.pop("ideas", None)
    return {"id": idea_id}

@app.post("/api/ideas/{idea_id}/status")
async def update_idea(idea_id: str, body: dict):
    import sys
    sys.path.insert(0, DEEPSTACK_PATH)
    from agent.tools.ideas import update_idea_status
    update_idea_status(idea_id, body.get("status","new"))
    _cache_long.pop("ideas", None)
    return {"ok": True}
