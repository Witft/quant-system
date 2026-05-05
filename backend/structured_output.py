"""
structured_output.py
Stores structured daily scanner picks + AI analysis into PostgreSQL on ECS (47.97.98.164).

DB: financial_assistant
Table: stock_picks (trade_date, code, name, price, pe, pb, graham, margin,
                    roe, debt_to_assets, ocfps, netprofit_yoy, ai_structured_json,
                    ai_raw_text, recorded_at)
"""
import json
import math
import os
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import psycopg2
import tushare as ts

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.hermes/.env")
except ImportError:
    pass

TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "REMOVED_TOKEN")
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()

DB_HOST = "47.97.98.164"
DB_PORT = 5432
DB_NAME = "financial_assistant"
DB_USER = "financial_user"
DB_PASSWORD = os.getenv("FINANCIAL_PG_PASSWORD")  # Set via cron env or VPS .env

def get_pg_conn(password=None):
    """创建PostgreSQL数据库连接"""
    p = password or DB_PASSWORD or os.getenv("DATABASE_URL", "").split(":")[-1].split("@")[0]
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=p
    )


def init_db():
    """初始化数据库：创建stock_picks表和索引（如果不存在）"""
    conn = get_pg_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stock_picks (
            id            SERIAL PRIMARY KEY,
            trade_date    TEXT NOT NULL,
            code          TEXT NOT NULL,
            name          TEXT,
            price         REAL,
            pe            REAL,
            pb            REAL,
            graham        REAL,
            margin        REAL,
            roe           REAL,
            debt_to_assets REAL,
            ocfps         REAL,
            netprofit_yoy REAL,
            ai_structured_json TEXT,
            ai_raw_text   TEXT,
            recorded_at   TEXT NOT NULL DEFAULT NOW(),
            UNIQUE(trade_date, code)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_picks_date ON stock_picks(trade_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_picks_code ON stock_picks(code)")
    conn.commit()
    conn.close()
    print("[PG] Table stock_picks ready.")


def upsert_pick(pick: dict):
    """插入或更新一条选股记录到stock_picks表（按交易日+股票代码去重）"""
    conn = get_pg_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO stock_picks
            (trade_date, code, name, price, pe, pb, graham, margin,
             roe, debt_to_assets, ocfps, netprofit_yoy,
             ai_structured_json, ai_raw_text, recorded_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
        ON CONFLICT(trade_date, code) DO UPDATE
            SET ai_structured_json = EXCLUDED.ai_structured_json,
                ai_raw_text       = EXCLUDED.ai_raw_text,
                recorded_at       = NOW()
    """, (
        pick["trade_date"], pick["code"], pick["name"], pick["price"],
        pick["pe"], pick["pb"], pick["graham"], pick["margin"],
        pick.get("roe"), pick.get("debt_to_assets"),
        pick.get("ocfps"), pick.get("netprofit_yoy"),
        pick.get("ai_structured_json"),
        pick.get("ai_raw_text"),
    ))
    conn.commit()
    conn.close()


def query_picks(trade_date: str = None, limit: int = 50) -> list:
    """查询选股记录，可按交易日筛选，默认按安全边际降序"""
    conn = get_pg_conn()
    cur = conn.cursor()
    if trade_date:
        cur.execute(
            "SELECT trade_date,code,name,price,pe,pb,graham,margin,roe,debt_to_assets,ai_structured_json,recorded_at "
            "FROM stock_picks WHERE trade_date=%s ORDER BY margin DESC LIMIT %s",
            (trade_date, limit)
        )
    else:
        cur.execute(
            "SELECT trade_date,code,name,price,pe,pb,graham,margin,roe,debt_to_assets,ai_structured_json,recorded_at "
            "FROM stock_picks ORDER BY trade_date DESC, margin DESC LIMIT %s",
            (limit,)
        )
    rows = cur.fetchall()
    conn.close()
    return rows


def query_stats() -> dict:
    """查询汇总统计：总天数、总推荐数、平均安全边际、平均ROE"""
    conn = get_pg_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(DISTINCT trade_date) AS days,
               COUNT(*) AS total_picks,
               ROUND(AVG(margin)::numeric, 2) AS avg_margin,
               ROUND(AVG(roe)::numeric, 2)    AS avg_roe
        FROM stock_picks
    """)
    row = cur.fetchone()
    conn.close()
    return {"days": row[0], "total_picks": row[1], "avg_margin": row[2], "avg_roe": row[3]}


# ── Tushare helpers ──────────────────────────────────────────────────────────

def get_last_trade_date():
    """获取最近一个A股交易日"""
    end   = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=20)).strftime("%Y%m%d")
    cal = pro.trade_cal(exchange="SSE", is_open="1", start_date=start, end_date=end)
    if cal.empty:
        return None
    return cal["cal_date"].iloc[0]  # descending, iloc[0] = latest


