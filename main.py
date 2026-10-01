import os
import time
import logging
import requests
import yfinance as yf
import google.generativeai as genai

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

STOCK_NAME_MAP = {
    "0056.TW": "元大高股息",
    "00878.TW": "國泰永續高股息",
    "00919.TW": "群益台灣精選高息",
    "00713.TW": "元大台灣高息低波",
    "0050.TW": "元大台灣50",
    "2330.TW": "台積電",
    "2317.TW": "鴻海",
    "2454.TW": "聯發科",
    "2409.TW": "友達",
    "3481.TW": "群創",
    "6116.TW": "彩晶",
    "4770.TW": "祥源",
    "NVDA": "輝達 (NVIDIA)",
    "AAPL": "蘋果 (Apple)",
    "TSLA": "特斯拉 (Tesla)",
}

def get_display_name(symbol: str) -> str:
    return STOCK_NAME_MAP.get(symbol.upper().strip(), symbol.upper().strip())

def send_telegram_message(bot_token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    try:
        res = requests.post(url, json=payload, timeout=15)
        res.raise_for_status()
    except Exception as e:
        logging.error(f"Telegram 推播失敗: {e}")

def analyze_batch_with_gemini(api_key: str, batch_data: list) -> list:
    """單次 API 呼叫，一次處理多檔股票"""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-3.8-flash')

    combined_text = ""
    for symbol, data in batch_data:
        display_name = get_display_name(symbol)
        combined_text += f"\n--- 【{display_name} ({symbol})】 ---\n{data}\n"

    prompt = f"""
你是一位專業的台灣證券分析師。請針對以下多檔股票數據分別進行簡短分析。

【語言與用語規範】
1. 必須全程使用【台灣繁體中文（zh-TW）】。
2. 財經術語：禁用「信息、信息速览、舆情情绪、大盘复盘、收益率」，採用「訊息/資訊、重點資訊速覽、市場情緒、大盤盤後分析、殖利率/報酬率」。
3. 請依照每檔股票獨立輸出以下格式，各股票間用「===」分隔。

【格式】
🟡 [股票名稱] ([代碼])

📰 重要資訊速覽
* 市場情緒：[簡短分析]
* 業績與籌碼預期：[簡短分析]

📊 技術面與操作建議
* 當前趨勢：[簡短分析]
* 操作重點：[簡短分析]

===

【股票數據清單】
{combined_text}
"""

    try:
        response = model.generate_content(prompt)
        # 依分隔符切分回傳結果
        reports = response.text.split("===")
        return [r.strip() for r in reports if r.strip()]
    except Exception as e:
        logging.error(f"Gemini 批量分析失敗: {e}")
        return [f"⚠️ 批量分析失敗：`{e}`"]

def main():
    gemini_key = os.getenv("GEMINI_API_KEY")
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    tg_chat_id = os.getenv("TELEGRAM_CHAT_ID")
    raw_stock_list = os.getenv("STOCK_LIST", "0056.TW")
    
    if not all([tg_token, tg_chat_id, gemini_key]):
        logging.error("缺少必要密鑰！")
        return

    stocks = [s.strip() for s in raw_stock_list.replace(";", ",").split(",") if s.strip()]
    
    # 抓取所有股票歷史資料
    collected_data = []
    for symbol in stocks:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="5d")
            if not hist.empty:
                summary = hist[['Open', 'High', 'Low', 'Close', 'Volume']].tail(3).to_string()
                collected_data.append((symbol, summary))
        except Exception as e:
            logging.error(f"抓取 {symbol} 失敗: {e}")

    # 以 5 檔股票為一組（Batch）打包發送
    batch_size = 5
    for i in range(0, len(collected_data), batch_size):
        batch = collected_data[i:i + batch_size]
        reports = analyze_batch_with_gemini(gemini_key, batch)
        
        for r in reports:
            send_telegram_message(tg_token, tg_chat_id, r)
            time.sleep(1)
            
        time.sleep(10) # 每批次間隔 10 秒

if __name__ == "__main__":
    main()
