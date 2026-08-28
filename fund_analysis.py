import os
import re
import json
import requests
from datetime import datetime

FUND_CODE = os.getenv("FUND_LIST", "022455")
ANSPIRE_KEY = os.getenv("ANSPIRE_API_KEYS", "").split(",")[0].strip()
SERVERCHAN_KEY = os.getenv("SERVERCHAN3_SENDKEY", "").strip()

FUND_NAME = "招商中证A500ETF联接A"


def get_fund_data(code):
    """获取场外基金历史净值数据"""
    url = f"https://fund.eastmoney.com/pingzhongdata/{code}.js"

    r = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=20
    )
    r.raise_for_status()

    text = r.text

    name_match = re.search(r'fS_name\s*=\s*"([^"]+)"', text)
    trend_match = re.search(
        r'Data_netWorthTrend\s*=\s*(\[[\s\S]*?\]);',
        text
    )

    name = name_match.group(1) if name_match else FUND_NAME
    trend = trend_match.group(1) if trend_match else "[]"

    try:
        trend_data = json.loads(trend)
    except Exception:
        trend_data = []

    return {
        "name": name,
        "code": code,
        "trend": trend_data[-30:]
    }


def get_a500_market():
    """获取中证A500盘中行情"""

    url = (
        "https://push2.eastmoney.com/api/qt/stock/get"
        "?secid=1.000510"
        "&fields=f58,f43,f169,f170,f57"
    )

    try:
        r = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15
        )

        data = r.json().get("data") or {}

        return {
            "name": data.get("f58", "中证A500"),
            "price": data.get("f43"),
            "change_pct": data.get("f170")
        }

    except Exception as e:
        return {
            "name": "中证A500",
            "price": None,
            "change_pct": None
        }


def ask_anspire(prompt):

    if not ANSPIRE_KEY:
        raise RuntimeError("ANSPIRE_API_KEYS 未配置")

    base_url = os.getenv(
        "ANSPIRE_LLM_BASE_URL",
        "https://open-gateway.anspire.cn/v6"
    ).rstrip("/")

    model = os.getenv(
        "ANSPIRE_LLM_MODEL",
        "deepseek-v3"
    )

    url = f"{base_url}/chat/completions"

    headers = {
        "Authorization": f"Bearer {ANSPIRE_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": """
你是一名专业的长期基金定投分析助手。

用户持有：
招商中证A500ETF联接A（022455）

用户计划：
每月定投1000元，长期持有。

你的任务不是预测短线涨跌，而是在每天14:20左右，
根据中证A500盘中表现、最近基金净值和市场环境，
判断今天是否适合执行额外加仓。

必须区分：
基金最终净值 ≠ 盘中估值。

如果当天基金最终净值尚未公布，必须明确说明。
不要编造基金当天净值。
"""
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.2
    }

    r = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=90
    )

    r.raise_for_status()

    return r.json()["choices"][0]["message"]["content"]


def send_wechat(title, content):

    if not SERVERCHAN_KEY:
        raise RuntimeError("SERVERCHAN3_SENDKEY 未配置")

    url = f"https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send"

    r = requests.post(
        url,
        data={
            "title": title,
            "desp": content
        },
        timeout=20
    )

    r.raise_for_status()


def main():

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    fund = get_fund_data(FUND_CODE)
    a500 = get_a500_market()

    prompt = f"""
现在时间：{now}

基金：
{fund["name"]}

基金代码：
{fund["code"]}

最近30个交易日基金净值数据：
{json.dumps(fund["trend"], ensure_ascii=False)}

中证A500盘中行情：
名称：{a500["name"]}
当前价格：{a500["price"]}
当前涨跌幅：{a500["change_pct"]}%

用户投资计划：
每月定投1000元。
长期持有。
可以接受正常市场波动。

请给出一份14:20左右的“今日加仓决策报告”。

必须包含：

### 1. 📊 今日市场
说明中证A500目前表现。

### 2. 💰 022455基金情况
说明最近已公布净值的表现。

### 3. 📈 短期趋势
分析最近5个、10个、20个交易日趋势。

### 4. ⚠️ 风险
指出目前主要风险。

### 5. 🎯 今日操作建议
必须从下面三个选项中选择一个：

【正常定投】
【可以适当加仓】
【今天不建议额外加仓】

### 6. 💰 金额建议
用户每月计划1000元。

如果判断适合额外加仓，可以给出建议金额，
但不得超过1000元。

### 7. 🧠 最终结论
用一句话明确告诉用户：

“今天14:20，我建议你……”。

特别注意：

- 022455是场外基金，不是股票。
- 不要把159338等其他ETF说成用户持有的基金。
- 不要编造当天尚未公布的基金净值。
- 盘中判断主要参考中证A500及相关市场表现。
- 这是长期定投，不建议因为一天涨跌频繁交易。
"""

    analysis = ask_anspire(prompt)

    report = f"""
# 📊 招商中证A500ETF联接A 定投决策

**基金：** {fund["name"]}
**代码：** {FUND_CODE}

**分析时间：** {now}

---

{analysis}

---

⚠️ 说明：
场外基金当天最终净值通常在收盘后公布。
本报告在14:20左右主要参考中证A500盘中表现及最近已公布基金净值，
用于辅助当天15:00前的定投/加仓决策。
"""

    print(report)

    send_wechat(
        "📊 022455 今日14:20加仓决策",
        report
    )


if __name__ == "__main__":
    main()
