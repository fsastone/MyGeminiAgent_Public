import os
import google.generativeai as genai
from dotenv import load_dotenv

# 1. 載入環境變數 (安全地讀取密碼)
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

# 2. 設定 Gemini
genai.configure(api_key=api_key)

# 3. 選擇模型 (以 2.5 Flash-lite 測試速度)
model = genai.GenerativeModel('gemini-2.5-flash-lite')

# 4. 發送測試訊息 (Debug 點)
print("正在呼叫 Gemini 大腦...")
try:
    response = model.generate_content("你好，請用一句話形容你自己。")
    print("Gemini 回應：", response.text)
except Exception as e:
    print("發生錯誤：", e)