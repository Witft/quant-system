import os
import json
import urllib.request
import math
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import tushare as ts

# 加载环境变量
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

MINIMAX_API_KEY = os.environ.get("MINIMAX_CN_API_KEY")
TUSHARE_TOKEN = os.environ.get("TUSHARE_TOKEN", "REMOVED_TOKEN")

ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()

BASE_DIR = Path(__file__).resolve().parent
HISTORY_FILE = BASE_DIR / "daily_scanner_history.json"
TECH_HISTORY_FILE = BASE_DIR / "tech_theme_history.json"
RECENT_DAYS = 7
TECH_RECENT_DAYS = 14
CANDIDATE_POOL_SIZE = 100
DAILY_PICK_COUNT = 3
PRE_FILTER_TARGET = 30  # 我们在百大候选池中，通过基本面过滤寻找前30个合格标的
TECH_DAILY_PICK_COUNT = 2
TZ = ZoneInfo("Asia/Shanghai")

TECH_WATCHLIST = [
    {"symbol": "NVDA", "name": "英伟达", "market": "US", "theme": "AI算力/GPU"},
    {"symbol": "AMD", "name": "AMD", "market": "US", "theme": "AI算力/GPU"},
    {"symbol": "AVGO", "name": "博通", "market": "US", "theme": "AI网络/ASIC"},
    {"symbol": "TSM", "name": "台积电ADR", "market": "US/TW", "theme": "先进制程/AI代工"},
    {"symbol": "ASML", "name": "阿斯麦ADR", "market": "US/EU", "theme": "光刻机/半导体设备"},
    {"symbol": "ARM", "name": "Arm", "market": "US", "theme": "AI终端/芯片IP"},
    {"symbol": "MSFT", "name": "微软", "market": "US", "theme": "AI应用/云"},
    {"symbol": "GOOGL", "name": "谷歌", "market": "US", "theme": "AI模型/云/广告"},
    {"symbol": "META", "name": "Meta", "market": "US", "theme": "AI应用/XR"},
    {"symbol": "AMZN", "name": "亚马逊", "market": "US", "theme": "AI云/电商"},
    {"symbol": "PLTR", "name": "Palantir", "market": "US", "theme": "AI软件/数据分析"},
    {"symbol": "AAPL", "name": "苹果", "market": "US", "theme": "XR/AI终端/消费电子"},
    {"symbol": "QCOM", "name": "高通", "market": "US", "theme": "AI手机/XR芯片"},
    {"symbol": "SONY", "name": "索尼ADR", "market": "US/JP", "theme": "XR/游戏/影像传感器"},
    {"symbol": "1810.HK", "name": "小米集团", "market": "HK", "theme": "AIoT/手机/智能汽车"},
    {"symbol": "0700.HK", "name": "腾讯控股", "market": "HK", "theme": "AI应用/游戏/云"},
    {"symbol": "9988.HK", "name": "阿里巴巴-W", "market": "HK", "theme": "AI云/电商"},
    {"symbol": "0981.HK", "name": "中芯国际", "market": "HK", "theme": "国产半导体制造"},
    {"symbol": "002415.SZ", "name": "海康威视", "market": "A股", "theme": "AI视觉/物联网"},
    {"symbol": "002230.SZ", "name": "科大讯飞", "market": "A股", "theme": "AI语音/大模型应用"},
]

def load_history():
    """加载A股选股历史记录（JSON文件）"""
    if not HISTORY_FILE.exists():
        return []
    try:
        with HISTORY_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []

