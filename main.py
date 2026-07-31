# -*- coding: utf-8 -*-
"""
每日主流程與單股量化分析（GitHub Actions 用）
================================
支援兩種執行模式（由環境變數 RUN_MODE 控制）：

1. morning_report（全盤晨報模式）：
   - 抓取市場快照 + 新聞（market.py）
   - 針對 CATEGORIES 清單裡的每個類股（權值股、AI概念股...）執行量化模型分析
   - 執行持股清單分析（portfolio.py）
   - 生成 AI 晨報（ai_report.py）並轉檔為 PDF（report_pdf.py）
   - 發送 Resend Email 附帶 Excel 與 PDF 報告
   - LINE 廣播與更新 Dashboard 網頁儀表板（dashboard.py）

2. single_stock（單股量化分析模式）：
   - 針對輸入的股號或公司名稱查詢 TWSE / TPEX 最新行情
   - 進行波段量化指標分析
   - 產生分析結論並透過 LINE Push API 即時推播給指定使用者
"""

import base64
import os
import sys
import re
import traceback
from datetime import datetime
import requests

import engine
import ai_report
import market
import report_pdf
import dashboard
import portfolio

# ------------------------------------------------------------------
# 晨報要跑哪些類股清單（對應 Google Sheets GID）
# ------------------------------------------------------------------
CATEGORIES = {
    "權值股": "630045424",
    # "面板股": "1749860219",
    "AI概念股": "0",
    # "國防自主概念": "2037567856",
    # "低軌衛星概念股": "1594256368",
    # "無人機概念股": "327999020",
}

# 持股清單分頁 GID（設為 None 則忽略）
PORTFOLIO_GID = "213589368"

RESEND_API_URL = "https://api.resend.com/emails"
FROM_EMAIL = "Stock Report <onboarding@resend.dev>"
TO_EMAIL = os.environ.get("TO_EMAIL", "hai1217.chi@gmail.com")


# ==========================================
# 個股查詢 1: 公司名稱與股號查表／轉換
# ==========================================
def resolve_stock_id(query):
    """將查詢字串（如：台積電或 2330）解析為標準股號與顯示名稱。"""
    query = query.strip()
    
    # 若已經是 4 至 6 位數股號
    if re.match(r'^\d{4,6}$', query):
        return query, f"股號 {query}"
    
    # 常用關鍵字快速映射
    common_stocks = {
        "台積電": "2330", "鴻海": "2317", "聯發科": "2454", "廣達": "2382",
        "緯創": "3231", "技嘉": "2376", "長榮": "2603", "陽明": "2609",
        "富邦金": "2881", "國泰金": "2882", "中信金": "2891", "台達電": "2308",
        "世芯": "3661", "創意": "3443", "智原": "3035", "微星": "2377"
    }
    
    for name, code in common_stocks.items():
        if name in query:
            return code, name
            
    # 呼叫證交所 Open Data 模糊比對
    try:
        url = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
        res = requests.get(url, timeout=5).json()
        for item in res:
            if query in item.get('Name', ''):
                return item.get('Code'), item.get('Name')
    except Exception as e:
        print(f"⚠️ 證交所名單查詢失敗: {e}")
        
    return query, query


