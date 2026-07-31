import os
import requests
import yfinance as yf

# ==========================================
# 1. 股票名稱轉代號 (Yahoo Search API)
# ==========================================
def resolve_stock_id(query):
    """
    判斷輸入的是代號還是中文名稱。
    如果是中文，透過 Yahoo Search API 找回對應的台股代號。
    """
    query = str(query).strip()
    
    # 如果已經是 4 位純數字，直接回傳
    if query.isdigit() and len(query) == 4:
        return query
        
    # 如果是中文名稱，去 Yahoo 查代碼
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=5&country=Taiwan"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            quotes = res.json().get('quotes', [])
            for q in quotes:
                symbol = q.get('symbol', '')
                # 確保只抓台灣上市(.TW)或上櫃(.TWO)的股票
                if symbol.endswith('.TW') or symbol.endswith('.TWO'):
                    return symbol.split('.')[0]
    except Exception as e:
        print(f"⚠️ 名稱轉換代碼失敗: {e}")
        
    return None

# ==========================================
# 2. 抓取股票市場真實行情數據
# ==========================================
def fetch_stock_market_data(stock_id):
    ticker_symbol = f"{stock_id}.TW" if not stock_id.endswith((".TW", ".TWO")) else stock_id
    ticker = yf.Ticker(ticker_symbol)
    
    df = ticker.history(period="5d")
    
    if df.empty or len(df) < 2:
        ticker_symbol = f"{stock_id}.TWO"
        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(period="5d")
    
    if df.empty or len(df) < 2:
        return None

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
# 3. 組合 LINE 訊息內容
# ==========================================
def format_stock_report(original_query, stock_id, close_price, change_price, change_pct, trend_signal="", conclusion=""):
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
        f"📊 【個股量化早報 - {original_query} ({stock_id})】\n"
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
# 4. 發送 LINE Message API 推播
# ==========================================
def send_line_push(text):
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = os.getenv("USER_ID")
    if not token or not user_id:
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
    requests.post(url, json=payload, headers=headers, timeout=10)

# ==========================================
# 5. 主程式執行邏輯
# ==========================================
if __name__ == "__main__":
    # 接收從 LINE 傳過來的關鍵字 (可能是 6414 也可能是 緯穎)
    raw_query = os.getenv("STOCK_ID", "2330").strip()
    
    # 將中文名稱轉換為台股代碼
    stock_id = resolve_stock_id(raw_query)

    if not stock_id:
        send_line_push(f"❌ 查無此股票：「{raw_query}」，請確認名稱或代號是否正確。")
        exit()

    print(f"🚀 目標標的：{raw_query} -> 對應代碼: {stock_id}...")

    # 抓取真實市場數據
    market_data = fetch_stock_market_data(stock_id)

    if market_data:
        # 示範量化分析訊號 (此處可替換為你的 HorseFinder 邏輯)
        if market_data['change_pct'] > 1.0:
            signal = "多頭強勢突破"
            conclusion = "短線放量上揚，均線多頭排列，可關注續強拉升機會。"
        elif market_data['change_pct'] < -1.0:
            signal = "空頭回檔修正"
            conclusion = "短線承壓拉回，建議觀察下檔支撐力道，靜待止跌訊號。"
        else:
            signal = "區間震盪整理"
            conclusion = "股價波動平緩，籌碼沉澱中，維持觀望或波段操作。"

        report = format_stock_report(
            original_query=raw_query,
            stock_id=market_data['stock_id'],
            close_price=market_data['close_price'],
            change_price=market_data['change_price'],
            change_pct=market_data['change_pct'],
            trend_signal=signal,
            conclusion=conclusion
        )

        send_line_push(report)
    else:
        send_line_push(f"⚠️ 無法取得股票 {stock_id} ({raw_query}) 的最新行情。")