def save_history(history):
    """将选股历史写入JSON文件"""
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_FILE.open("w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def recent_analyzed_codes(history, trade_date, days=RECENT_DAYS):
    """从历史记录中提取最近N天内已分析过的股票代码，用于去重"""
    cutoff = datetime.strptime(trade_date, "%Y%m%d") - timedelta(days=days)
    codes = set()
    for item in history:
        item_date = item.get("trade_date")
        code = item.get("code")
        if not item_date or not code:
            continue
        try:
            if datetime.strptime(item_date, "%Y%m%d") >= cutoff:
                codes.add(code)
        except ValueError:
            continue
    return codes

def record_picks(history, picks, trade_date):
    """将当日选股结果记录到历史中，幂等去重，并裁剪超过60天的旧记录"""
    existing = {(item.get("trade_date"), item.get("code")) for item in history}
    for stock in picks:
        key = (trade_date, stock["code"])
        if key not in existing:
            history.append({
                "trade_date": trade_date,
                "code": stock["code"],
                "name": stock["name"],
                "price": stock.get("price"),
                "margin": stock["margin"],
                "recorded_at": datetime.now(TZ).isoformat(timespec="seconds")
            })
    # 只保留最近 60 天，避免状态文件无限增长
    cutoff = datetime.strptime(trade_date, "%Y%m%d") - timedelta(days=60)
    compacted = []
    for item in history:
        try:
            if datetime.strptime(item.get("trade_date", ""), "%Y%m%d") >= cutoff:
                compacted.append(item)
        except ValueError:
            continue
    save_history(compacted)

def load_json_list(path):
    """通用的JSON列表文件加载器"""
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []

def save_json_list(path, data):
    """通用的JSON列表文件写入器"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def fetch_yahoo_quote(symbol):
    """从Yahoo Finance获取美股/港股的最新行情（价格、涨跌幅）"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
    result = data["chart"]["result"][0]
    meta = result["meta"]
    closes = [x for x in result.get("indicators", {}).get("quote", [{}])[0].get("close", []) if x is not None]
    price = meta.get("regularMarketPrice") or (closes[-1] if closes else None)
    prev = meta.get("chartPreviousClose") or (closes[-2] if len(closes) >= 2 else None)
    change_pct = None
    if price is not None and prev not in (None, 0):
        change_pct = (price - prev) / prev * 100
    return {
        "price": round(price, 2) if price is not None else None,
        "currency": meta.get("currency", ""),
        "exchange": meta.get("exchangeName", ""),
        "change_pct": round(change_pct, 2) if change_pct is not None else None,
    }

def scan_tech_themes(limit=TECH_DAILY_PICK_COUNT):
    """扫描AI/XR/科技数码跨市场主题观察池（美股+港股+A股），按当日波动排序，14天去重"""
    today = datetime.now(TZ).strftime("%Y%m%d")
    print(f"4. 正在扫描 AI/XR/科技数码跨市场主题观察池 ({len(TECH_WATCHLIST)}只)...")
    history = load_json_list(TECH_HISTORY_FILE)
    recent_symbols = recent_analyzed_codes(history, today, days=TECH_RECENT_DAYS)

    candidates = []
    for item in TECH_WATCHLIST:
        stock = dict(item)
        stock["code"] = stock["symbol"]
        try:
            stock.update(fetch_yahoo_quote(stock["symbol"]))
            stock["quote_error"] = None
        except Exception as e:
            stock.update({"price": None, "currency": "", "exchange": "", "change_pct": None})
            stock["quote_error"] = str(e)
        candidates.append(stock)
        time.sleep(0.2)

    # 主题股不适合用格雷厄姆低估排序；这里用“当日波动幅度”优先提示更值得复盘的标的，再做14天去重。
    candidates.sort(key=lambda x: abs(x["change_pct"] or 0), reverse=True)
    fresh = [s for s in candidates if s["symbol"] not in recent_symbols]
    selected = fresh[:limit]
    if len(selected) < limit:
        selected_symbols = {s["symbol"] for s in selected}
        selected.extend([s for s in candidates if s["symbol"] not in selected_symbols][:limit - len(selected)])

    existing = {(item.get("trade_date"), item.get("code")) for item in history}
    for stock in selected:
        key = (today, stock["symbol"])
        if key not in existing:
            history.append({
                "trade_date": today,
                "code": stock["symbol"],
                "name": stock["name"],
                "theme": stock["theme"],
                "change_pct": stock.get("change_pct"),
                "recorded_at": datetime.now(TZ).isoformat(timespec="seconds")
            })
    cutoff = datetime.strptime(today, "%Y%m%d") - timedelta(days=90)
    compacted = []
    for item in history:
        try:
            if datetime.strptime(item.get("trade_date", ""), "%Y%m%d") >= cutoff:
                compacted.append(item)
        except ValueError:
            continue
    save_json_list(TECH_HISTORY_FILE, compacted)
    return selected, today, len(candidates), len(recent_symbols)

def ask_minimax(prompt):
    """调用MiniMax大模型API进行AI分析"""
    if not MINIMAX_API_KEY:
        return "未配置 MINIMAX_CN_API_KEY，跳过 AI 分析。"
        
    url = "https://api.minimax.chat/v1/text/chatcompletion_v2"
    headers = {
        "Authorization": f"Bearer {MINIMAX_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "MiniMax-M2.7", 
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2 
    }
    
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers)
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result['choices'][0]['message']['content']
    except Exception as e:
        return f"AI分析失败: {e}"

