import akshare as ak
import pandas as pd
import datetime
import requests
import os

# 获取 Bark 推送 token（通过 GitHub Secrets 设置）
bark_token = os.getenv("BARK_TOKEN")
bark_url = f"https://api.day.app/{bark_token}"

# 设置股票代码与当前日期
symbol = "01810"
today = datetime.datetime.today()
today_str = today.strftime("%Y-%m-%d")

# 获取小米港股最近半年日线数据
df = ak.stock_hk_daily(symbol=symbol)
df['date'] = pd.to_datetime(df['date'])
df = df[df['date'] <= today].copy()
df = df.sort_values('date').reset_index(drop=True)
df = df[df['date'] >= today - datetime.timedelta(days=180)].copy()

# 计算日线 KDJ 指标
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

# 计算周线 KDJ 指标
df.set_index('date', inplace=True)
weekly = df.resample('W-FRI').agg({
    'close': 'last',
    'high': 'max',
    'low': 'min'
}).dropna().reset_index()
weekly['K'], weekly['D'], weekly['J'] = calculate_kdj(weekly)
周J值 = weekly['J'].iloc[-1]

# 价格数据与涨跌幅
today_price = df['close'].iloc[-1]
yesterday_price = df['close'].iloc[-2]
涨跌幅 = (today_price - yesterday_price) / yesterday_price

# 计算跌幅与回撤
if len(df) >= 21:
    price_20_days_ago = df['close'].iloc[-21]
    跌幅 = (price_20_days_ago - today_price) / price_20_days_ago
else:
    跌幅 = 0

recent_high = df['close'].max()
回撤 = (recent_high - today_price) / recent_high

# 触发条件判断
暴跌触发 = 跌幅 >= 0.10
回撤_trigger = 回撤 >= 0.15

# 文本表达优化
跌幅输出 = f"{跌幅:.2%} ｜ {'✅ 建议买入（跌幅大）' if 暴跌触发 else '❌ 不建议买入（跌幅正常）'}"
回撤输出 = f"{回撤:.2%} ｜ {'✅ 建议买入（回撤深）' if 回撤_trigger else '❌ 不建议买入（回撤轻）'}"

# 最终操作建议
建议 = "✅ 加仓 3–5 手" if 暴跌触发 or 回撤_trigger else "✅ 定投 1 手 或 ❌ 暂不操作"

# 组装通知内容
title = "📊 小米操作建议"
body = f"""📅 日期：{today_str}
📈 当前股价：HK${today_price:.2f}（{涨跌幅:+.2%}）
📉 跌幅（20日）：{跌幅输出}
📉 回撤（近高点）：{回撤输出}

📐 KDJ 日线 J 值：{日J值:.2f}
📐 KDJ 周线 J 值：{周J值:.2f}

📌 建议操作：{建议}
"""

# Bark 推送
params = {"title": title, "body": body, "group": "xiaomi-tips"}
r = requests.get(bark_url, params=params)
print("✅ 推送成功" if r.ok else f"❌ 推送失败：{r.text}")
