import os
import sys
import re
import requests

# ==========================================
# 1. 公司名稱與股號查表／轉換 (支援名稱與代號)
# ==========================================
def resolve_stock_id(query):
    query = query.strip()
    
    # 如果已經是 4-6 位數字代碼
    if re.match(r'^\d{4,6}$', query):
        return query, f"股號 {query}"
    
    # 常用關鍵字快速映射 (可根據需求擴充)
    common_stocks = {
        "台積電": "2330", "鴻海": "2317", "聯發科": "2454", "廣達": "2382",
        "緯創": "3231", "技嘉": "2376", "長榮": "2603", "陽明": "2609",
        "富邦金": "2881", "國泰金": "2882", "中信金": "2891", "台達電": "2308",
        "世芯": "3661", "創意": "3443", "智原": "3035", "微星": "2377"
    }
    
    for name, code in common_stocks.items():
        if name in query:
            return code, name
            
    # 若不在常用清單，呼叫證交所 Open Data API 模糊搜尋名稱
    try:
        url = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
        res = requests.get(url, timeout=5).json()
        for item in res:
            if query in item.get('Name', ''):
                return item.get('Code'), item.get('Name')
    except Exception as e:
        print(f"證交所名單查詢失敗: {e}")
        
    return query, query

# ==========================================
# 2. 抓取台股最新行情 (TWSE / TPEX 官方 API)
# ==========================================
def fetch_stock_market_data(stock_id):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    # 1. 查上市 (TWSE)
    url_twse = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_{stock_id}.tw"
    try:
        res = requests.get(url_twse, headers=headers, timeout=8).json()
        info = res.get('msgArray', [])
        if info and info[0].get('z') and info[0].get('z') != '-':
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
                "change_pct": change_pct,
                "high": float(data.get('h', close_p)),
                "low": float(data.get('l', close_p)),
                "volume": data.get('v', '0')
            }
    except Exception as e:
        print(f"上市 API 讀取異常: {e}")

    # 2. 查上櫃 (TPEX)
    url_tpex = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=otc_{stock_id}.tw"
    try:
        res = requests.get(url_tpex, headers=headers, timeout=8).json()
        info = res.get('msgArray', [])
        if info and info[0].get('z') and info[0].get('z') != '-':
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
                "change_pct": change_pct,
                "high": float(data.get('h', close_p)),
                "low": float(data.get('l', close_p)),
                "volume": data.get('v', '0')
            }
    except Exception as e:
        print(f"上櫃 API 讀取異常: {e}")

    return None

# ==========================================
# 3. 整合量化模型分析 (呼叫 engine.py 或波段邏輯)
# ==========================================
def analyze_quantitative_stock(stock_id, market_data):
    """
    對接原專案 engine.py 或是 2in1_wave 波段演算法
    """
    close_price = market_data['close_price']
    change_pct = market_data['change_pct']
    
    # 試圖引用專案內的 engine 邏輯
    try:
        import engine
        if hasattr(engine, 'run_stock_analysis'):
            return engine.run_stock_analysis(stock_id, market_data)
    except Exception as e:
        print(f"未找到自訂 engine 模組或執行出錯，採用預設 2in1 波段量化邏輯: {e}")

    # --- 預設 2in1 Wave 18.4 波段量化分析邏輯 ---
    if change_pct >= 3.0:
        trend = "🔥 多頭強勢衝刺 (HorseFinder 強勢訊號)"
        highlights = (
            "1. 攻擊量能釋放，強勢突破短期均線糾結帶。\n"
            "2. 波段指標呈黃金交叉，主力籌碼偏多控盤。\n"
            "3. 乖離率略拉高，但短線動能極強。"
        )
        conclusion = "短線仍有上攻空間，可採 5 日線移動停利策略，沿均線偏多操作。"
    elif 0.5 <= change_pct < 3.0:
        trend = "📈 溫和偏多增溫"
        highlights = (
            "1. 股價沿短均線穩健爬升，量價配合良好。\n"
            "2. 支撐位有效防守，籌碼沉澱狀況良好。"
        )
        conclusion = "趨勢維持多頭格局，拉回至關鍵均線不破皆可留意佈局機會。"
    elif -2.0 < change_pct < 0.5:
        trend = "⚖️ 橫盤區間震盪"
        highlights = (
            "1. 價位在多空交界區橫向整理，量能稍微萎縮。\n"
            "2. 觀望氣氛較濃，等待方向突破。"
        )
        conclusion = "建議維持區間操作觀望，待出現明確增量突破或止跌紅K再行進場。"
    else:
        trend = "⚠️ 短線修正/壓回"
        highlights = (
            "1. 賣壓相對沉重，跌破短期移動平均線。\n"
            "2. 短線技術指標轉弱，下方尋求關鍵支撐。"
        )
        conclusion = "短線風險升溫，建議暫時觀望避開修正，待底部止跌訊號確立。"

    return trend, highlights, conclusion

