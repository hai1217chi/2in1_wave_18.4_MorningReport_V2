# -*- coding: utf-8 -*-
"""
持股清單模組
=============
讀取 Google Sheet 的「持股清單」分頁（gid=213589368），欄位配置：
    A欄 = 股號（可能含 .TW/.TWO 後綴，也可能沒有）
    B欄 = 公司名稱
    C欄 = 類股
    D欄 = 買入價格

把持股清單當成一組「自選股」，交給 engine.run_analysis(custom_codes=...) 分析
（跟 app.py 裡「自選股（自行輸入股號）」用的是同一條路徑），
這樣不管持股屬於哪個類股、有沒有在今天的 CATEGORIES 清單裡跑過，都能拿到最新的量化數據，
不用去猜測、比對「今天有沒有剛好分析到這檔股票」。
"""

import pandas as pd


def load_portfolio(sheet_id: str, gid: str = "213589368") -> list:
    """從 Google Sheet 讀取持股清單，回傳 [{"raw_ticker", "stock_id", "company", "category", "buy_price"}, ...]"""
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    try:
        print(f"🔗 正在從 Google Sheet 載入持股清單 (gid={gid})...")
        df = pd.read_csv(url, header=0)
    except Exception as e:
        print(f"❌ 無法讀取持股清單：{e}")
        return []

    holdings = []
    for _, row in df.iterrows():
        raw_id = str(row.iloc[0]).strip() if len(row) > 0 else ""
        if not raw_id or raw_id.lower() == "nan":
            continue

        company = str(row.iloc[1]).strip() if len(row) > 1 and str(row.iloc[1]).lower() != "nan" else ""
        category = str(row.iloc[2]).strip() if len(row) > 2 and str(row.iloc[2]).lower() != "nan" else ""

        buy_price = None
        if len(row) > 3:
            try:
                buy_price = float(row.iloc[3])
            except (ValueError, TypeError):
                buy_price = None

        stock_id = raw_id.replace(".TW", "").replace(".TWO", "")
        holdings.append({
            "raw_ticker": raw_id,
            "stock_id": stock_id,
            "company": company,
            "category": category,
            "buy_price": buy_price,
        })

    print(f"✅ 成功讀取到 {len(holdings)} 檔持股")
    return holdings


def build_custom_codes(holdings: list) -> str:
    """把持股清單組成 engine.run_analysis(custom_codes=...) 需要的逗號分隔字串。"""
    return ",".join(h["raw_ticker"] for h in holdings if h.get("raw_ticker"))


def merge_with_analysis(holdings: list, summary_data: list) -> list:
    """
    把持股的買入價格，跟本次量化分析結果（用 stock_id 對應）合併，
    算出未實現損益 %。找不到對應分析結果的持股（例如流動性不足被引擎篩掉）
    會標記 matched=False，不會中斷整體流程，AI 那邊會據實說明「本次未涵蓋」。
    """
    by_id = {d.get("stock_id"): d for d in summary_data}
    merged = []
    for h in holdings:
        analysis = by_id.get(h["stock_id"])
        if not analysis:
            merged.append({**h, "matched": False})
            continue

        item = {**h, **analysis, "matched": True}
        current_price = analysis.get("current_price")
        if h.get("buy_price") and current_price:
            item["unrealized_pnl_pct"] = round((current_price / h["buy_price"] - 1) * 100, 2)
        merged.append(item)
    return merged
