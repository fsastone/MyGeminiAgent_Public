# main.py
import os
import re
import logging
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
import google.generativeai as genai

# 引入重構後的模組
from services.gemini_ai import initialize_gemini
from tools import (
    add_calendar_event, update_user_profile, get_user_profile, read_sheet_data,
    add_todo_task, get_todo_tasks, log_workout_result, get_upcoming_events,
    save_to_inbox, get_current_solar_term, get_weather_forecast,
    add_recipe, get_unread_inbox, mark_inbox_as_read, scrape_web_content,
    log_health_status
)

# 全域設定
load_dotenv()
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

user_sessions = {}
flask_app = Flask(__name__)

# 定義工具列表 (供 Gemini 使用)
my_tools = [
    add_calendar_event, update_user_profile, get_user_profile, read_sheet_data,
    add_todo_task, get_todo_tasks, log_workout_result, get_upcoming_events,
    save_to_inbox, get_current_solar_term, get_weather_forecast,
    add_recipe, get_unread_inbox, mark_inbox_as_read, scrape_web_content,
    log_health_status
]

# 初始化模型 (移至 services 處理)
model = initialize_gemini(my_tools)

def get_system_instruction():
    now = datetime.now()
    current_time_str = now.strftime("%Y-%m-%d %A %H:%M")
    
    instruction = f"""
    你是一位高效的個人秘書、專業健身教練與中醫養生顧問。對於數據、事實性的回報講求精簡，對於建議與感性回覆則富有同理心與溫度。
    現在時間是：{current_time_str} (由 Python datetime 提供)
    
    【格式規範】
    - **格式**：僅使用 `•` 或 `-` 列表，禁止 HTML 標籤。遇到「天氣預報」等完整格式回傳，請直接顯示，勿修改。
    - **多工**：若指令涉及多個面向（如「早安」），請一次呼叫所有相關工具。
    - **主動性**：從對話中得知用戶偏好（飲食、計畫）時，務必主動更新 `User Profile`。
    
    【關鍵工具對照表 (Strict Parameter Mapping)】
    呼叫 `read_sheet_data` 時，`sheet_name` 參數**僅限**使用以下字串，嚴禁自行創造：
    - 查健身動作庫 -> "training"
    - 查長期病歷/體質 -> "health_profile"
    - 查運動歷史紀錄 -> "workout_history"
    - 查食材屬性/忌口 -> "food_properties"
    - 查食譜 -> "recipes"
    
    【網址處理 (URL Handling)】
    當用戶傳送任何網址 (URL) 時，呼叫 `scrape_web_content(url)` 取得內容。
    - 內容是食譜相關 -> 額外提取資訊並呼叫 `add_recipe` 儲存。
    - 內容非食譜 -> 呼叫 `save_to_inbox` 儲存至 Inbox，並告知已抓取的標題與150字內摘要。
    
    【特殊指令：定時排程】
    當你收到以 **`[定時指令]`** 開頭的訊息時，這代表系統自動觸發的排程任務。
    請忽略禮貌性用語，直接根據指令內容執行對應動作，並產出結構清晰的訊息。

    【情境反應指南】
    1. **早安/晨間喚醒 (Routine: Morning)**
       - 用戶說：「早安」、「晨間訊息」。
       - 動作：同時呼叫 `get_weather_forecast`, `get_current_solar_term`, `get_upcoming_events(days=1)`, `get_todo_tasks`。
       - 回覆：(1)天氣 (2)節氣 (3)今日行程 (4)重點待辦。

    2. **工作與專案 (Work & Tasks)**
       - 用戶說：「進度」、「下班」、「午休結束」。
       - 動作：同時呼叫 `get_todo_tasks`, `get_upcoming_events`。
       - 邏輯：盤點未完成事項，協助安排優先順序或延後至明日。

    3. **健身與運動 (Fitness Coaching)**
       - **安排運動**：
         (1) 檢查恢復：呼叫 `read_sheet_data("workout_history")` 確認上次訓練日與部位。
         (2) 檢查體質：呼叫 `read_sheet_data("health_profile")` 若 HP<6 或氣虛，建議輕度運動。
         (3) 排程：避開上次部位，從 `read_sheet_data("training")` 依「強度」挑選動作，呼叫 `add_calendar_event` 寫入行事曆。
       - **結算運動**：
         (1) 用戶回報「練完了」。
         (2) 確認行事曆上的菜單 -> 詢問 RPE (1-10) -> 呼叫 `log_workout_result`。

    4. **飲食與養生 (Diet & TCM)**
       - 用戶問「吃什麼」、「食譜」：
         (1) 呼叫 `get_user_profile`, `get_current_solar_term` 與 `read_sheet_data("health_profile")` 確認習慣、節氣與健康狀況。
         (2) 呼叫 `read_sheet_data("food_properties")` 排除忌口食材。
         (3) 呼叫 `read_sheet_data("recipes")` 推薦適合食譜。

    5. **健康狀況紀錄 (Diagnosis)**
       - 用戶說：「不舒服」、「紀錄身體」。
       - 動作：引導輸入 HP 及症狀並判斷體質變化 -> 呼叫 `log_health_status`。
    
    6. **行程管理** (Google Calendar)
       - 用戶提及「約會」、「餐聚」、「會議」
       - 動作：呼叫 `get_upcoming_events` 確認無重複 -> 呼叫 `add_calendar_event` 新增行程並回報。
    """
    return instruction

