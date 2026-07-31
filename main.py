import os
import sys
import requests
import yfinance as yf

# ==========================================
# 1. 抓取股票市場真實行情數據
# ==========================================
def fetch_stock_market_data(stock_id):
    """
    透過 yfinance 抓取台灣股票最新行情數據 (支援上市/上櫃)
    """
    # 預設加上台股上市代號 (.TW)
    ticker_symbol = f"{stock_id}.TW" if not stock_id.endswith((".TW", ".TWO")) else stock_id
    ticker = yf.Ticker(ticker_symbol)
    
    # 抓取最近 5 天資料 (避免遇到假日無資料)
    df = ticker.history(period="5d")
    
    # 若上市查無資料，嘗試上櫃代號 (.TWO)
    if df.empty or len(df) < 2:
        ticker_symbol = f"{stock_id}.TWO"
        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(period="5d")
    
    if df.empty or len(df) < 2:
        print(f"❌ 查無股票 {stock_id} 的行情資料，請確認代號是否正確。")
        return None

    # 取最新兩日資料計算價差與漲跌幅
    latest_row = df.iloc[-1]
    prev_row = df.iloc[-2]

    close_price = float(latest_row['Close'])
    prev_close = float(prev_row['Close'])
    
    change_price = close_price - prev_close
    change_pct = (change_price / prev_close) * 100

    return {
        "stock_id": stock_id,
        "close_price": close_price,
        "change_price": change_price,
        "change_pct": change_pct
    }

# ==========================================
# 2. 組合 LINE 訊息內容
# ==========================================
def format_stock_report(stock_id, close_price, change_price, change_pct, trend_signal="", conclusion=""):
    """
    組裝包含最新收盤價與今日漲跌幅的完整 LINE 報表訊息
    """
    if change_pct > 0:
        icon = "🔺"
        change_str = f"+{change_price:.2f} (+{change_pct:.2f}%)"
    elif change_pct < 0:
        icon = "🔻"
        change_str = f"{change_price:.2f} ({change_pct:.2f}%)"
    else:
        icon = "➖"
        change_str = "0.00 (0.00%)"

    message = (
        f"📊 【每日個股早報 - {stock_id}】\n"
        f"------------------------------\n"
        f"💰 最新收盤價：{close_price:,.2f} 元\n"
        f"📈 今日漲跌幅：{icon} {change_str}\n"
        f"------------------------------\n"
    )
    
    if trend_signal:
        message += f"🔹 趨勢訊號：{trend_signal}\n"
    if conclusion:
        message += f"💡 綜合評估：\n{conclusion}\n"

    return message

# ==========================================
# 3. 發送 LINE Message API 推播
# ==========================================
def send_line_push(text):
    """
    呼叫 LINE Messaging API 發送推播訊息給使用者
    """
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = os.getenv("USER_ID")

    if not token or not user_id:
        print("⚠️ 未正確設定 LINE_CHANNEL_ACCESS_TOKEN 或 USER_ID 環境變數！")
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

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            print("✅ LINE 訊息推播成功！")
        else:
            print(f"❌ LINE 發送失敗 ({res.status_code}): {res.text}")
    except Exception as e:
        print(f"❌ 發送 LINE 訊息時發生例外錯誤: {e}")

# ==========================================
# 4. 主程式執行邏輯
# ==========================================
if __name__ == "__main__":
    # 1. 讀取 GitHub Actions 傳入的 STOCK_ID (預設為 2330)
    raw_stock = os.getenv("STOCK_ID", "2330").strip()
    stock_id = raw_stock if raw_stock and raw_stock != "DEFAULT" else "2330"

    print(f"🚀 開始執行分析流程，目標標的：{stock_id}...")

    # 2. 抓取真實市場數據
    market_data = fetch_stock_market_data(stock_id)

    if market_data:
        # 3. 根據漲跌動態示範分析訊號 (此處可替換為你的量化模型邏輯/HorseFinder)
        if market_data['change_pct'] > 1.0:
            signal = "多頭強勢突破"
            conclusion = "短線放量上揚，均線多頭排列，可關注續強拉升機會。"
        elif market_data['change_pct'] < -1.0:
            signal = "空頭回檔修正"
            conclusion = "短線承壓拉回，建議觀察下檔支撐力道，靜待止跌訊號。"
        else:
            signal = "區間震盪整理"
            conclusion = "股價波動平緩，籌碼沉澱中，維持觀望或波段操作。"

        # 4. 格式化訊息內容
        report = format_stock_report(
            stock_id=market_data['stock_id'],
            close_price=market_data['close_price'],
            change_price=market_data['change_price'],
            change_pct=market_data['change_pct'],
            trend_signal=signal,
            conclusion=conclusion
        )

        # 5. 發送 LINE 訊息
        send_line_push(report)
    else:
        # 失敗通知
        error_msg = f"⚠️ 無法取得股票 {stock_id} 的最新行情，請檢查代號是否正確。"
        send_line_push(error_msg)
