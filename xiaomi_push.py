import akshare as ak
import pandas as pd
import datetime
import requests
import os

# ------------------ Notion 配置 ------------------
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("DATABASE_ID")

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def check_recent_operations(days: int = 5):
    today = datetime.date.today()
    start_date = today - datetime.timedelta(days=days + 2)
    start_iso = start_date.isoformat()

    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    payload = {
        "filter": {
            "property": "日期",
            "date": {"on_or_after": start_iso}
        },
        "page_size": 20
    }

    response = requests.post(url, headers=headers, json=payload)
    data = response.json()

    if "results" not in data:
        print("❌ 无法读取 Notion 数据:", data)
        return False, False

    加仓过 = False
    定投过 = False
    for result in data["results"]:
        properties = result.get("properties", {})
        type_field = properties.get("类型", {}).get("select", {})
        type_value = type_field.get("name", "")
        if type_value == "加仓":
            加仓过 = True
        elif type_value == "定投":
            定投过 = True

    return 加仓过, 定投过

# ------------------ 小米数据分析 ------------------

bark_token = os.getenv("BARK_TOKEN")
bark_url = f"https://api.day.app/{bark_token}"
symbol = "01810"
today = datetime.datetime.today()
today_str = today.strftime("%Y-%m-%d")

df = ak.stock_hk_daily(symbol=symbol)
df['date'] = pd.to_datetime(df['date'])
df = df[df['date'] <= today].copy()
df = df.sort_values('date').reset_index(drop=True)
df = df[df['date'] >= today - datetime.timedelta(days=180)].copy()

def calculate_kdj(data, n=9):
    low_min = data['low'].rolling(window=n, min_periods=1).min()
    high_max = data['high'].rolling(window=n, min_periods=1).max()
    rsv = (data['close'] - low_min) / (high_max - low_min) * 100
    K = rsv.ewm(com=2).mean()
    D = K.ewm(com=2).mean()
    J = 3 * K - 2 * D
    return K, D, J

df['K'], df['D'], df['J'] = calculate_kdj(df)
日J值 = df['J'].iloc[-1]
df.set_index('date', inplace=True)
weekly = df.resample('W-FRI').agg({
    'close': 'last',
    'high': 'max',
    'low': 'min'
}).dropna().reset_index()
weekly['K'], weekly['D'], weekly['J'] = calculate_kdj(weekly)
周J值 = weekly['J'].iloc[-1]

today_price = df['close'].iloc[-1]
yesterday_price = df['close'].iloc[-2]
涨跌幅 = (today_price - yesterday_price) / yesterday_price

if len(df) >= 21:
    price_20_days_ago = df['close'].iloc[-21]
    跌幅 = (price_20_days_ago - today_price) / price_20_days_ago
else:
    跌幅 = 0

recent_high = df['close'].max()
回撤 = (recent_high - today_price) / recent_high
暴跌触发 = 跌幅 >= 0.10
回撤_trigger = 回撤 >= 0.15

跌幅输出 = f"{跌幅:.2%} ｜ {'✅ 建议买入（跌幅大）' if 暴跌触发 else '❌ 不建议买入（跌幅正常）'}"
回撤输出 = f"{回撤:.2%} ｜ {'✅ 建议买入（回撤深）' if 回撤_trigger else '❌ 不建议买入（回撤轻）'}"

# 判断是否近期已加仓或定投
加仓过, 定投过 = check_recent_operations(5)
if (暴跌触发 or 回撤_trigger) and not 加仓过:
    建议 = "✅ 加仓 3–5 手"
elif (暴跌触发 or 回撤_trigger) and 加仓过:
    建议 = "❌ 已加仓过，今日不重复操作"
elif not 定投过:
    建议 = "✅ 定投 1 手"
else:
    建议 = "❌ 今日不建议操作"

title = "📊 小米操作建议"
body = f"""📅 日期：{today_str}
📈 当前股价：HK${today_price:.2f}（{涨跌幅:+.2%}）
📉 跌幅（20日）：{跌幅输出}
📉 回撤（近高点）：{回撤输出}

📐 KDJ 日线 J 值：{日J值:.2f}
📐 KDJ 周线 J 值：{周J值:.2f}

📌 建议操作：{建议}
"""

if bark_token:
    params = {"title": title, "body": body, "group": "xiaomi-tips"}
    r = requests.get(bark_url, params=params)
    print("✅ 推送成功" if r.ok else f"❌ 推送失败：{r.text}")
else:
    print("📬 Bark token 未设置，跳过推送")
    print(body)
