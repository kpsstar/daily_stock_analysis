import os
import time
import logging
import requests
import yfinance as yf
import google.generativeai as genai

# 設定 Logging 紀錄
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 1. 常見台股與美股中文名稱對照表
STOCK_NAME_MAP = {
    "0056.TW": "元大高股息",
    "00878.TW": "國泰永續高股息",
    "00919.TW": "群益台灣精選高息",
    "00713.TW": "元大台灣高息低波",
    "0050.TW": "元大台灣50",
    "2330.TW": "台積電",
    "2317.TW": "鴻海",
    "2454.TW": "聯發科",
    "NVDA": "輝達 (NVIDIA)",
    "AAPL": "蘋果 (Apple)",
    "TSLA": "特斯拉 (Tesla)",
    "MSFT": "微軟 (Microsoft)",
    "AMZN": "亞馬遜 (Amazon)",
    "VOO": "Vanguard S&P 500 ETF",
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

# 2. 呼叫 Gemini AI (帶有錯誤捕捉增強)
def analyze_stock_with_gemini(api_key: str, symbol: str, stock_data: str) -> str:
    display_name = get_display_name(symbol)
    
    if not api_key:
        return f"🟡 {display_name} ({symbol})\n\n⚠️ 未讀取到 GEMINI_API_KEY，請檢查 GitHub Secrets。"

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""
你是一位專業的台灣證券分析師。請根據以下【{display_name} ({symbol})】的近期數據進行簡短分析。

【語言與用語嚴格規範】
1. 必須全程使用【台灣繁體中文（zh-TW）】回答，嚴禁使用簡體字。
2. 財經術語規範：
   - ❌ 禁用：信息、信息速览、舆情情绪、大盘复盘、收益率
   - ✅ 採用：訊息/資訊、重點資訊速覽、市場情緒、大盤盤後分析、殖利率/報酬率
3. 使用台灣全形標點符號。

【格式】
🟡 {display_name} ({symbol})

📰 重要資訊速覽
* 市場情緒：[簡短分析]
* 業績與籌碼預期：[簡短分析]

📊 技術面與操作建議
* 當前趨勢：[簡短分析]
* 操作重點：[簡短分析]

【數據】
{stock_data}
"""
        response = model.generate_content(prompt)
        return response.text

    except Exception as e:
        # 印出詳細錯誤至 Log，並把錯誤訊息直接回傳給 Telegram
        error_msg = f"{type(e).__name__}: {str(e)}"
        logging.error(f"Gemini API 呼叫失敗 ({symbol}): {error_msg}")
        return f"🟡 {display_name} ({symbol})\n\n⚠️ AI 分析失敗\n錯誤原因：`{error_msg}`"

# 3. 主程序
def main():
    gemini_key = os.getenv("GEMINI_API_KEY")
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    tg_chat_id = os.getenv("TELEGRAM_CHAT_ID")
    raw_stock_list = os.getenv("STOCK_LIST", "0056.TW")
    
    if not all([tg_token, tg_chat_id]):
        logging.error("缺少必要密鑰！請檢查 Secrets 設定 (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)")
        return

    stocks = [s.strip() for s in raw_stock_list.replace(";", ",").split(",") if s.strip()]
    
    for symbol in stocks:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="5d")
            
            if hist.empty:
                continue
                
            stock_summary = hist[['Open', 'High', 'Low', 'Close', 'Volume']].tail(3).to_string()
            report = analyze_stock_with_gemini(gemini_key, symbol, stock_summary)
            send_telegram_message(tg_token, tg_chat_id, report)
            
            # 冷卻 3 秒避開 Rate Limit
            time.sleep(3)
            
        except Exception as e:
            logging.error(f"處理 {symbol} 出錯: {e}")

if __name__ == "__main__":
    main()