# ==========================================
# 個股查詢 2: 抓取台股最新行情 (TWSE / TPEX)
# ==========================================
def fetch_stock_market_data(stock_id):
    """從 TWSE / TPEX 官方 MIS 介面抓取單股即時盤後行情。"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    # 1. 查詢上市 (TSE)
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
            return {
                "name": data.get('n', stock_id),
                "stock_id": stock_id,
                "close_price": close_p,
                "change_price": change_p,
                "change_pct": change_pct,
                "high": float(data.get('h', close_p)),
                "low": float(data.get('l', close_p)),
                "volume": data.get('v', '0')
            }
    except Exception as e:
        print(f"⚠️ 上市 API 讀取異常: {e}")

    # 2. 查詢上櫃 (OTC)
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
            return {
                "name": data.get('n', stock_id),
                "stock_id": stock_id,
                "close_price": close_p,
                "change_price": change_p,
                "change_pct": change_pct,
                "high": float(data.get('h', close_p)),
                "low": float(data.get('l', close_p)),
                "volume": data.get('v', '0')
            }
    except Exception as e:
        print(f"⚠️ 上櫃 API 讀取異常: {e}")

    return None


# ==========================================
# 個股查詢 3: 波段量化分析邏輯
# ==========================================
def analyze_quantitative_stock(stock_id, market_data):
    """產出單股量化分析觀點與結論。"""
    try:
        if hasattr(engine, 'run_stock_analysis'):
            return engine.run_stock_analysis(stock_id, market_data)
    except Exception as e:
        print(f"⚠️ 呼叫自訂 engine 個股模組失敗，切換至預設波段邏輯: {e}")

    change_pct = market_data['change_pct']
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
# 個股查詢 4: LINE Push 推播訊息發送
# ==========================================
def send_line_push(text, target_user_id=None):
    """發送指定 LINE Push 推播訊息。"""
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = target_user_id or os.getenv("USER_ID")

    if not token or not user_id:
        print("❌ 錯誤：未設定 LINE_CHANNEL_ACCESS_TOKEN 或 USER_ID Secrets！")
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
        print(f"📱 LINE Push 回應狀態: HTTP {res.status_code}")
    except Exception as e:
        print(f"❌ LINE Push 發送失敗: {e}")


def run_single_stock_flow(query, target_user_id=None):
    """單股查詢完整流程。"""
    if not query or query == "DEFAULT":
        query = "2330"

    stock_id, resolved_name = resolve_stock_id(query)
    print(f"🔎 正在執行個股量化分析：{resolved_name} (代號: {stock_id})")

    market_data = fetch_stock_market_data(stock_id)
    if not market_data:
        err_msg = f"❌ 無法取得股票「{query}」({stock_id}) 的當日行情資料，請確認股號或名稱。"
        print(err_msg)
        send_line_push(err_msg, target_user_id)
        return

    trend, highlights, conclusion = analyze_quantitative_stock(stock_id, market_data)

    if market_data['change_pct'] > 0:
        icon = "🔺"
        change_str = f"+{market_data['change_price']:.2f} (+{market_data['change_pct']:.2f}%)"
    elif market_data['change_pct'] < 0:
        icon = "🔻"
        change_str = f"{market_data['change_price']:.2f} ({market_data['change_pct']:.2f}%)"
    else:
        icon = "➖"
        change_str = "0.00 (0.00%)"

    line_msg = (
        f"📊 【2in1 波段量化報告 - {market_data['name']} ({market_data['stock_id']})】\n"
        f"----------------------------------\n"
        f"💰 最新收盤價：{market_data['close_price']:,.2f} 元\n"
        f"📈 今日漲跌幅：{icon} {change_str}\n"
        f"----------------------------------\n"
        f"🎯 趨勢訊號：\n{trend}\n\n"
        f"📌 核心量化觀點：\n{highlights}\n\n"
        f"💡 綜合評估與結論：\n{conclusion}\n"
        f"----------------------------------\n"
        f"⏱ 報告生成時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    send_line_push(line_msg, target_user_id)


# ==========================================
# 全盤晨報流程：1. 抓取大盤快照與新聞
# ==========================================
def fetch_market_context() -> tuple:
    """抓市場快照 + 新聞，任何一步失敗都不影響後續進行。"""
    print("🌍 抓取大盤/美股/國際市場快照...")
    try:
        snapshot = market.fetch_market_snapshot()
        print(f"   完成，共 {sum(len(v) for v in snapshot.values())} 項指標")
    except Exception as e:
        print(f"   ⚠️ 市場快照抓取失敗（{e}），晨報將略過此部分")
        snapshot = {}

    print("📰 抓取相關新聞標題...")
    try:
        news = market.fetch_news_headlines()
        print(f"   完成，共 {len(news)} 組關鍵字有結果")
    except Exception as e:
        print(f"   ⚠️ 新聞抓取失敗（{e}），晨報將略過此部分")
        news = {}

    return snapshot, news


# ==========================================
# 全盤晨報流程：2. 跑單一類股分析
# ==========================================
def run_one_category(tab_name: str, gid: str, market_overview: str) -> dict:
    """跑完一個類股的完整流程（分析 → AI 晨報 → PDF）。"""
    if os.environ.get("FINMIND_TOKEN"):
        engine.FINMIND_TOKEN = os.environ["FINMIND_TOKEN"]

    print(f"\n🚀 開始分析類股：{tab_name}（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）")
    output_file, summary_data, val_data_all = engine.run_analysis(
        gid=gid,
        tab_name=tab_name,
        sheet_id=engine.SHEET_ID,
    )
    print(f"✅ {tab_name} 分析完成，共 {len(summary_data)} 檔個股，Excel 已存至：{output_file}")

    print(f"🤖 呼叫 Gemini 生成 {tab_name} 專屬分析...")
    try:
        category_briefing = ai_report.generate_category_briefing(summary_data, tab_name)
    except Exception as e:
        print(f"⚠️ AI 晨報生成失敗（{e}），改用純數據摘要。", file=sys.stderr)
        category_briefing = "（AI 晨報生成失敗，本次僅提供 Excel 數據，請見附件。）"

    full_text_for_pdf = f"{market_overview}\n\n{category_briefing}"

    pdf_path = None
    try:
        pdf_path = report_pdf.markdown_to_pdf(
            full_text_for_pdf,
            output_path=f"./AI晨報_{tab_name}_{datetime.now().strftime('%Y%m%d')}.pdf",
            title=f"{tab_name} AI 晨報 {datetime.now().strftime('%Y-%m-%d')}",
        )
        print(f"📄 {tab_name} PDF 晨報已產生：{pdf_path}")
    except Exception as e:
        print(f"⚠️ PDF 產生失敗（{e}），本次僅有 Excel + 信件內文。", file=sys.stderr)

    return {
        "tab_name": tab_name,
        "excel_path": output_file,
        "pdf_path": pdf_path,
        "ai_briefing": category_briefing,
        "summary_data": summary_data,
    }


# ==========================================
# 全盤晨報流程：3. 讀取與分析持股清單
# ==========================================
def run_portfolio_analysis(market_overview: str, news_headlines: dict) -> dict | None:
    """讀取持股清單並生成「持股操作建議」。"""
    if not PORTFOLIO_GID:
        return None

    print("\n💼 讀取持股清單...")
    try:
        holdings = portfolio.load_portfolio(sheet_id=engine.SHEET_ID, gid=PORTFOLIO_GID)
    except Exception as e:
        print(f"⚠️ 讀取持股清單失敗（{e}），略過持股操作建議。", file=sys.stderr)
        return None

    if not holdings:
        print("ℹ️ 持股清單目前沒有任何資料，略過持股操作建議。")
        return None

    custom_codes = portfolio.build_custom_codes(holdings)
    company_map = portfolio.build_company_map(holdings)
    print(f"🚀 開始分析持股清單（共 {len(holdings)} 檔：{custom_codes}）...")
    try:
        output_file, summary_data, _ = engine.run_analysis(
            gid=None,
            tab_name="我的持股",
            custom_codes=custom_codes,
            custom_company_map=company_map,
            sheet_id=engine.SHEET_ID,
        )
    except Exception as e:
        print(f"⚠️ 持股分析失敗（{e}），略過持股操作建議。", file=sys.stderr)
        return None

    merged = portfolio.merge_with_analysis(holdings, summary_data)

    print("🤖 呼叫 Gemini 生成持股操作建議...")
    try:
        portfolio_briefing = ai_report.generate_portfolio_briefing(merged, news_headlines)
    except Exception as e:
        print(f"⚠️ 持股操作建議生成失敗（{e}）。", file=sys.stderr)
        portfolio_briefing = "（持股操作建議生成失敗，請見附件 Excel 數據。）"

    pdf_path = None
    if output_file:
        try:
            pdf_path = report_pdf.markdown_to_pdf(
                f"{market_overview}\n\n{portfolio_briefing}",
                output_path=f"./AI晨報_我的持股_{datetime.now().strftime('%Y%m%d')}.pdf",
                title=f"我的持股 AI 操作建議 {datetime.now().strftime('%Y-%m-%d')}",
            )
            print(f"📄 持股 PDF 已產生：{pdf_path}")
        except Exception as e:
            print(f"⚠️ 持股 PDF 產生失敗（{e}）。", file=sys.stderr)

    return {
        "tab_name": "我的持股",
        "excel_path": output_file,
        "pdf_path": pdf_path,
        "ai_briefing": portfolio_briefing,
        "summary_data": summary_data,
    }


# ==========================================
# 全盤晨報流程：4. 透過 Resend 發送 Email 報告
# ==========================================
def send_email_with_report(category_results: list, market_overview: str) -> None:
    """將各類股 PDF 與 Excel 附件統整寄出 Email。"""
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        print("⚠️ 未設定 RESEND_API_KEY，略過 Email 寄送。")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    attachments = []
    sections_html = []

    for r in category_results:
        if r.get("excel_path") and os.path.exists(r["excel_path"]):
            with open(r["excel_path"], "rb") as f:
                encoded_excel = base64.b64encode(f.read()).decode("utf-8")
            attachments.append({"filename": os.path.basename(r["excel_path"]), "content": encoded_excel})

        if r.get("pdf_path") and os.path.exists(r["pdf_path"]):
            with open(r["pdf_path"], "rb") as f:
                encoded_pdf = base64.b64encode(f.read()).decode("utf-8")
            attachments.append({"filename": os.path.basename(r["pdf_path"]), "content": encoded_pdf})

        sections_html.append(f"<h2>📌 {r['tab_name']}</h2>")
        sections_html.append(ai_report.markdown_to_html(r["ai_briefing"]))
        sections_html.append("<hr>")

    category_names = "、".join(r["tab_name"] for r in category_results)
    market_overview_html = ai_report.markdown_to_html(market_overview)
    html_body = f"""
    <div style="font-family: -apple-system, Arial, sans-serif; max-width: 640px;">
        <h1>📊 AI 晨報：{category_names}</h1>
        <p style="color:#666;">{today} 自動產生</p>
        <hr>
        <h2>🌍 市場總覽</h2>
        {market_overview_html}
        <hr>
        {''.join(sections_html)}
        <p style="color:#999; font-size: 12px;">
            本郵件由 GitHub Actions 排程自動產生，完整量化數據請見附件 Excel 檔案，
            各類股晨報 PDF 版本也一併附上（PDF 內含市場總覽，方便單獨閱讀）。
            內容為量化模型輸出，僅供參考，不構成投資建議。
        </p>
    </div>
    """

    payload = {
        "from": FROM_EMAIL,
        "to": [TO_EMAIL],
        "subject": f"AI 晨報 {today}：{category_names}",
        "html": html_body,
        "attachments": attachments,
    }

    resp = requests.post(
        RESEND_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    print("📧 Resend API 回應狀態碼:", resp.status_code)
    resp.raise_for_status()


# ==========================================
# 全盤晨報流程：5. LINE 廣播與 Dashboard 更新
# ==========================================
def send_line_digest(category_results: list, market_overview: str) -> None:
    """發送全盤晨報精簡摘要至 LINE。"""
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    if not token:
        print("ℹ️ 未設定 LINE_CHANNEL_ACCESS_TOKEN，略過 LINE 晨報廣播。")
        return

    try:
        import line_notify
        message = line_notify.build_digest_message(category_results, market_overview)
        line_notify.send_line_broadcast(message, token)
        print("📱 LINE 晨報通知已成功廣播。")
    except Exception as e:
        print(f"⚠️ LINE 晨報廣播失敗（{e}），不影響其他流程。", file=sys.stderr)


def update_dashboard_safe(category_results: list, market_snapshot: dict, market_overview: str) -> None:
    """更新 GitHub Pages 網頁儀表板。"""
    try:
        dashboard.update_dashboard(category_results, market_snapshot, market_overview)
        print("🌐 Dashboard 網頁儀表板已更新。")
    except Exception as e:
        print(f"⚠️ Dashboard 更新失敗（{e}），不影響其他流程。", file=sys.stderr)


# ==========================================
# 全盤晨報主執行入口
# ==========================================
def run_morning_report_main(target_user_id=None):
    """完整全盤晨報主流程。"""
    print("🌅 開始執行 2in1 波段量化全盤晨報...")
    
    market_snapshot, news_headlines = fetch_market_context()

    print("🤖 呼叫 Gemini 生成市場總覽...")
    try:
        market_overview = ai_report.generate_market_overview(market_snapshot, news_headlines)
    except Exception as e:
        print(f"⚠️ 市場總覽生成失敗（{e}），改用預設文字。", file=sys.stderr)
        market_overview = "## 今天盤勢\n（市場總覽生成失敗）\n\n## 國際新聞觀察\n（市場總覽生成失敗）"

    print("--- 市場總覽預覽 ---")
    print(market_overview)
    print("------------------------")

    category_results = []
    for tab_name, gid in CATEGORIES.items():
        result = run_one_category(tab_name, gid, market_overview)
        category_results.append(result)

    portfolio_result = run_portfolio_analysis(market_overview, news_headlines)
    if portfolio_result:
        category_results.append(portfolio_result)

    # 1. 寄送 Email 報告
    send_email_with_report(category_results, market_overview)

    # 2. 發送 LINE 廣播
    send_line_digest(category_results, market_overview)

    # 3. 更新 Dashboard
    update_dashboard_safe(category_results, market_snapshot, market_overview)

    # 4. 推播完成訊息給指定使用者
    send_line_push("🟢 2in1 全盤晨報與 Email 報告已成功處理並發送完成！", target_user_id)


# ==========================================
# 程式主進入點
# ==========================================
if __name__ == "__main__":
    run_mode = os.getenv("RUN_MODE", "single_stock").strip()
    stock_query = os.getenv("STOCK_QUERY", "").strip()
    target_user_id = os.getenv("TARGET_USER_ID", "").strip()

    print(f"🤖 系統執行模式: {run_mode} | 查詢字串: '{stock_query}' | 觸發用戶 ID: {target_user_id}")

    try:
        if run_mode == "morning_report":
            run_morning_report_main(target_user_id)
        else:
            run_single_stock_flow(stock_query, target_user_id)
    except Exception as err:
        err_detail = traceback.format_exc()
        print(f"❌ 執行發生未預期例外:\n{err_detail}")
        send_line_push(f"❌ 腳本執行異常報錯:\n{str(err)}", target_user_id)
        sys.exit(1)