# --- Telegram 處理邏輯 ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
    user_id = update.effective_user.id
    logger.info(f"User ({user_id}): {user_input}")

    try:
        # 顯示 "打字中..." 狀態
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        system_prompt = get_system_instruction()

        # Session 管理
        if user_id not in user_sessions:
            print(f"User {user_id}: 建立新對話 Session", flush=True)
            chat_session = model.start_chat(
                history=[
                    {"role": "user", "parts": [system_prompt]},
                    {"role": "model", "parts": ["收到，我已準備好執行您的個人助理任務。"]} 
                ],
                enable_automatic_function_calling=True 
            )
            user_sessions[user_id] = chat_session
        else:
            chat_session = user_sessions[user_id]

        # 發送給 Gemini
        response = chat_session.send_message(user_input)
        ai_reply = response.text
        
        # 格式轉換 (Markdown -> HTML)
        ai_reply = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', ai_reply)
        ai_reply = ai_reply.replace("- ", "• ")
        ai_reply = ai_reply.replace("```html", "").replace("```", "")
        ai_reply = ai_reply.replace("<br>", "\n").replace("<ul>", "").replace("</ul>", "").replace("<li>", "• ").replace("</li>", "")
        
        await update.message.reply_text(ai_reply, parse_mode=ParseMode.HTML)
    
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        if user_id in user_sessions: del user_sessions[user_id]
        await update.message.reply_text("對話發生錯誤，已重置記憶。請再試一次。")

# --- 初始化 Telegram App ---
token = os.getenv("TELEGRAM_BOT_TOKEN")
if not token: raise ValueError("TELEGRAM_BOT_TOKEN 未設定！")

ptb_app = ApplicationBuilder().token(token).build()
ptb_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

# --- Flask 路由設定 ---

@flask_app.route('/', methods=['GET'])
def index():
    return "Gemini Bot is Alive!"

# 1. Telegram Webhook 入口
@flask_app.route(f'/{token}', methods=['POST'])
async def telegram_webhook():
    """接收 Telegram 傳來的更新"""
    if not ptb_app._initialized:
        await ptb_app.initialize()
    update = Update.de_json(request.get_json(force=True), ptb_app.bot)
    await ptb_app.process_update(update)
    return "OK"

# 2. GitHub Actions 排程入口 (關鍵新增)
@flask_app.route('/trigger_routine', methods=['POST'])
async def trigger_routine():
    """
    接收 GitHub Actions 的定時呼叫。
    Payload 格式: {"user_id": 123456789, "message": "[定時指令] 早安"}
    Header: {"X-API-KEY": "您的密鑰"}
    """
    # 簡單的資安驗證
    api_key = request.headers.get("X-API-KEY")
    server_key = os.getenv("GEMINI_API_KEY") # 為了方便，我們先借用 Gemini Key 當作驗證碼，您也可以另外設一個
    if api_key != server_key:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    target_user_id = data.get("user_id")
    message_text = data.get("message")

    if not target_user_id or not message_text:
        return jsonify({"error": "Missing params"}), 400

    logger.info(f"收到排程觸發: User={target_user_id}, Msg={message_text}")

    if not ptb_app._initialized:
        await ptb_app.initialize()
    
    # 【黑魔法】：偽造一個 Telegram Update 物件
    # 這讓 handle_message 以為是使用者真的傳了這句話
    # 這樣我們就不需要重寫邏輯，Session、權限、格式處理通通沿用
    from telegram import User, Chat, Message
    
    mock_user = User(id=target_user_id, first_name="Auto", is_bot=False)
    mock_chat = Chat(id=target_user_id, type="private")
    mock_message = Message(
        message_id=0, 
        date=datetime.now(), 
        chat=mock_chat, 
        from_user=mock_user, 
        text=message_text
    )
    mock_update = Update(update_id=0, message=mock_message)

    # 丟進 PTB 處理
    await ptb_app.process_update(mock_update)

    return jsonify({"status": "Triggered", "message": message_text})

# --- 啟動伺服器 ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    webhook_url = os.getenv("WEBHOOK_URL")
    
    # 這裡只做一次設定
    if webhook_url:
        print(f"設定 Webhook: {webhook_url}/{token}")
        # 注意：在 Flask 模式下，我們需要手動設定 webhook
        # 但這裡為了避免 async 問題，我們通常建議手動用 curl 設定一次，
        # 或者讓 Application 在啟動時設定。
        # 簡單作法：透過 requests 同步設定
        import requests
        requests.get(f"https://api.telegram.org/bot{token}/setWebhook?url={webhook_url}/{token}")

    # 啟動 Flask
    flask_app.run(host="0.0.0.0", port=port)