def get_last_trade_date():
    """获取最近一个A股交易日日期"""
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=15)).strftime('%Y%m%d')
    df_cal = pro.trade_cal(exchange='SSE', is_open='1', start_date=start_date, end_date=end_date)
    return df_cal['cal_date'].iloc[-1]

def scan_a_shares(limit=DAILY_PICK_COUNT, candidate_pool_size=CANDIDATE_POOL_SIZE):
    """A股核心选股流程：格雷厄姆估值扫描 → 基本面排雷 → 7天去重 → 返回每日Top N"""
    last_date = get_last_trade_date()
    print(f"1. 正在获取全市场 A 股基础行情 (交易日: {last_date})...")
    
    df_stock = pro.stock_basic(exchange='', list_status='L', fields='ts_code,name')
    df_stock = df_stock[~df_stock['name'].str.contains('ST|退', na=False)]
    df_basic = pro.daily_basic(trade_date=last_date, fields='ts_code,close,pe_ttm,pb')
    df = pd.merge(df_stock, df_basic, on='ts_code')
    
    results = []
    print(f"2. 正在执行格雷厄姆内在价值全盘扫描...")
    
    for _, row in df.iterrows():
        price, pe, pb = row.get('close'), row.get('pe_ttm'), row.get('pb')
        if pd.isna(price) or pd.isna(pe) or pd.isna(pb) or price <= 0 or pe <= 0 or pb <= 0:
            continue
            
        eps, bvps = price / pe, price / pb
        graham_number = math.sqrt(22.5 * eps * bvps)
        
        if price < graham_number:
            margin = (graham_number - price) / graham_number
            results.append({
                'code': row['ts_code'], 'name': row['name'], 'price': price,
                'pe': round(pe, 2), 'pb': round(pb, 2),
                'graham': round(graham_number, 2), 'margin': round(margin * 100, 2)
            })
            
    results.sort(key=lambda x: x['margin'], reverse=True)
    initial_pool = results[:candidate_pool_size]
    
    print(f"3. 正在执行基本面硬指标排雷 (过滤高杠杆/负现金流/亏损)...")
    
    # 批量获取候选池的财务指标以避免API卡顿
    codes_str = ",".join([s['code'] for s in initial_pool])
    fina_df = pd.DataFrame()
    try:
        # 往前回溯半年以上的财报期，以确保能拿到最新的一期
        start_date = (datetime.now() - timedelta(days=200)).strftime("%Y%m%d")
        fina_df = pro.fina_indicator(ts_code=codes_str, start_date=start_date)
        if not fina_df.empty:
            fina_df = fina_df.sort_values('end_date', ascending=False).drop_duplicates(subset=['ts_code'], keep='first')
            fina_df = fina_df.set_index('ts_code')
    except Exception as e:
        print(f"   获取财务指标失败: {e}")

    candidate_pool = []
    for s in initial_pool:
        if len(candidate_pool) >= PRE_FILTER_TARGET:
            break
            
        code = s['code']
        if not fina_df.empty and code in fina_df.index:
            f = fina_df.loc[code]
            roe = f.get('roe', 0)
            roe = 0 if pd.isna(roe) else roe
            
            debt_to_assets = f.get('debt_to_assets', 100)
            debt_to_assets = 100 if pd.isna(debt_to_assets) else debt_to_assets
            
            ocfps = f.get('ocfps', -1)
            ocfps = -1 if pd.isna(ocfps) else ocfps
            
            netprofit_yoy = f.get('netprofit_yoy', -100)
            netprofit_yoy = -100 if pd.isna(netprofit_yoy) else netprofit_yoy
            
            if roe > 0 and ocfps > 0 and debt_to_assets < 85 and netprofit_yoy > -50:
                s['roe'] = round(roe, 2)
                s['debt_to_assets'] = round(debt_to_assets, 2)
                candidate_pool.append(s)
        else:
            # 如果拿不到数据，暂时放过，但没有这些指标
            candidate_pool.append(s)
            
    print(f"   过滤完成，获得 {len(candidate_pool)} 只基本面合格标的。")

    history = load_history()
    recent_codes = recent_analyzed_codes(history, last_date)
    fresh_picks = [s for s in candidate_pool if s['code'] not in recent_codes]
    selected = fresh_picks[:limit]

    # 如果 Top30 在最近7天都分析过，就允许回退到 Top30 中安全边际最高的股票，避免无内容输出。
    if len(selected) < limit:
        selected_codes = {s['code'] for s in selected}
        fallback = [s for s in candidate_pool if s['code'] not in selected_codes]
        selected.extend(fallback[:limit - len(selected)])

    record_picks(history, selected, last_date)
    return selected, last_date, len(candidate_pool), len(recent_codes)

