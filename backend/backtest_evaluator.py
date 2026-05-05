import json
import os
import time
import pandas as pd
import tushare as ts
from datetime import datetime, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.hermes/.env")
except ImportError:
    pass

TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "REMOVED_TOKEN")
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()

BASE_DIR = Path(__file__).resolve().parent
HISTORY_FILE = BASE_DIR / "daily_scanner_history.json"
REPORT_FILE = BASE_DIR / "backtest_report.txt"


def get_last_trade_date():
    """获取最近一个A股交易日"""
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=20)).strftime("%Y%m%d")
    cal = pro.trade_cal(exchange="SSE", is_open="1", start_date=start, end_date=end)
    if cal.empty:
        return None
    return cal["cal_date"].iloc[0]  # Tushare returns descending; first = latest


def fetch_prices_batch(codes, trade_date):
    """批量获取指定交易日的股票收盘价（每批50只）"""
    prices = {}
    for i in range(0, len(codes), 50):
        batch = ",".join(codes[i:i + 50])
        try:
            # Use daily API (not daily_basic) with trade_date parameter - works for historical data
            df = pro.daily(ts_code=batch, trade_date=trade_date, fields="ts_code,close")
            for _, row in df.iterrows():
                prices[row["ts_code"]] = row["close"]
        except Exception:
            pass
        time.sleep(0.12)
    return prices


def fetch_prices_fallback(codes, trade_date):
    """带降级的价格获取：先尝试目标日期，失败则逐日回溯历史交易日"""
    prices = fetch_prices_batch(codes, trade_date)
    if prices:
        return prices
    cal = pro.trade_cal(exchange="SSE", is_open="1", start_date="20200101", end_date=trade_date)
    dates = cal["cal_date"].tolist()
    try:
        idx = dates.index(trade_date)
    except ValueError:
        return prices
    for d in reversed(dates[:idx]):
        prices = fetch_prices_batch(codes, d)
        if prices:
            return prices
    return prices


def evaluate():
    """回测主函数：读取历史选股记录，对比当前价格，计算收益率、胜率，生成报告"""
    if not HISTORY_FILE.exists():
        return None, "No history found."

    with open(HISTORY_FILE, "r", encoding="utf-8") as fh:
        history = json.load(fh)

    if not history:
        return None, "History is empty."

    latest_date = get_last_trade_date()

    all_codes = list({item["code"] for item in history})
    curr_prices = fetch_prices_fallback(all_codes, latest_date)

    hist_price_map = {}
    missing_dates = {}
    for item in history:
        code = item["code"]
        tdate = item["trade_date"]
        p = item.get("price")
        if p is not None:
            hist_price_map[(tdate, code)] = p
        else:
            missing_dates.setdefault(tdate, set()).add(code)

    for tdate, codes in missing_dates.items():
        prices = fetch_prices_batch(list(codes), tdate)
        for code, price in prices.items():
            hist_price_map[(tdate, code)] = price

    results = []
    total_ret = 0.0
    for item in history:
        code = item["code"]
        tdate = item["trade_date"]
        hp = hist_price_map.get((tdate, code))
        cp = curr_prices.get(code)
        if hp and cp:
            ret = (cp - hp) / hp * 100
            results.append({
                "date": tdate,
                "code": code,
                "name": item["name"],
                "hist_price": hp,
                "curr_price": cp,
                "return": round(ret, 2),
            })
            total_ret += ret

    if not results:
        return None, "Cannot compute returns (missing price data)."

    results.sort(key=lambda x: (x["date"], x["return"]), reverse=True)
    total_count = len(results)
    avg_ret = total_ret / total_count
    win_count = sum(1 for r in results if r["return"] > 0)
    win_rate = win_count / total_count * 100

    lines = [
        "## [flag] A股价值投资推荐历史回溯",
        f"累计推荐：{total_count}只 | 胜率(上涨比例)：{win_rate:.1f}% | 平均收益率：{avg_ret:+.2f}%",
        f"推荐日期参考：{results[-1]['date']} | 最新行情截止：{latest_date}",
        "",
    ]
    for r in results:
        trend = "[red]" if r["return"] > 0 else "[green]" if r["return"] < 0 else "[white]"
        lines.append(
            f"- **{r['name']}** ({r['code']}): "
            f"{r['date']} @ {r['hist_price']} -> {r['curr_price']} | {trend} {r['return']:+.2f}%"
        )

    report_text = "\n".join(lines)
    with open(REPORT_FILE, "w", encoding="utf-8") as fh:
        fh.write(report_text)

    return results, report_text


if __name__ == "__main__":
    results, text = evaluate()
    print(text)
