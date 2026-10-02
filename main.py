import os
import time
import json
import logging
import requests
import yfinance as yf
import google.generativeai as genai

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

STOCK_NAME_MAP = {
    "0056.TW": "元大高股息",
    "00878.TW": "國泰永續高股息",
    "00919.TW": "群益台灣精選高息",
    "009826.TW": "貝萊德世界",
    "0050.TW": "元大台灣50",
    "2330.TW": "台積電",
    "5314.TW": "世紀",
    "2454.TW": "聯發科",
    "2409.TW": "友達",
    "3481.TW": "群創",
    "6116.TW": "彩晶",
    "4770.TW": "上品",
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
    """單次 API 呼叫，強迫回傳 JSON 格式以確保 100% 完整解析"""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-3.8-flash')

    target_symbols = [symbol for symbol, _ in batch_data]
    combined_text = ""
    for symbol, data in batch_data:
        display_name = get_display_name(symbol)
        combined_text += f"\n--- 【{display_name} ({symbol})】 ---\n{data}\n"

    prompt = f"""
你是一位專業的台灣證券分析師。
請針對傳入的 {len(target_symbols)} 檔股票（{', '.join(target_symbols)}）進行分析。

【重要任務】：
你必須為【每一檔股票】生成一份獨立報告，並以 JSON 陣列（JSON Array）格式回傳，格式如下：
[
  {{
    "symbol": "股票代碼",
    "report": "格式化後的 Markdown 報告內容"
  }}
]

【報告語氣與用語規範】
1. 全程使用【台灣繁體中文（zh-TW）】。
2. 禁用大陸用語（如：信息、舆情、复盘、收益率），採用「訊息/資訊、市場情緒、盤後分析、殖利率」。

【單檔 Markdown 內容格式 (寫在 report 欄位內)】：
🟡 [股票名稱] ([代碼])

📰 重要資訊速覽
* 市場情緒：[簡短分析]
* 業績與籌碼預期：[簡短分析]

📊 技術面與操作建議
* 當前趨勢：[簡短分析]
* 操作重點：[簡短分析]

【待分析數據】
{combined_text}
"""

    max_retries = 3
    for attempt in range(max_retries):
        try:
            # 強制要求 JSON 輸出模式
            response = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            data = json.loads(response.text)
            return [item.get("report", "") for item in data if item.get("report")]
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "ResourceExhausted" in error_str:
                if attempt < max_retries - 1:
                    logging.warning(f"觸發頻率限制 (429)，冷卻 20 秒...")
                    time.sleep(20)
                    continue
            logging.error(f"Gemini 批量分析解析失敗: {error_str}")
            return [f"⚠️ 分析失敗：`{error_str}`"]

def main():
    gemini_key = os.getenv("GEMINI_API_KEY")
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    tg_chat_id = os.getenv("TELEGRAM_CHAT_ID")
    raw_stock_list = os.getenv("STOCK_LIST", "0056.TW")
    
    if not all([tg_token, tg_chat_id, gemini_key]):
        logging.error("缺少必要密鑰！")
        return

    stocks = [s.strip() for s in raw_stock_list.replace(";", ",").split(",") if s.strip()]
    logging.info(f"📋 準備分析的 STOCK_LIST ({len(stocks)} 檔): {stocks}")
    
    collected_data = []
    for symbol in stocks:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="5d")
            if not hist.empty:
                summary = hist[['Open', 'High', 'Low', 'Close', 'Volume']].tail(3).to_string()
                collected_data.append((symbol, summary))
            else:
                logging.warning(f"⚠️ {symbol} 沒抓到歷史數據，使用預設代碼替代")
                collected_data.append((symbol, "無近期交易歷史數據"))
        except Exception as e:
            logging.error(f"抓取 {symbol} 失敗: {e}")
            collected_data.append((symbol, "數據抓取異常"))

    # 以 3~5 檔為一組做 Batch 打包
    batch_size = 4
    for i in range(0, len(collected_data), batch_size):
        batch = collected_data[i:i + batch_size]
        reports = analyze_batch_with_gemini(gemini_key, batch)
        
        for r in reports:
            send_telegram_message(tg_token, tg_chat_id, r)
            time.sleep(1)
            
        time.sleep(15) # 批次間隔冷卻

if __name__ == "__main__":
    main()
