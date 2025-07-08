import akshare as ak
import pandas as pd
import datetime
import requests
import os

# ---------- 参数设置 ----------
bark_token = os.getenv("BARK_TOKEN")
bark_url = f"https://api.day.app/{bark_token}"
symbol = "01810"  # 小米港股代码
today = datetime.datetime.today()
today_str = today.strftime("%Y-%m-%d")

# ---------- 获取日线数据 ----------
df = ak.stock_hk_daily(symbol=symbol)

# 修正列名为英文版（你的版本）
df['date'] = pd.to_datetime(df['date'])
df = df[df['date'] <= today].copy()
df = df.sort_values('date').reset_index(drop=True)
df = df[df['date'] >= today - datetime.timedelta(days=180)].copy()

# ---------- 计算 KDJ 函数 ----------
def calculate_kdj(data, n=9):
    low_min = data['low'].rolling(window=n, min_periods=1).min()
    high_max = data['high'].rolling(window=n, min_periods=1).max()
    rsv = (data['close'] - low_min) / (high_max - low_min) * 100

    K = rsv.ewm(com=2).mean()
    D = K.ewm(com=2).mean()
    J = 3 * K - 2 * D
    return K, D, J

# ---------- 日线 KDJ ----------
df['K'], df['D'], df['J'] = calculate_kdj(df)
日J值 = df['J'].iloc[-1]

# ---------- 周线数据 ----------
df.set_index('date', inplace=True)
weekly = df.resample('W-FRI').agg({
    'close': 'last',
    'high': 'max',
    'low': 'min'
}).dropna().reset_index()
weekly['K'], weekly['D'], weekly['J'] = calculate_kdj(weekly)
周J值 = weekly['J'].iloc[-1]

# ---------- 判断逻辑 ----------
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

# ---------- 操作建议 ----------
if 暴跌触发 or 回撤_trigger:
    建议 = "✅ 加仓 3–5 手"
else:
    建议 = "✅ 定投 1 手 或 ❌ 暂不操作"

# ---------- 构造推送内容 ----------
title = "📊 小米操作建议"
body = f"""📅 日期：{today_str}
📈 当前股价：HK${today_price:.2f}（{涨跌幅:+.2%}）
📉 跌幅（20日）：{跌幅:.2%} ｜ {'✅ 暴跌' if 暴跌触发 else '❌ 正常'}
📉 回撤（近高点）：{回撤:.2%} ｜ {'✅ 回撤' if 回撤_trigger else '❌ 正常'}

📐 KDJ 日线 J 值：{日J值:.2f}
📐 KDJ 周线 J 值：{周J值:.2f}

📌 建议操作：{建议}
"""

# ---------- Bark 推送 ----------
params = {
    "title": title,
    "body": body,
    "group": "xiaomi-tips"
}
r = requests.get(bark_url, params=params)
print("✅ 推送成功" if r.ok else f"❌ 推送失败：{r.text}")
