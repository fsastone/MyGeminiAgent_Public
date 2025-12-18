import os
import asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

load_dotenv()
token = os.getenv("TELEGRAM_BOT_TOKEN")

# 定義一個簡單的指令 /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    print(f"收到來自 {user_name} 的指令！") # Debug 訊息
    await update.message.reply_text(f"你好 {user_name}，介面連接成功！")

if __name__ == '__main__':
    # 建立 Application (機器人的本體)
    application = ApplicationBuilder().token(token).build()

    # 加入指令處理器 (告訴機器人聽到 /start 該做什麼)
    start_handler = CommandHandler('start', start)
    application.add_handler(start_handler)

    print("機器人啟動中...請在 Telegram 對它輸入 /start")
    # 開始輪詢 (Polling)：機器人會一直問 Telegram 伺服器「有新訊息嗎？」
    application.run_polling()