def fetch_prices_batch(codes, trade_date):
    """批量获取指定交易日的股票收盘价（每批50只，限速0.12s）"""
    prices = {}
    for i in range(0, len(codes), 50):
        batch = ",".join(codes[i:i + 50])
        try:
            df = pro.daily(ts_code=batch, trade_date=trade_date, fields="ts_code,close")
            for _, row in df.iterrows():
                prices[row["ts_code"]] = row["close"]
        except Exception:
            pass
        time.sleep(0.12)
    return prices


# ── AI helpers ───────────────────────────────────────────────────────────────

def ask_minimax(prompt: str) -> str:
    """调用MiniMax大模型API，返回AI分析文本"""
    key = os.getenv("MINIMAX_CN_API_KEY")
    if not key:
        return "AI analysis skipped: MINIMAX_CN_API_KEY not set."
    url = "https://api.minimax.chat/v1/text/chatcompletion_v2"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": "MiniMax-M2.7",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"]
    except Exception as e:
        return f"AI call failed: {e}"


def parse_structured_response(text: str) -> dict:
    """从AI自由文本中提取结构化字段（推荐结论、风险点）"""
    out = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        for sep in [":", "："]:
            if sep in line:
                key = line.split(sep, 1)[0].strip()
                val = line.split(sep, 1)[1].strip()
                if any(k in key for k in ["裁决", "结论", "最终结论", "最终裁决"]):
                    out["recommendation"] = val
                elif "蓝军" in key or "做空" in key:
                    out["risk_points"] = val
    return out


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_pipeline(top_n: int = 3):
    """
    Full daily pipeline:
    1. Graham scan -> fundamental filter -> AI analysis -> PG upsert
    Returns number of records stored.
    """
    init_db()
    last_date = get_last_trade_date()
    print(f"[PG] Pipeline start for {last_date}")

    # 1. A-share basics
    df_stock = pro.stock_basic(exchange="", list_status="L", fields="ts_code,name")
    df_stock = df_stock[~df_stock["name"].str.contains("ST|退", na=False)]
    df_basic = pro.daily_basic(trade_date=last_date, fields="ts_code,close,pe_ttm,pb")
    df = pd.merge(df_stock, df_basic, on="ts_code")

    # 2. Graham scan
    results = []
    for _, row in df.iterrows():
        price, pe, pb = row.get("close"), row.get("pe_ttm"), row.get("pb")
        if pd.isna(price) or pd.isna(pe) or pd.isna(pb) or price <= 0 or pe <= 0 or pb <= 0:
            continue
        eps, bvps = price / pe, price / pb
        graham = math.sqrt(22.5 * eps * bvps)
        if price < graham:
            results.append({
                "code": row["ts_code"], "name": row["name"],
                "price": price, "pe": round(pe, 2), "pb": round(pb, 2),
                "graham": round(graham, 2),
                "margin": round((graham - price) / graham * 100, 2),
            })

    results.sort(key=lambda x: x["margin"], reverse=True)
    initial_pool = results[:100]

    # 3. Fundamental filter
    codes_str = ",".join([s["code"] for s in initial_pool])
    fina_df = pd.DataFrame()
    try:
        start = (datetime.now() - timedelta(days=200)).strftime("%Y%m%d")
        fina_df = pro.fina_indicator(ts_code=codes_str, start_date=start)
        if not fina_df.empty:
            fina_df = (fina_df.sort_values("end_date", ascending=False)
                                .drop_duplicates("ts_code", keep="first")
                                .set_index("ts_code"))
    except Exception as e:
        print(f"[PG] fina_indicator error: {e}")

    candidate_pool = []
    for s in initial_pool:
        if len(candidate_pool) >= 30:
            break
        code = s["code"]
        if not fina_df.empty and code in fina_df.index:
            f = fina_df.loc[code]
            roe    = f.get("roe");            roe    = 0   if pd.isna(roe)    else roe
            debt   = f.get("debt_to_assets"); debt   = 100 if pd.isna(debt)   else debt
            ocfps  = f.get("ocfps");           ocfps  = -1  if pd.isna(ocfps)  else ocfps
            npm    = f.get("netprofit_yoy");  npm    = -100 if pd.isna(npm)   else npm
            if roe > 0 and ocfps > 0 and debt < 85 and npm > -50:
                s["roe"]           = round(roe, 2)
                s["debt_to_assets"] = round(debt, 2)
                s["ocfps"]          = round(ocfps, 2)
                s["netprofit_yoy"]  = round(npm, 2)
                candidate_pool.append(s)
        else:
            candidate_pool.append(s)

    print(f"[PG] {len(candidate_pool)} candidates after filter.")

    # 4. AI analysis -> PG upsert
    stored = 0
    for s in candidate_pool[:top_n]:
        print(f"[PG] Analyzing {s['name']} ({s['code']})...")
        try:
            info_df = pro.stock_company(ts_code=s["code"], fields="main_business")
            summary = ""
            if not info_df.empty and not pd.isna(info_df["main_business"].iloc[0]):
                summary = str(info_df["main_business"].iloc[0])
        except Exception:
            summary = ""

        prompt = f"""你现在主持一场针对A股公司【{s['name']}({s['code']})】的投资决策会议。
当前股价: ￥{s['price']}，理论内在价值(格雷厄姆数字): ￥{s['graham']} (安全边际: {s['margin']}%)
市盈率(PE TTM): {s['pe']}，市净率(PB): {s['pb']}
基本面数据：ROE {s.get('roe','未知')}%，资产负债率 {s.get('debt_to_assets','未知')}%
主营业务：{summary}

请以如下结构严格输出会议记录：
1. 【做空蓝军排雷】：挑出这只股票最致命的3个潜在暴雷点或价值陷阱。
2. 【F-Score审计师】：基于皮奥特罗斯基F-Score，指出最需要重点查验的2个底层财务指标。
3. 【金融私教课】：提取一个最核心的专业金融词汇，用生活比喻解释（80字以内）。
4. 【最终裁决】：(坚决回避 / 放入观察池 / 具备安全边际可买入)
"""
        raw_text = ask_minimax(prompt)
        structured = parse_structured_response(raw_text)
        ai_json = json.dumps(structured, ensure_ascii=False) if structured else None

        pick = {
            "trade_date": last_date,
            "code": s["code"],
            "name": s["name"],
            "price": s["price"],
            "pe": s["pe"],
            "pb": s["pb"],
            "graham": s["graham"],
            "margin": s["margin"],
            "roe": s.get("roe"),
            "debt_to_assets": s.get("debt_to_assets"),
            "ocfps": s.get("ocfps"),
            "netprofit_yoy": s.get("netprofit_yoy"),
            "ai_structured_json": ai_json,
            "ai_raw_text": raw_text,
        }
        upsert_pick(pick)
        stored += 1
        time.sleep(0.5)

    print(f"[PG] Pipeline done. {stored} records stored.")
    return stored


if __name__ == "__main__":
    n = run_pipeline()
    stats = query_stats()
    print(f"DB stats: {stats}")
