import os
import sys
import requests

# ==========================================
# 1. 抓取台股最新行情 (使用 TWSE / TPEX 官方 API，防止 GitHub IP 被擋)
# ==========================================
def get_tw_stock_data(stock_id):
    """
    直接呼叫證交所/櫃買中心官方 API 取得最新收盤價與漲跌
    """
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    # 先查上市 (TWSE)
    url_twse = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_{stock_id}.tw"
    try:
        res = requests.get(url_twse, headers=headers, timeout=8).json()
        info = res.get('msgArray', [])
        if info and info[0].get('z') != '-':
            data = info[0]
            close_p = float(data['z']) # 當日收盤/最新價
            prev_p = float(data['y'])  # 昨收價
            change_p = close_p - prev_p
            change_pct = (change_p / prev_p) * 100
            name = data.get('n', stock_id)
            return {
                "name": name,
                "stock_id": stock_id,
                "close_price": close_p,
                "change_price": change_p,
                "change_pct": change_pct
            }
    except Exception as e:
        print(f"上市 API 讀取異常: {e}")

    # 若上市沒抓到，查上櫃 (TPEX)
    url_tpex = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=otc_{stock_id}.tw"
    try:
        res = requests.get(url_tpex, headers=headers, timeout=8).json()
        info = res.get('msgArray', [])
        if info and info[0].get('z') != '-':
            data = info[0]
            close_p = float(data['z'])
            prev_p = float(data['y'])
            change_p = close_p - prev_p
            change_pct = (change_p / prev_p) * 100
            name = data.get('n', stock_id)
            return {
                "name": name,
                "stock_id": stock_id,
                "close_price": close_p,
                "change_price": change_p,
                "change_pct": change_pct
            }
    except Exception as e:
        print(f"上櫃 API 讀取異常: {e}")

    return None

# ==========================================
# 2. 量化模型計算 logic (可在此對接你的 HorseFinder / 2in1 波段邏輯)
# ==========================================
def run_quantitative_analysis(stock_id, market_data):
    """
    在這裡運算你的量化指標/HorseFinder模型，並產生核心重點與結論
    """
    close_price = market_data['close_price']
    change_pct = market_data['change_pct']

    # --- 這裡替換/插入你的 HorseFinder / 波段量化分析 logic ---
    if change_pct >= 2.0:
        signal = "🔥 多頭強勢發動 (HorseFinder 轉強)"
        summary = "1. 成交量同步放大，突破短線整理平台。\n2. 均線呈多頭排列，主力籌碼偏多控盤。"
        conclusion = "短線具強勢上攻動能，可留意拉回不破 5 日線之加碼點。"
    elif change_pct <= -2.0:
        signal = "⚠️ 空頭修正訊號"
        summary = "1. 短線跌破重要支撐均線。\n2. 賣壓相對沉重，需注意乖離過大疑慮。"
        conclusion = "建議暫時觀望，待出現底部止跌紅K訊號後再行佈局。"
    else:
        signal = "⚖️ 區間沉澱整理"
        summary = "1. 股價於小幅波動區間盤整。\n2. 量能收縮，等待新一波方向確立。"
        conclusion = "籌碼沉澱中，可維持區間觀望策略。"

    return signal, summary, conclusion

# ==========================================
# 3. 組裝 LINE 推播訊息
# ==========================================
def format_stock_report(data, signal, summary, conclusion):
    if data['change_pct'] > 0:
        icon = "🔺"
        change_str = f"+{data['change_price']:.2f} (+{data['change_pct']:.2f}%)"
    elif data['change_pct'] < 0:
        icon = "🔻"
        change_str = f"{data['change_price']:.2f} ({data['change_pct']:.2f}%)"
    else:
        icon = "➖"
        change_str = "0.00 (0.00%)"

    message = (
        f"📊 【個股量化早報 - {data['name']} ({data['stock_id']})】\n"
        f"------------------------------\n"
        f"💰 最新收盤價：{data['close_price']:,.2f} 元\n"
        f"📈 今日漲跌幅：{icon} {change_str}\n"
        f"------------------------------\n"
        f"🔹 趨勢訊號：\n{signal}\n\n"
        f"📌 核心觀察重點：\n{summary}\n\n"
        f"💡 綜合評估與結論：\n{conclusion}"
    )
    return message

# ==========================================
# 4. 發送 LINE Message
# ==========================================
def send_line_push(text):
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = os.getenv("USER_ID")

    if not token or not user_id:
        print("❌ 未抓取到 LINE Token 或 USER_ID，請檢查 GitHub Secrets 設定！")
        return

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": text}]
    }
    res = requests.post(url, json=payload, headers=headers, timeout=10)
    print(f"LINE API 回應狀態碼: {res.status_code}")

# ==========================================
# 主流程
# ==========================================
if __name__ == "__main__":
    # 接收 GitHub Actions 傳入的參數，預設 2330
    stock_id = os.getenv("STOCK_ID", "2330").strip()
    if stock_id == "DEFAULT" or not stock_id:
        stock_id = "2330"

    print(f"🚀 開始執行個股量化報告，目標：{stock_id}")

    # 1. 抓取行情數據
    market_data = get_tw_stock_data(stock_id)

    if market_data:
        # 2. 進行量化運算
        signal, summary, conclusion = run_quantitative_analysis(stock_id, market_data)

        # 3. 組合訊息
        report_text = format_stock_report(market_data, signal, summary, conclusion)

        # 4. 推播至 LINE
        send_line_push(report_text)
    else:
        error_text = f"❌ 無法取得股票 [{stock_id}] 的當日行情資料，請確認股號是否正確。"
        print(error_text)
        send_line_push(error_text)
