import datetime
import pandas as pd
import akshare as ak
import requests
from notion_client import Client

# ====== 配置项 ======
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
BARK_TOKEN = os.getenv("BARK_TOKEN")
BARK_URL = f"https://api.day.app/{BARK_TOKEN}"
SYMBOL = "01810"  # 小米港股代码
ADD_INTERVAL_DAYS = 10  # 加仓间隔（交易日）

# ====== 判断是否为交易日 ======
today = datetime.date.today()
calendar_df = ak.tool_trade_date_hist_sina()
calendar_df["trade_date"] = pd.to_datetime(calendar_df["trade_date"]).dt.date
is_trading_day = today in calendar_df["trade_date"].tolist()

if not is_trading_day:
    print(f"❌ 今天 {today} 不是交易日，跳过执行")
    exit(0)
else:
    print(f"✅ 今天 {today} 是交易日，继续执行")

# ====== 获取数据 ======
df = ak.stock_hk_daily(symbol=SYMBOL)
df['date'] = pd.to_datetime(df['date'])
df = df[df['date'].dt.date < today].sort_values('date')

last_trade_date = df['date'].iloc[-1].date()
today_str = last_trade_date.strftime("%Y-%m-%d")

latest_data = df[df['date'].dt.date == last_trade_date].iloc[-1]
today_price = latest_data['close']
涨跌幅 = (latest_data['close'] - latest_data['open']) / latest_data['open']

past_20_idx = df.index[df['date'].dt.date == last_trade_date][0] - 20
if past_20_idx >= 0:
    price_20_days_ago = df.iloc[past_20_idx]['close']
    跌幅 = (price_20_days_ago - today_price) / price_20_days_ago
else:
    跌幅 = 0

recent_high = df['close'].max()
回撤 = (recent_high - today_price) / recent_high

# ====== KDJ ======
def calc_kdj(data):
    low_list = data['low'].rolling(9, min_periods=1).min()
    high_list = data['high'].rolling(9, min_periods=1).max()
    rsv = (data['close'] - low_list) / (high_list - low_list) * 100
    k = rsv.ewm(com=2).mean()
    d = k.ewm(com=2).mean()
    j = 3 * k - 2 * d
    return j

kdj_j_daily = calc_kdj(df.tail(60)).iloc[-1]
df_weekly = df.set_index('date').resample('W-FRI').agg({
    'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
})
df_weekly = df_weekly[df_weekly['close'].notna()]
kdj_j_weekly = calc_kdj(df_weekly.tail(30)).iloc[-1]

# ====== Notion 加仓历史检查 ======
notion = Client(auth=NOTION_TOKEN)
past_trade_dates = df[df['date'].dt.date < last_trade_date]['date'].dt.date.tolist()
interval_start = past_trade_dates[-ADD_INTERVAL_DAYS] if len(past_trade_dates) >= ADD_INTERVAL_DAYS else past_trade_dates[0]

filter_query = {
    "property": "记录日期",
    "date": {"on_or_after": interval_start.isoformat()}
}
results = notion.databases.query(database_id=DATABASE_ID, filter=filter_query)
recent_ops = results.get("results", [])
最近加过仓 = any(
    page["properties"].get("已执行操作", {}).get("select", {}).get("name") == "已加仓"
    for page in recent_ops
)

# ====== 判断建议操作 ======
跌幅_output = f"{跌幅:.2%} ｜ {'✅ 建议买入（跌幅大）' if 跌幅 >= 0.10 else '❌ 跌幅不足'}"
回撤_output = f"{回撤:.2%} ｜ {'✅ 建议买入（回撤深）' if 回撤 >= 0.15 else '❌ 回撤不足'}"
建议 = "❌ 不建议操作"
类型 = "不建议操作"

if not 最近加过仓:
    if 跌幅 >= 0.20 or 回撤 >= 0.25:
        建议 = "✅ 加仓 5 手"
        类型 = "加仓"
    elif 跌幅 >= 0.15 or 回撤 >= 0.20:
        建议 = "✅ 加仓 4 手"
        类型 = "加仓"
    elif 跌幅 >= 0.10 or 回撤 >= 0.15:
        建议 = "✅ 加仓 3 手"
        类型 = "加仓"
else:
    print("⚠️ 已在近 10 个交易日内加仓过，今日不建议重复加仓")

if 类型 == "不建议操作":
    try:
        same_month = df[df['date'].dt.month == last_trade_date.month]
        first_idx = same_month[same_month['date'].dt.day >= 16].index[0]
        is_first_after_16 = df[df['date'].dt.date == last_trade_date].index[0] == first_idx
        is_invest_day = last_trade_date.day >= 16 and is_first_after_16
    except IndexError:
        is_invest_day = False

    if is_invest_day:
        建议 = "✅ 定投 1 手"
        类型 = "定投"

# ====== Bark 推送 ======
msg_lines = [
    f"📅 日期：{today_str}",
    f"📈 当前股价：HK${today_price:.2f}（{涨跌幅:+.2%}）",
    f"📉 跌幅（20日）：{跌幅_output}",
    f"📉 回撤（近高点）：{回撤_output}",
    f"\n📐 KDJ 日线 J 值：{kdj_j_daily:.2f}",
    f"📐 KDJ 周线 J 值：{kdj_j_weekly:.2f}",
    f"\n📌 建议操作：{建议}"
]
message = "\n".join(msg_lines)
requests.get(f"{BARK_URL}/{类型}?body=" + message)

# ====== 写入 Notion ======
notion.pages.create(
    parent={"database_id": DATABASE_ID},
    properties={
        "日期": {"title": [{"text": {"content": today_str}}]},
        "记录日期": {"date": {"start": today_str}},
        "当前股价（涨跌幅）": {"rich_text": [{"text": {"content": f"HK${today_price:.2f}（{涨跌幅:+.2%}）"}}]},
        "跌幅（20日）": {"rich_text": [{"text": {"content": 跌幅_output}}]},
        "回撤（近高点）": {"rich_text": [{"text": {"content": 回撤_output}}]},
        "KDJ 日线 J": {"rich_text": [{"text": {"content": f"{kdj_j_daily:.2f}"}}]},
        "KDJ 周线 J": {"rich_text": [{"text": {"content": f"{kdj_j_weekly:.2f}"}}]},
        "建议操作": {"rich_text": [{"text": {"content": 建议}}]},
        "已执行操作": {"select": {"name": "无操作"}},
        "备注": {"rich_text": [{"text": {"content": ""}}]}
    }
)

print("✅ 数据已推送并写入 Notion（默认操作为无操作）")