def generate_daily_report():
    """主入口：运行A股扫描 + 科技主题扫描，对每只股票调用AI分析，生成完整日报"""
    top_stocks, trade_date, candidate_count, recent_count = scan_a_shares() # Top30候选池 + 最近7天去重 + 每日3只
    tech_stocks, tech_date, tech_count, tech_recent_count = scan_tech_themes()
    
    if not top_stocks and not tech_stocks:
        print("[SILENT] 今日无满足安全边际的股票推荐，科技主题观察池也暂无可分析标的。")
        return
        
    report = "=================================================\n"
    report += "🤖 【AI 投资董事会】每日深度低估扫描与科技主题观察\n"
    report += f"📅 A股交易日期: {trade_date} | 科技观察日期: {tech_date}\n"
    report += f"🔁 价值选股: 安全边际Top{candidate_count}候选池，最近{RECENT_DAYS}天已分析标的优先跳过，每日最多{DAILY_PICK_COUNT}只\n"
    report += f"🔭 科技主题: AI/XR/科技数码观察池{tech_count}只，按当日波动幅度排序，最近{TECH_RECENT_DAYS}天去重，每日最多{TECH_DAILY_PICK_COUNT}只\n"
    report += "=================================================\n"
    
    if top_stocks:
        report += "\n## 一、格雷厄姆低估值扫描\n"
    else:
        report += "\n## 一、格雷厄姆低估值扫描\n今日无满足安全边际的 A 股标的。\n"

    for s in top_stocks:
        print(f"\n正在召开针对 {s['name']} 的 AI 董事会会议...")
        
        summary = "无"
        try:
            info_df = pro.stock_company(ts_code=s['code'], fields='main_business')
            if not info_df.empty and not pd.isna(info_df['main_business'].iloc[0]):
                summary = str(info_df['main_business'].iloc[0])
        except:
            pass
            
        prompt = f"""
你现在主持一场针对A股公司【{s['name']}({s['code']})】的投资决策会议。
当前股价: ￥{s['price']}，理论内在价值(格雷厄姆数字): ￥{s['graham']} (安全边际: {s['margin']}%)
市盈率(PE TTM): {s['pe']}，市净率(PB): {s['pb']}
基本面数据：ROE {s.get('roe', '未知')}%，资产负债率 {s.get('debt_to_assets', '未知')}%
主营业务：{summary}

请以如下结构严格输出会议记录：
1. 😈 【做空蓝军排雷】：不要说好话！假设你持有10亿做空仓位，请强行挑出这只股票最致命的 3 个潜在暴雷点或价值陷阱（如：涉房涉地方债、重资产折旧、技术被淘汰等）。
2. 🧐 【F-Score 审计师】：基于皮奥特罗斯基(Piotroski)的财务健康理念和该公司的行业特征，指出要确认它“不是即将破产的垃圾股”，我们最需要重点查验它的哪 2 个底层财务指标？（如：经营现金流、毛利率等）为什么？
3. 👨‍🏫 【金融私教课】：从上述两点分析中，提取一个最核心的专业金融词汇，向非金融专业的IT工程师用生活中的比喻解释一下（80字以内）。
4. ⚖️ 【最终裁决】：(坚决回避 / 放入观察池 / 具备安全边际可买入)
"""
        analysis = ask_minimax(prompt)
        
        report += f"🔥 标的：{s['name']} ({s['code']})\n"
        report += f"   数据：现价 ￥{s['price']} | 理论估值 ￥{s['graham']} | PE {s['pe']} | PB {s['pb']}\n"
        report += f"   基本面：ROE {s.get('roe', '未知')}% | 负债率 {s.get('debt_to_assets', '未知')}%\n\n"
        report += f"{analysis}\n"
        report += "="*50 + "\n"

    if tech_stocks:
        report += "\n## 二、AI / XR / 科技数码主题观察\n"

    for s in tech_stocks:
        print(f"\n正在召开针对科技主题股 {s['name']} 的 AI 观察会议...")
        change_text = "未知" if s.get("change_pct") is None else f"{s['change_pct']}%"
        price_text = "未知" if s.get("price") is None else f"{s['price']} {s.get('currency', '')}".strip()
        prompt = f"""
你现在主持一场针对跨市场科技主题股票【{s['name']}({s['symbol']})】的观察会议。
市场/交易所：{s['market']} / {s.get('exchange', '')}
主题标签：{s['theme']}
最新价格：{price_text}
最近交易日涨跌幅：{change_text}

注意：这不是格雷厄姆低估值策略，而是 AI/XR/科技数码主题观察。请避免因为热门叙事就直接看多。
请以如下结构输出，保持简洁但有信息密度：
1. 🚀 【技术叙事】：它和 AI、XR 或科技数码趋势的核心关联是什么？是真需求还是蹭概念？
2. 😈 【反方排雷】：挑出 3 个主要风险，尤其关注估值过热、周期性、竞争格局、监管/地缘政治、硬件库存周期。
3. 📌 【后续观察指标】：列出接下来最值得跟踪的 2 个催化剂或财报指标。
4. ⚖️ 【观察结论】：(忽略 / 放入观察池 / 值得深入研究)，并说明原因。不要给直接买入建议。
"""
        analysis = ask_minimax(prompt)
        report += f"🧭 主题标的：{s['name']} ({s['symbol']})\n"
        report += f"   主题：{s['theme']} | 市场：{s['market']} | 价格：{price_text} | 涨跌幅：{change_text}\n\n"
        if s.get("quote_error"):
            report += f"   注：行情拉取异常：{s['quote_error']}\n\n"
        report += f"{analysis}\n"
        report += "="*50 + "\n"
        
    print(report)

if __name__ == "__main__":
    generate_daily_report()
