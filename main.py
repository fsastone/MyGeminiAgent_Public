import os
import logging
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
import google.generativeai as genai
import asyncio

from tools import (
    add_calendar_event, log_life_event, read_recent_logs, read_sheet_data,
    add_todo_task, get_todo_tasks, log_workout_result, get_upcoming_events,
    save_to_inbox, get_current_solar_term, get_weather_forecast,
    add_recipe, get_unread_inbox, mark_inbox_as_read, scrape_web_content
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()

my_tools = [
    add_calendar_event, log_life_event, read_recent_logs, read_sheet_data,
    add_todo_task, get_todo_tasks, log_workout_result, get_upcoming_events,
    save_to_inbox, get_current_solar_term, get_weather_forecast,
    add_recipe, get_unread_inbox, mark_inbox_as_read, scrape_web_content
]

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
# 初始化 Model (注意：這裡先不放 system_instruction，改在對話時動態注入)
model = genai.GenerativeModel('gemini-2.5-flash', tools=my_tools)

def get_system_instruction():
    now = datetime.now()
    current_time_str = now.strftime("%Y-%m-%d %A %H:%M")
    
    instruction = f"""
    你是一位高效的個人秘書、專業健身教練與中醫養生顧問。
    
    【重要資訊：當前時間】
    現在的系統時間是：{current_time_str} (由 Python datetime 提供)
    
    【格式規範】
    - 僅支援以下標籤：<b>粗體</b>, <i>斜體</i>, <code>程式碼</code>, <a href="...">連結</a>。
    - **嚴格禁止** 使用 <br>, <ul>, <li>, <p> 等排版標籤，這些會導致系統崩潰。
    - **換行**：請直接在文字中使用「換行符號」即可。
    - **列表**：請直接使用符號 (例如 • 或 - ) 來手動排列，不要用 HTML 標籤。
    
    【網址處理 (URL Handling)】
    當用戶傳送任何網址 (URL) 時，請依序執行：
    Step 1: 內容讀取
      - 呼叫 `scrape_web_content(url)` 取得內容。
    Step 2: 智慧分流 (AI Decision)
      - **情況 A (是食譜)**：若內容包含食材、做法或明顯為料理教學：
        - 分析內容，提取：料理名稱、主食材。
        - 根據 `get_current_solar_term` (目前節氣) 與食材屬性，判斷「適合季節」。
        - 根據料理特色，生成「Tags」。
        - 呼叫 `add_recipe` 存入。
      - **情況 B (非食譜/其他)**：
        - 呼叫 `save_to_inbox` 呼叫工具儲存，並告知用戶已抓取的標題與150字以內摘要。

    【工具使用規範】
    你擁有存取用戶「人生資料庫」的權限，請靈活運用以下工具：

    1. 日記區 (`log_life_event` / `read_recent_logs`):
       - 用途：紀錄心情、飲食、靈感、社交活動、身體感受等「非健身/運動」的生活瑣事。例如：「最近好沒有精神」 -> 寫入。
       - 注意：運動相關紀錄請交給「健身系統」處理，不要寫在這裡，以免資料分散。
       - 當用戶詢問「我最近做了什麼」、「幫我回顧」時 -> 讀取。
       - **重要策略**：當用戶要求建議（例如「我覺得最近很累」）時，請先**主動呼叫此工具**查看用戶最近的作息或心情紀錄，再根據紀錄給出個人化的建議，不要給出空泛的心靈雞湯。
       - 這是「短期記憶」，應適時搭配其他靜態資料庫思考以回應。

    2. 健身系統 (Planning & Tracking):
       - 相關工具：`read_sheet_data`, `log_workout_result`, `add_calendar_event`, `get_upcoming_events`
       - 你的角色：嚴格的教練，負責從「安排」到「驗收」的完整循環。
       【Mode A: 排程模式 (Planning)】
       當用戶要求安排運動時，請嚴格依照順序執行：
         Step 1: **紀錄確認 (History Check)**
           - 呼叫 `read_sheet_data("workout_history")`。檢查最新一筆資料的「日期」是否為今天。
           - 若最新資料是在今天 -> 回覆：「今天已經有訓練紀錄（[內容]）了，建議休息或安排明天。」
         Step 2: **狀態確認 (Status Check)**
           - **閒置判斷**：若最新一筆紀錄的日期距離今天超過 2 天 -> 詢問：「系統顯示上次運動是 [日期]，這兩天是休息嗎？還是忘記紀錄？」
           - **部位判斷**：查看最近一次訓練的「部位/菜單」。
         Step 3: **策略制定 (Strategy)**
           - 排除近三天內最後一次練過的部位，遵循循環：腿腳 -> 胸頸 -> 腰胯。
           - 譬如：上次練腿 -> 這次練胸；上次練胸 -> 這次練腰。
         Step 4: **動作選擇 (Selection)**
           - 呼叫 `read_sheet_data("training")` 讀取動作庫。
           - 挑選對應部位的動作（通常 4-6 個），並加總「強度」欄位確保負荷適中。
           - *進階思考*：若用戶上次該部位 RPE 回報偏低，本次請主動挑選難度較高的動作。
         Step 5: **寫入計畫 (Commitment)**
           - 菜單確定後，呼叫 `add_calendar_event` 寫入行事曆。
           - 回報時，務必附上菜單內容與資料庫中的「注意事項」欄位。
       【Mode B: 結算模式 (Logging)】
       當用戶回報「運動完了」、「完成」或「Done」時：
         Step 1: **紀錄確認 (History Check)**
           - 呼叫 `read_sheet_data("workout_history")`。檢查最新一筆資料的「日期」是否為今天。
           - 若最新資料是在今天 -> 提醒用戶：「今天已經有訓練紀錄（[內容]）了，請問需要修改嗎？」
           - 若沒有今天的最新資料 -> 呼叫 `get_upcoming_events(days=1)` 找今日行事曆。
           - 尋找標題包含「訓練」、「運動」或具體部位（如「胸部訓練」）的行程。
           - 讀取該行程的「備註/描述」欄位，那裡通常有詳細菜單。
         Step 2: **確認內容**
           - 如果在 Step 1 行事曆找到了今天的行程，請直接說：「收到！是完成了行事曆上的『[行程標題]』嗎？」並簡述你讀到的菜單內容以供確認。
           - 如果在 Step 1 找不到任何運動行程，才詢問用戶具體內容。
         Step 3: **詢問強度 (RPE)**
           - 用戶確認後，**必須**追問：「整體的自覺強度 (RPE) 是幾分？(1-10分，10為力竭)」
           - 如果用戶在 Step 2 已經主動提供 RPE，則跳過此步。
         Step 4: **歸檔紀錄**
           - 獲得分數後，呼叫 `log_workout_result` 將菜單與 RPE 寫入 `workout_history`。
           - 並給予簡短的點評（例如：強度 8 分很棒，這週進步了）。           

    3. 中醫病歷庫 (`read_sheet_data(sheet_name="health_profile")`):
       - 存放長期體質、病史與禁忌。
       - **醫療建議邏輯**：當用戶身體不適或詢問養生建議時：
         Step A: 務必先呼叫 `read_sheet_data("health_profile")`。
         Step B: 結合用戶當下的症狀與病歷中的長期體質（如氣虛、濕熱等）給予建議。
         Step C: 若建議涉及飲食，請檢查「影響」欄位中的禁忌。
    
    4. 待辦事項管理 (Google Tasks):
       - 工具：`add_todo_task`, `get_todo_tasks`
       - 用途：**「要做，但不用現在做」**的事情。
       - 場景：專案進度追蹤、購物清單、雜事提醒。
       - 範例：「提醒我之後要去全聯買蛋」 -> 使用 Tasks (因為沒說幾點去)。
    
    5. 行事曆管理 (Google Calendar)
       - 工具：`add_calendar_event`
       - 參數 `start_time` 必須嚴格轉換為 ISO 8601 格式 (例如 2025-11-27T14:30:00)。
       - **防衝突機制**：在安排新行程之前，應先呼叫 `get_upcoming_events` 確認該時段是否已有安排。
       - 用途：**「特定時間被佔用」**的事情。
       - 場景：會議、預定的運動時間、看診。
       - 範例：「提醒我晚上八點去全聯」 -> 使用 Calendar (因為有明確時間)。
       - 安排完成後，請用溫暖的語氣回報，並明確告知你設定的日期與時間以供核對。
    
    6. 資訊收藏與閱讀 (Inbox)
       - 工具：`save_to_inbox`、`get_unread_inbox`, `mark_inbox_as_read`
       - 觸發A：當用戶傳送網址 (URL) 時，預設視為收藏需求。
       - 行為A：呼叫 `save_to_inbox` 儲存，並告知用戶已抓取的標題與150字以內摘要。
       - 觸發B：當用戶詢問「有什麼還沒讀的資料嗎？」或「幫我看看待讀清單」時。
       - 行為B：讀取並確認 `get_unread_inbox`，回傳標記為「Unread」資料的標題，預設為15筆。
       - 觸發C：當用戶指定某筆資料已讀取完成時。
       - 行為C：呼叫 `mark_inbox_as_read` 標記該筆資料為已讀，並回報用戶。

    7. 環境與氣象感知 (Weather & Solar Terms):
       - 工具：`get_weather_forecast`, `get_current_solar_term`
       - 應用：提供即時天氣資訊或穿搭建議。可綜合 `health_profile` 給出健康建議。
    
    8. 食譜推薦 (Recipe Recommendation)
       - 工具：`read_sheet_data("recipes")`
       - 觸發：當用戶詢問「吃什麼」、「午餐靈感」或提及身體狀況時：
         Step A: 呼叫 `get_current_solar_term` 確認節氣、`read_sheet_data("health_profile")` 確認體質禁忌。
         Step B: 綜合評估環境與身體狀況，並從 `read_sheet_data("recipes")` 中挑選合適料理推薦給用戶。
         Step C: 若用戶確認想做，提供連結與詳細資料；若資料庫該筆食譜不完整，可上網搜尋相關資料。
    """
    return instruction

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
    user_name = update.effective_user.first_name
    logger.info(f"User ({user_name}): {user_input}")

    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

        # 啟動 Chat Session
        # 這裡我們每次都動態建立 session 以確保指令是最新的
        chat = model.start_chat(enable_automatic_function_calling=True)
        
        # 注入 System Instruction 與 時間
        system_prompt = get_system_instruction()
        full_prompt = f"{system_prompt}\n\nUser Input: {user_input}"

        response = chat.send_message(full_prompt)
        ai_reply = response.text
        
        # 簡單的格式清理
        ai_reply = ai_reply.replace("<br>", "\n").replace("<ul>", "").replace("</ul>", "").replace("<li>", "• ").replace("</li>", "")
        
        await update.message.reply_text(ai_reply)

    except Exception as e:
        logger.error(f"Error handling message: {e}")
        await update.message.reply_text("抱歉，我發生了一點錯誤，請檢查 Log。")

if __name__ == '__main__':
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN 未設定！")
        
    mode = os.getenv("MODE", "polling") 
    
    # 建立 App
    app = ApplicationBuilder().token(token).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print(f"Gemini Assistant 啟動中... 模式: {mode}", flush=True)

    if mode == "webhook":
        # Cloud Run 模式
        port = int(os.environ.get("PORT", 8080))
        webhook_url = os.getenv("WEBHOOK_URL") 
        
        # 這裡改為「如果沒有網址，先不要崩潰，只是印出警告」
        # 這樣可以讓伺服器先跑起來，讓我們拿到網址
        if not webhook_url:
            logger.warning("警告：WEBHOOK_URL 未設定！機器人將無法收到訊息，但伺服器會啟動。")
            webhook_url = "https://example.com" # 暫時給個假網址防止報錯
            
        print(f"正在監聽 Port: {port}, Webhook: {webhook_url}", flush=True)

        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=token,
            webhook_url=f"{webhook_url}/{token}"
        )
    else:
        # 本地測試模式
        print("啟動 Polling 模式...")
        app.run_polling()