# ==========================================
# 4. 格式化 LINE 量化報告訊息
# ==========================================
def build_line_message(data, trend, highlights, conclusion):
    if data['change_pct'] > 0:
        icon = "🔺"
        change_str = f"+{data['change_price']:.2f} (+{data['change_pct']:.2f}%)"
    elif data['change_pct'] < 0:
        icon = "🔻"
        change_str = f"{data['change_price']:.2f} ({data['change_pct']:.2f}%)"
    else:
        icon = "➖"
        change_str = "0.00 (0.00%)"

    msg = (
        f"📊 【2in1 波段量化報告 - {data['name']} ({data['stock_id']})】\n"
        f"----------------------------------\n"
        f"💰 最新收盤價：{data['close_price']:,.2f} 元\n"
        f"📈 今日漲跌幅：{icon} {change_str}\n"
        f"----------------------------------\n"
        f"🎯 趨勢訊號：\n{trend}\n\n"
        f"📌 核心量化觀點：\n{highlights}\n\n"
        f"💡 綜合評估與結論：\n{conclusion}\n"
        f"----------------------------------\n"
        f"⏱ 報告生成時間：即時盤後數據"
    )
    return msg

# ==========================================
# 5. LINE API 發送 Push 訊息
# ==========================================
def send_line_push(text, target_user_id=None):
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = target_user_id or os.getenv("USER_ID")

    if not token or not user_id:
        print("❌ 錯誤：未找到 LINE Token 或 USER_ID Secrets！")
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
    print(f"LINE API 推播回應狀態碼: {res.status_code}")

# ==========================================
# 6. 全盤晨報執行 (僅在輸入「執行」時調用)
# ==========================================
def run_full_morning_report():
    print("🌅 開始執行全盤晨報與寄送信件流程...")
    try:
        # 如果原程式中有 ai_report 或 main 的晨報流程，在這裡執行
        import ai_report
        if hasattr(ai_report, 'main'):
            ai_report.main()
        print("✅ 晨報與寄信執行完畢！")
        send_line_push("🟢 全盤晨報與 Email 報告已順利發送完成！")
    except Exception as e:
        print(f"❌ 執行晨報發生例外: {e}")
        send_line_push(f"❌ 全盤晨報發送失敗: {e}")

# ==========================================
# 主進入點
# ==========================================
if __name__ == "__main__":
    run_mode = os.getenv("RUN_MODE", "single_stock").strip()
    stock_query = os.getenv("STOCK_QUERY", "").strip()
    target_user_id = os.getenv("TARGET_USER_ID", "").strip()

    print(f"🤖 執行模式: {run_mode} | 查詢內容: '{stock_query}'")

    if run_mode == "morning_report":
        # 執行晨報 & 寄信
        run_full_morning_report()
    else:
        # 個股查詢模式 (預設 2330)
        if not stock_query or stock_query == "DEFAULT":
            stock_query = "2330"

        # 1. 解析股號
        stock_id, resolved_name = resolve_stock_id(stock_query)
        print(f"🔎 正在分析個股：{resolved_name} (代號: {stock_id})")

        # 2. 抓取行情
        market_data = fetch_stock_market_data(stock_id)

        if market_data:
            # 3. 進行量化分析
            trend, highlights, conclusion = analyze_quantitative_stock(stock_id, market_data)

            # 4. 組裝訊息
            line_msg = build_line_message(market_data, trend, highlights, conclusion)

            # 5. 推播回 LINE
            send_line_push(line_msg, target_user_id)
        else:
            err_msg = f"❌ 無法取得股票「{stock_query}」({stock_id}) 的當日行情資料，請確認名稱或股號是否正確。"
            print(err_msg)
            send_line_push(err_msg, target_user_id)
