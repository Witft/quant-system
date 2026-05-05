"""
Quant Stock Picks API
Serves structured daily scanner results from PostgreSQL.
"""
import os

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

DB_HOST = os.getenv("DB_HOST", "47.97.98.164")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "financial_assistant")
DB_USER = os.getenv("DB_USER", "financial_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

app = FastAPI(title="Quant Stock Picks API", version="0.1.0")


def get_conn():
    """创建PostgreSQL数据库连接"""
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASSWORD
    )


# ── Pydantic models ─────────────────────────────────────────────────────────

class StockPick(BaseModel):
    trade_date: str
    code: str
    name: str | None
    price: float | None
    pe: float | None
    pb: float | None
    graham: float | None
    margin: float | None
    roe: float | None
    debt_to_assets: float | None
    ai_structured_json: str | None
    recorded_at: str | None


class StatsOut(BaseModel):
    total_days: int
    total_picks: int
    avg_margin: float | None
    avg_roe: float | None


# ── Routes ──────────────────────────────────────────────────────────────────

@app.get("/api/stats", response_model=StatsOut)
def stats():
    """GET /api/stats — 返回汇总统计（总天数、总推荐数、平均安全边际、平均ROE）"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(DISTINCT trade_date)::int,
               COUNT(*)::int,
               ROUND(AVG(margin)::numeric, 2),
               ROUND(AVG(roe)::numeric, 2)
        FROM stock_picks
    """)
    row = cur.fetchone()
    conn.close()
    return {
        "total_days": row[0],
        "total_picks": row[1],
        "avg_margin": float(row[2]) if row[2] else None,
        "avg_roe": float(row[3]) if row[3] else None,
    }


@app.get("/api/picks")
def picks(
    """GET /api/picks — 查询选股记录，支持按日期/股票代码筛选"""
    date: str = Query(None, min_length=8, max_length=8),
    code: str = Query(None, min_length=3, max_length=12),
    limit: int = Query(50, ge=1, le=200),
):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if date:
        cur.execute(
            "SELECT * FROM stock_picks WHERE trade_date=%s ORDER BY margin DESC LIMIT %s",
            (date, limit),
        )
    elif code:
        cur.execute(
            "SELECT * FROM stock_picks WHERE code=%s ORDER BY trade_date DESC LIMIT %s",
            (code, limit),
        )
    else:
        cur.execute(
            "SELECT * FROM stock_picks ORDER BY trade_date DESC, margin DESC LIMIT %s",
            (limit,),
        )
    rows = cur.fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["recorded_at"] = str(d["recorded_at"]) if d["recorded_at"] else None
        result.append(d)
    return {"data": result}


@app.get("/health")
def health():
    """GET /health — 健康检查，验证数据库连接是否正常"""
    try:
        conn = get_conn()
        conn.close()
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        return {"status": "error", "db": str(e)}


@app.get("/", response_class=HTMLResponse)
def index():
    """Serve the dashboard page."""
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    path = os.path.join(static_dir, "dashboard.html")
    if not os.path.exists(path):
        return HTMLResponse("<h1>dashboard.html not found</h1>", status_code=404)
    with open(path, "r") as f:
        return HTMLResponse(f.read())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
