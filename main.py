# main.py
import os
import re
import logging
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
import asyncio

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
user_sessions = {}
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
load_dotenv()

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
    你是一位高效的個人秘書、專業健身教練與中醫養生顧問。
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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
    user_id = update.effective_user.id
    logger.info(f"User ({user_id}): {user_input}")

    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        system_prompt = get_system_instruction()

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

        response = chat_session.send_message(user_input)
        ai_reply = response.text
        
        # 格式轉換
        ai_reply = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', ai_reply)
        ai_reply = ai_reply.replace("- ", "• ")
        ai_reply = ai_reply.replace("```html", "").replace("```", "")
        ai_reply = ai_reply.replace("<br>", "\n").replace("<ul>", "").replace("</ul>", "").replace("<li>", "• ").replace("</li>", "")
        
        await update.message.reply_text(ai_reply, parse_mode=ParseMode.HTML)
    
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        if user_id in user_sessions: del user_sessions[user_id]
        await update.message.reply_text("對話發生錯誤，已重置記憶。請再試一次。")

if __name__ == '__main__':
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token: raise ValueError("TELEGRAM_BOT_TOKEN 未設定！")
        
    mode = os.getenv("MODE", "polling") 
    app = ApplicationBuilder().token(token).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print(f"Gemini Assistant 啟動中... 模式: {mode}", flush=True)

    if mode == "webhook":
        port = int(os.environ.get("PORT", 8080))
        webhook_url = os.getenv("WEBHOOK_URL") 
        if not webhook_url:
            logger.warning("警告：WEBHOOK_URL 未設定！")
            webhook_url = "https://example.com"
        
        app.run_webhook(listen="0.0.0.0", port=port, url_path=token, webhook_url=f"{webhook_url}/{token}")
    else:
        app.run_polling()