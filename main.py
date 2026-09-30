import os
import json
import logging
import requests
import yfinance as yf
import google.generativeai as genai

# 設定 Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ---------------------------------------------------------
# 1. 台股與美股中文名稱對照表
# ---------------------------------------------------------
STOCK_NAME_MAP = {
    # 熱門台股 ETF / 個股
    "0056.TW": "元大高股息",
    "00878.TW": "國泰永續高股息",
    "00919.TW": "群益台灣精選高息",
    "00713.TW": "元大台灣高息低波",
    "0050.TW": "元大台灣50",
    "2330.TW": "台積電",
    "2317.TW": "鴻海",
    "2454.TW": "聯發科",
    
    # 熱門美股
    "NVDA": "輝達 (NVIDIA)",
    "AAPL": "蘋果 (Apple)",
    "TSLA": "特斯拉 (Tesla)",
    "MSFT": "微軟 (Microsoft)",
    "AMZN": "亞馬遜 (Amazon)",
    "GOOGL": "Alphabet (Google)",
    "VOO": "Vanguard S&P 500 ETF",
    "QQQ": "Invesco QQQ Trust",
}

def get_display_name(symbol: str) -> str:
    """取得乾淨的中文股票名稱"""
    symbol_upper = symbol.upper().strip()
    return STOCK_NAME_MAP.get(symbol_upper, symbol_upper)

# ---------------------------------------------------------
# 2. Telegram 發送訊息函數
# ---------------------------------------------------------
def send_telegram_message(bot_token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        logging.info("Telegram 訊息發送成功！")
    except Exception as e:
        logging.error(f"Telegram 推播失敗: {e}")

# ---------------------------------------------------------
# 3. 呼叫 Gemini AI 進行繁體中文分析
# ---------------------------------------------------------
def analyze_stock_with_gemini(api_key: str, symbol: str, stock_data: str) -> str:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    display_name = get_display_name(symbol)
    
    # 強制繁體中文與台灣財經習慣用語 Prompt
    prompt = f"""
你是一位專業的台灣證券分析師。請根據以下【{display_name} ({symbol})】的近期股市數據，進行簡明扼要的每日分析。

【語言與用語嚴格規範】
1. 必須全程使用【台灣繁體中文（zh-TW）】回答，嚴禁出現任何簡體字與中國大陸用語。
2. 財經術語對照標準：
   - ❌ 禁用：信息、信息速览、舆情情绪、大盘复盘、收益率、股份
   - ✅ 採用：訊息/資訊、重點資訊速覽、市場情緒、大盤盤後分析、殖利率/報酬率、股票
3. 使用台灣標準全形標點符號（，。！？）。

【輸出格式範例】
🟡 {display_name} ({symbol})

📰 重要資訊速覽
* 市場情緒：[簡短分析]
* 業績與籌碼預期：[簡短分析]

📊 技術面與操作建議
* 當前趨勢：[簡短分析]
* 操作重點：[簡短分析]

【股市數據】
{stock_data}
"""
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        logging.error(f"Gemini API 分析失敗: {e}")
        return f"🟡 {display_name} ({symbol})\n\n⚠️ AI 分析產生失敗，請檢查 API Key 或配額。"

# ---------------------------------------------------------
# 4. 主執行邏輯
# ---------------------------------------------------------
def main():
    # 讀取環境變數
    gemini_key = os.getenv("GEMINI_API_KEY")
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    tg_chat_id = os.getenv("TELEGRAM_CHAT_ID")
    raw_stock_list = os.getenv("STOCK_LIST", "0056.TW")
    
    if not all([gemini_key, tg_token, tg_chat_id]):
        logging.error("缺少必要密鑰！請確認 Secrets 設定 (GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)")
        return

    # 解析股票清單 (支援逗號或分號分隔)
    stocks = [s.strip() for s in raw_stock_list.replace(";", ",").split(",") if s.strip()]
    
    logging.info(f"準備分析的股票清單: {stocks}")
    
    for symbol in stocks:
        logging.info(f"正在抓取 {symbol} 的數據...")
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="5d")
            
            if hist.empty:
                logging.warning(f"無法取得 {symbol} 的數據，跳過。")
                continue
                
            # 將最後幾天的數據整理成簡短字串
            stock_summary = hist[['Open', 'High', 'Low', 'Close', 'Volume']].tail(3).to_string()
            
            # 開始 AI 分析
            logging.info(f"正在讓 Gemini 分析 {symbol}...")
            report = analyze_stock_with_gemini(gemini_key, symbol, stock_summary)
            
            # 發送 Telegram 通知
            send_telegram_message(tg_token, tg_chat_id, report)
            
        except Exception as e:
            logging.error(f"處理 {symbol} 時發生錯誤: {e}")

if __name__ == "__main__":
    main()
