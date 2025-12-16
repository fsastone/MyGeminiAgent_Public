import os
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import requests
from bs4 import BeautifulSoup
import urllib3
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from urllib.parse import urlparse, parse_qs

# 載入環境變數
load_dotenv()
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 設定全域變數與服務 ---
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/tasks'
]
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
CWA_API_KEY = os.getenv("CWA_API_KEY")

# --- 關鍵修改：移除全域 Service 物件，改用函數取得 ---
# 舊程式碼這裡會直接連線，導致啟動失敗。我們把它拿掉。

def get_google_service(service_name, version):
    """
    動態取得 Google 服務連線。
    (含自動更新 Token 功能)
    """
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # 關鍵修改區塊：自動更新 Token
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                # 這行就是拿 Refresh Token 去換新鑰匙的動作
                print(f"正在更新 {service_name} 的 Access Token...", flush=True)
                creds.refresh(Request())
            except Exception as e:
                print(f"Token 更新失敗: {e}")
                return None
        else:
            print("警告：憑證不存在或已失效且無法更新，請重新執行 setup_google.py")
            return None
        
    try:
        service = build(service_name, version, credentials=creds)
        return service
    except Exception as e:
        print(f"連線 {service_name} 失敗: {e}")
        return None

# --- 工具函數區 ---

def add_calendar_event(summary: str, start_time: str, duration_minutes: int = 60, description: str = ""):
    """在 Google 日曆上建立活動。"""
    service = get_google_service('calendar', 'v3') 
    if not service:
        return "錯誤：無法連線至 Google Calendar"

    try:
        # ... (原本的邏輯保持不變，將 calendar_service 替換為 service) ...
        start_dt = datetime.fromisoformat(start_time)
        end_dt = start_dt + timedelta(minutes=duration_minutes)
        event = {
            'summary': summary,
            'description': description,
            'start': {'dateTime': start_time, 'timeZone': 'Asia/Taipei'},
            'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'Asia/Taipei'},
        }
        created_event = service.events().insert(calendarId='primary', body=event).execute()
        return f"成功建立活動：{created_event.get('htmlLink')}"
    except Exception as e:
        return f"建立活動失敗: {e}"

def get_upcoming_events(days: int = 1):
    """
    讀取 Google 日曆上未來幾天的行程。
    用途：
    1. 檢查行程衝突 (避免重複安排)。
    2. 確認今日已安排的運動內容 (用於結算追蹤)。
    
    Args:
        days (int): 要讀取未來幾天的資料，預設為 1 天 (讀取今天與明天的行程)。
    """
    service = get_google_service('calendar', 'v3') 
    if not service:
        return "錯誤：無法連線至 Google Calendar"

    try:
        # 準備時間範圍 (UTC 時間)
        now = datetime.utcnow()
        time_min = now.isoformat() + 'Z' # 'Z' 代表 UTC
        
        end_date = now + timedelta(days=days)
        time_max = end_date.isoformat() + 'Z'

        # 呼叫 API
        events_result = service.events().list(
            calendarId='primary',
            timeMin=time_min,
            timeMax=time_max,
            maxResults=20,
            singleEvents=True, # 展開重複性活動
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])

        if not events:
            return f"接下來 {days} 天內沒有安排行程。"

        formatted_events = f"【未來 {days} 天的行程】\n"
        for event in events:
            # 處理時間 (有些是全天活動，格式不同)
            start = event['start'].get('dateTime', event['start'].get('date'))
            summary = event.get('summary', '無標題')
            description = event.get('description', '')
            
            # 轉換顯示格式，把 description 也抓出來，因為運動菜單可能寫在備註裡
            details = f" ({description})" if description else ""
            formatted_events += f"• {start} | {summary}{details}\n"
            
        return formatted_events

    except Exception as e:
        return f"讀取日曆失敗 (Error): {str(e)}"

def log_life_event(category: str, content: str, note: str = ""):
    """將生活事件記錄到 Google Sheets。"""
    service = get_google_service('sheets', 'v4') 
    if not service:
        return "錯誤：無法連線至 Google Sheets"
        
    if not SPREADSHEET_ID:
        return "錯誤：找不到 SPREADSHEET_ID，請檢查 .env 檔案"

    try:
        today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        values = [[today, category, content, note]]
        body = {'values': values}
        
        result = service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range="logs!A:D", # 確保你的分頁名稱真的是 logs
            valueInputOption="USER_ENTERED",
            body=body
        ).execute()
        
        return f"已記錄到記憶庫：[{category}] {content}"
        
    except Exception as e:
        # 這裡會捕捉真實錯誤 (例如 403 Forbidden, 404 Not Found)
        return f"記錄失敗 (Error): {str(e)}"

def read_sheet_data(sheet_name: str):
    """
    從記憶庫讀取特定的資料表（健身菜單或健康病歷）。
    
    Args:
        sheet_name (str): 
            - "training": 讀取健身動作庫 (欄位: 肌群, 名稱, 強度, 注意事項)
            - "health_profile": 讀取長期病歷與體質 (欄位: date, tags, factors, record, implications)
    """
    service = get_google_service('sheets', 'v4') 
    if not service:
        return "錯誤：無法連線至 Google Sheets"
    
    valid_sheets = ["training", "health_profile", "workout_history"]
    if sheet_name not in valid_sheets:
        return f"錯誤：不支援的頁籤名稱 '{sheet_name}'。僅支援: {valid_sheets}"

    try:
        # 修改點 1: 讀取範圍擴大至 E 欄，以涵蓋新增的 'implications'
        range_name = f"{sheet_name}!A:E"
        
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=range_name
        ).execute()
        
        rows = result.get('values', [])
        
        if not rows:
            return f"頁籤 '{sheet_name}' 是空的。"

        # 處理資料
        data_rows = rows[1:] # 跳過標題列
        
        formatted_text = f"【資料庫讀取：{sheet_name}】\n"
        
        if sheet_name == "training":
            formatted_text += "格式：[肌群] 動作名稱 (強度/10) - 注意事項\n"
            for row in data_rows:
                # 健身菜單維持 4 欄處理
                while len(row) < 4: row.append("")
                category, name, intensity, remark = row[0], row[1], row[2], row[3]
                formatted_text += f"- [{category}] {name} (強度:{intensity}) : {remark}\n"
                
        elif sheet_name == "health_profile":
            # 修改點 2: 更新格式說明，讓 Agent 知道如何解讀新欄位
            formatted_text += "格式：日期 | 健康度(1-10分) | 體質 | 變化 | 細節\n"
            
            for row in data_rows:
                # 修改點 3: 補齊至 5 欄 (Date, HP, Constitution, Changes, Details)
                while len(row) < 5: row.append("") 
                
                date = row[0]
                hp = row[1]  # 健康度 (1-10)
                constitution = row[2]  # 體質
                changes = row[3]  # 變化
                details = row[4]  # 細節
                
                # 修改點 4: 組合字串，使用 >>> 強調 Action Item
                formatted_text += (
                    f"- {date} | "
                    f"健康度: {hp} | "
                    f"體質: {constitution} | "
                    f"變化: {changes} | "
                    f"細節: {details}\n"
                )
        elif sheet_name == "food_properties":
            formatted_text += "格式：食材 - 性味 - 忌諱體質\n"
            for row in data_rows:
                while len(row) < 3: row.append("")
                ing, prop, avoid = row[0], row[1], row[2]
                formatted_text += f"- {ing}: {prop} (忌:{avoid})\n"
        
        elif sheet_name == "workout_history":
            formatted_text += "格式：日期 - 菜單 - RPE - 調整建議\n"
            for row in data_rows:
                # 確保至少有 5 欄 (A-E)
                while len(row) < 5: row.append("")
                date, menu, rpe, adj, note = row[0], row[1], row[2], row[3], row[4]
                formatted_text += f"- {date}: {menu} (RPE:{rpe}) | 建議:{adj}\n"
        
        elif sheet_name == "recipes":
            formatted_text += "格式：名稱 - 主食材 - 適合季節 - 標籤 - 連結 - 備註\n"
            for row in data_rows:
                # 確保至少有 6 欄 (A-F)
                while len(row) < 6: row.append("")
                name, main_ing, season, tags, link, note = row[0], row[1], row[2], row[3], row[4], row[5]
                formatted_text += f"- {name}: {main_ing} (季節:{season}, 標籤:{tags}) 連結: {link} 備註: {note}\n"
        
        return formatted_text

    except Exception as e:
        return f"讀取失敗 (Error): {str(e)}"

def log_workout_result(menu: str, rpe: int, note: str = ""):
    """
    記錄運動訓練成果到專屬的 workout_history 頁籤。
    
    Args:
        menu (str): 當次執行的訓練內容（例如 "深蹲 5x5, 伏地挺身 3x10"）。
        rpe (int): 自覺強度 (1-10)。10代表力竭，1代表無感。
        note (str): 身體感受或調整細節。
    """
    service = get_google_service('sheets', 'v4') 
    if not service:
        return "錯誤：無法連線至 Google Sheets"

    try:
        today = datetime.now().strftime("%Y-%m-%d")
        
        # 簡單的漸進式負荷演算法 (由 Python 預判，或是讓 AI 在 Prompt 判斷填入)
        # 這裡我們讓 AI 在 content 裡決定，這裡只負責寫入
        adjustment_suggestion = ""
        if rpe <= 4:
            adjustment_suggestion = "強度過低，下週顯著增加負荷"
        elif rpe >= 9:
            adjustment_suggestion = "接近極限，下週維持或減量"
        else:
            adjustment_suggestion = "強度適中，下週可微幅增加"

        values = [[today, menu, rpe, adjustment_suggestion, note]]
        
        body = {'values': values}
        
        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range="workout_history!A:E",
            valueInputOption="USER_ENTERED",
            body=body
        ).execute()
        
        return f"訓練紀錄已歸檔。強度評估：{rpe}/10，建議：{adjustment_suggestion}"

    except Exception as e:
        return f"記錄失敗 (Error): {str(e)}"

def read_recent_logs(limit: int = 20):
    """
    從記憶庫 (Google Sheets) 讀取最近的生活紀錄。
    當用戶詢問「我最近做了什麼」、「幫我回顧本週」、「查看運動紀錄」時使用此工具。
    
    Args:
        limit (int): 要讀取的筆數，預設為最近 20 筆。
    """
    service = get_google_service('sheets', 'v4') 
    if not service:
        return "錯誤：無法連線至 Google Sheets"
    
    try:
        # 1. 讀取整張表 (假設你的資料不會多到爆掉，目前先讀 A 到 D 欄)
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range="logs!A:D"
        ).execute()
        
        rows = result.get('values', [])
        
        if not rows:
            return "記憶庫目前是空的。"

        # 2. 處理資料：保留標題列，並取得最後 N 筆
        header = rows[0] # ['date', 'category', 'content', 'note']
        data_rows = rows[1:] # 扣除標題剩下的資料
        
        # 取最後 limit 筆 (最新的資料通常在最下面)
        recent_rows = data_rows[-limit:]
        
        # 3. 格式化成文字回傳給 Gemini
        formatted_logs = "【最近的記憶紀錄】\n"
        for row in recent_rows:
            # 防呆機制：有些列可能沒填滿，用空字串補齊
            while len(row) < 4:
                row.append("")
            
            date, category, content, note = row[0], row[1], row[2], row[3]
            formatted_logs += f"- [{date}] ({category}): {content} | {note}\n"
            
        return formatted_logs

    except Exception as e:
        return f"讀取失敗 (Error): {str(e)}"

def add_todo_task(title: str, notes: str = ""):
    """
    新增一項待辦事項到 Google Tasks (預設清單)。
    適用於：雜事、購物清單、專案待辦、沒有確切執行時間的任務。
    
    Args:
        title (str): 任務標題 (例如 "買牛奶", "修改 main.py").
        notes (str): 備註或細節說明.
    """
    service = get_google_service('tasks', 'v1') 
    if not service:
        return "錯誤：無法連線至 Google Tasks"

    try:
        task_body = {
            'title': title,
            'notes': notes
        }
        
        # '@default' 代表使用者的預設清單
        result = service.tasks().insert(tasklist='@default', body=task_body).execute()
        
        return f"已建立待辦事項：{result.get('title')}"

    except Exception as e:
        return f"建立任務失敗 (Error): {str(e)}"

def get_todo_tasks(max_results: int = 10):
    """
    查詢目前未完成的待辦事項。
    當用戶問「我還有什麼事沒做？」、「查看待辦清單」時使用。
    """
    service = get_google_service('tasks', 'v1') 
    if not service:
        return "錯誤：無法連線至 Google Tasks"

    try:
        # showCompleted=False 代表只看沒做完的
        results = service.tasks().list(
            tasklist='@default', 
            showCompleted=False, 
            maxResults=max_results
        ).execute()
        
        items = results.get('items', [])

        if not items:
            return "目前沒有未完成的待辦事項，太棒了！"

        formatted_tasks = "【待辦事項清單】\n"
        for item in items:
            title = item.get('title')
            notes = item.get('notes', '')
            # 如果有備註就顯示，沒有就不顯示
            note_str = f" ({notes})" if notes else ""
            formatted_tasks += f"• {title}{note_str}\n"
            
        return formatted_tasks

    except Exception as e:
        return f"查詢任務失敗 (Error): {str(e)}"

import requests
from bs4 import BeautifulSoup

def save_to_inbox(url: str, note: str = ""):
    """
    將網頁連結儲存到 'inbox' 頁籤，並嘗試抓取標題與內文供 Gemini 摘要。
    
    Args:
        url (str): 網頁連結。
        note (str): 備註。
    """
    service = get_google_service('sheets', 'v4') 
    if not service:
        return "錯誤：無法連線至 Google Sheets"

    page_title = "未命名頁面"
    page_content_snippet = "無法抓取內文"

    # 1. 嘗試抓取網頁內容
    try:
        # 偽裝成一般的 Chrome 瀏覽器
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        
        # verify=False 避免某些網站 SSL 報錯
        response = requests.get(url, headers=headers, timeout=10, verify=False)
        
        if response.status_code == 200:
            # 指定編碼，避免中文亂碼
            response.encoding = response.apparent_encoding
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 抓標題
            if soup.title and soup.title.string:
                page_title = soup.title.string.strip()
            
            # 抓內文 (尋找所有的 p 段落)
            paragraphs = soup.find_all('p')
            # 過濾掉太短的廣告文字，並組合成文章
            text_content = "\n".join([p.get_text().strip() for p in paragraphs if len(p.get_text()) > 10])
            
            if text_content:
                # 只取前 1500 字傳給 Gemini，避免 Token 爆炸
                page_content_snippet = text_content[:1500]
            else:
                page_content_snippet = "網頁無文字內容，可能是純圖片或動態載入(JavaScript)網頁。"
                
    except Exception as e:
        print(f"爬蟲失敗: {e}")
        page_title = "標題抓取失敗"
        page_content_snippet = f"爬取錯誤: {str(e)}"

    # 2. 寫入 Google Sheets
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        # 欄位: Date, URL, Title, Note, Status
        values = [[today, url, page_title, note, "Unread"]]
        
        body = {'values': values}
        
        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range="inbox!A:E",
            valueInputOption="USER_ENTERED",
            body=body
        ).execute()
        
        # 3. 關鍵回傳：把抓到的內文傳回給 Gemini
        # 這樣 Gemini 才能「看到」網頁內容並幫你摘要
        return f"✅ 已收藏至 Inbox。\n標題：{page_title}\n\n【網頁內容摘要 (供 AI 閱讀)】：\n{page_content_snippet}..."

    except Exception as e:
        return f"儲存失敗 (Error): {str(e)}"

def get_unread_inbox(limit: int = 5):
    """
    讀取 Inbox 中尚未閱讀 (Status=Unread) 的項目。
    格式優化版：標題限制 15 字，網址換行。
    """
    service = get_google_service('sheets', 'v4') 
    if not service:
        return "錯誤：無法連線至 Google Sheets"

    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range="inbox!A:E"
        ).execute()
        
        rows = result.get('values', [])
        if not rows:
            return "Inbox 是空的。"

        unread_items = []
        # 跳過標題列，從第 2 行開始
        for index, row in enumerate(rows[1:], start=2):
            while len(row) < 5: row.append("")
            
            status = row[4].strip().lower()
            if status != "read":
                # 資料解包
                url = row[1]
                full_title = row[2]
                
                # 標題截斷邏輯
                display_title = full_title
                if len(full_title) > 15:
                    display_title = full_title[:15] + "..."
                
                # 組合新格式: • [ID] 標題 \n (網址)
                item_str = f"• [{index}] {display_title}\n  ({url})"
                unread_items.append(item_str)
            
            if len(unread_items) >= limit:
                break
        
        if not unread_items:
            return "太棒了！你的 Inbox 目前沒有未讀項目。"
            
        return "【未讀清單】\n" + "\n".join(unread_items)

    except Exception as e:
        return f"讀取 Inbox 失敗: {str(e)}"

def mark_inbox_as_read(row_ids_str: str):
    """
    將 Inbox 中的特定項目標記為已讀 (Read)。支援一次標記多筆。
    
    Args:
        row_ids_str (str): 項目 ID 字串，以逗號分隔 (例如 "2, 4, 5")。
    """
    service = get_google_service('sheets', 'v4') 
    if not service:
        return "錯誤：無法連線至 Google Sheets"

    try:
        # 解析 ID：將 "2, 4" 轉成 [2, 4]
        # 這裡做了一些防呆，把空格去掉，確保是數字
        row_ids = [int(x.strip()) for x in row_ids_str.split(',') if x.strip().isdigit()]
        
        if not row_ids:
            return "錯誤：無法識別 ID，請提供數字 (例如 '2, 4')。"

        success_ids = []
        fail_ids = []

        # 批次處理 (Google Sheets API 其實有 batchUpdate，但為了代碼簡單，我們用迴圈)
        for row_id in row_ids:
            try:
                range_name = f"inbox!E{row_id}"
                body = {'values': [["Read"]]}
                
                service.spreadsheets().values().update(
                    spreadsheetId=SPREADSHEET_ID,
                    range=range_name,
                    valueInputOption="USER_ENTERED",
                    body=body
                ).execute()
                success_ids.append(str(row_id))
            except Exception:
                fail_ids.append(str(row_id))
        
        result_msg = f"已將 ID {', '.join(success_ids)} 標記為已讀。"
        if fail_ids:
            result_msg += f" (ID {', '.join(fail_ids)} 更新失敗)"
            
        return result_msg

    except Exception as e:
        return f"更新狀態失敗: {str(e)}"

def get_current_solar_term():
    """
    精準計算目前的節氣與下一個節氣。
    (使用簡易算法，誤差約在 1 天內，對一般生活應用足夠)
    """
    import bisect
    
    # 節氣基準表 (以 2024-2025 為例的概略日期，這可以每年微調，或用更複雜演算法)
    # 格式: (月, 日, 節氣名稱)
    solar_terms_data = [
        (1, 5, "小寒"), (1, 20, "大寒"), (2, 4, "立春"), (2, 19, "雨水"),
        (3, 5, "驚蟄"), (3, 20, "春分"), (4, 4, "清明"), (4, 19, "穀雨"),
        (5, 5, "立夏"), (5, 21, "小滿"), (6, 5, "芒種"), (6, 21, "夏至"),
        (7, 7, "小暑"), (7, 22, "大暑"), (8, 7, "立秋"), (8, 23, "處暑"),
        (9, 7, "白露"), (9, 23, "秋分"), (10, 8, "寒露"), (10, 23, "霜降"),
        (11, 7, "立冬"), (11, 22, "小雪"), (12, 7, "大雪"), (12, 21, "冬至")
    ]
    
    now = datetime.now()
    year = now.year
    
    # 建立當年度的時間戳記列表
    dates = []
    term_names = []
    for month, day, name in solar_terms_data:
        try:
            d = datetime(year, month, day)
            dates.append(d)
            term_names.append(name)
        except:
            pass # 處理閏年日期可能的微小誤差

    # 找到今天在列表中的位置
    idx = bisect.bisect_right(dates, now)
    
    # 取得「當下/最近」的節氣 (上一個)
    current_term = term_names[idx - 1] if idx > 0 else term_names[-1]
    current_term_date = dates[idx - 1] if idx > 0 else dates[-1]

    # 取得「下一個」節氣
    if idx < len(dates):
        next_term = term_names[idx]
        next_term_date = dates[idx]
    else:
        # 跨年處理
        next_term = solar_terms_data[0][2]
        next_term_date = datetime(year + 1, solar_terms_data[0][0], solar_terms_data[0][1])

    days_until = (next_term_date - now).days + 1
    
    msg = f"目前節氣：{current_term} (已過 {abs((now - current_term_date).days)} 天)\n"
    msg += f"下個節氣：{next_term} (再 {days_until} 天)"
    
    # 特別提醒：如果是節氣轉換前後 2 天
    if days_until <= 2:
        msg += f"\n>>> 注意：即將進入 {next_term}，請注意氣候轉換與調養！"
    elif abs((now - current_term_date).days) <= 1:
        msg += f"\n>>> 注意：正值 {current_term} 節氣轉換期！"
        
    return msg

def get_weather_forecast(location: str = "臺北市"):
    """
    呼叫中央氣象署 API 取得精簡版天氣預報 (純數據版)。
    回傳格式範例：
    【臺北市今日天氣】
    - 下午 🌥️晴時多雲 🌂0% 🌡️20 - 25℃
    - 晚間 🌥️晴時多雲 ☂️10% 🌡️17 - 20℃
    """
    if not CWA_API_KEY:
        return "錯誤：找不到 CWA_API_KEY"

    api_url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001?Authorization={CWA_API_KEY}&format=JSON&locationName={location}"

    try:
        # 加入 verify=False 解決 SSL 錯誤
        response = requests.get(api_url, verify=False)
        data = response.json()
        
        if not data.get('success') == 'true':
            return f"氣象署 API 回傳錯誤: {data}"

        location_data = data['records']['location'][0]
        elements = location_data['weatherElement']
        # elements index: 0=Wx(現象), 1=PoP(降雨%), 2=MinT, 3=CI(舒適度), 4=MaxT
        report_lines = []
           
        # 只需要前兩筆預報 (通常是 12小時 + 12小時)
        for i in range(0, 2):
            start_str = elements[0]['time'][i]['startTime'] # Format: YYYY-MM-DD HH:MM:SS
            # 抓取小時 (例如 12:00:00 -> 12)
            hour = int(start_str.split(' ')[1].split(':')[0])
            
            # --- 1. 時段顯示名稱 ---
            if 5 <= hour < 11: time_desc = "早晨"
            elif 11 <= hour < 13: time_desc = "中午"
            elif 13 <= hour < 17: time_desc = "下午"
            elif 17 <= hour < 19: time_desc = "傍晚"
            elif 19 <= hour < 23: time_desc = "晚間"
            else: time_desc = "深夜"

            # --- 2. 數值取得 ---
            wx_name = elements[0]['time'][i]['parameter']['parameterName'] # 天氣現象
            pop_val = int(elements[1]['time'][i]['parameter']['parameterName']) # 降雨機率
            min_t = elements[2]['time'][i]['parameter']['parameterName']
            max_t = elements[4]['time'][i]['parameter']['parameterName']

            # --- 3. Emoji 邏輯 ---
            if "雷" in wx_name: wx_icon = "⛈️"
            elif "雨" in wx_name: wx_icon = "🌧️"
            elif "雲" in wx_name or "陰" in wx_name: wx_icon = "🌥️"
            else: # 晴天相關
                # 判斷是白天還是晚上 (06~18為白天)
                is_daytime = 6 <= hour < 18
                wx_icon = "☀️" if is_daytime else "🌙"

            pop_icon = "🌂" if pop_val == 0 else ("☂️" if pop_val <= 50 else "☔")
            
            # --- 4. 組合字串 ---
            # 格式: - 下午 🌥️晴時多雲 🌂0% 🌡️20 - 25℃
            line = f"- {time_desc} {wx_icon}{wx_name} {pop_icon}{pop_val}% 🌡️{min_t} - {max_t}℃"
            report_lines.append(line)
            
        # 組合最終輸出
        header = f"【{location}今日天氣】"
        body = "\n".join(report_lines)
    
        return f"{header}\n{body}"

    except Exception as e:
        return f"天氣查詢失敗: {str(e)}"

def log_health_status(hp: int, constitution: str, changes: str = "", details: str = ""):
    """
    [Health 2.0] 記錄每日身體數值與體質狀態。
    
    Args:
        hp (int): 整體健康/精神分數 (1-10)。
        constitution (str): 當下體質判定 (平和/氣虛/陽虛/陰虛/痰濕/濕熱/血瘀/氣鬱/特稟)。
        changes (str): 身體變化 (例如：睡很少、吃了麻辣鍋、生理期)。
        details (str): 詳細症狀或備註。
    """
    service = get_google_service('sheets', 'v4') 
    if not service: return "錯誤：無法連線至 Google Sheets"

    valid_constitutions = ["平和", "氣虛", "陽虛", "陰虛", "痰濕", "濕熱", "血瘀", "氣鬱", "特稟"]
    if constitution not in valid_constitutions:
        return f"體質分類錯誤，請從以下選擇：{valid_constitutions}"

    try:
        today = datetime.now().strftime("%Y-%m-%d")
        # 欄位順序：Date, HP, Constitution, Changes, Details
        values = [[today, hp, constitution, changes, details]]
        body = {'values': values}
        
        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range="health_profile!A:E", # 寫入新結構
            valueInputOption="USER_ENTERED",
            body=body
        ).execute()
        
        return f"已記錄健康狀態：HP={hp}, 體質={constitution}"
    except Exception as e:
        return f"記錄失敗: {str(e)}"

def get_youtube_video_id(url):
    """
    從各種 YouTube 網址格式中精準提取 Video ID。
    支援: youtu.be, www.youtube.com/watch, shorts
    """
    try:
        parsed = urlparse(url)
        # 情況 1: youtu.be/VIDEO_ID?si=...
        if parsed.hostname == 'youtu.be':
            return parsed.path[1:]
        
        # 情況 2: youtube.com/watch?v=VIDEO_ID&...
        if parsed.hostname in ('www.youtube.com', 'youtube.com'):
            if parsed.path == '/watch':
                query = parse_qs(parsed.query)
                return query.get('v', [None])[0]
            if parsed.path.startswith('/shorts/'):
                return parsed.path.split('/')[2]
    except Exception as e:
        print(f"網址解析錯誤: {e}")
    return None

def scrape_web_content(url: str):
    """
    整合 YouTube 字幕抓取 (增強版) 與網頁爬蟲。
    """
    print(f"正在處理網址: {url}")
    
    # --- 策略 A: YouTube 字幕抓取 ---
    video_id = get_youtube_video_id(url)
    
    if video_id:
        print(f"偵測到 YouTube ID: {video_id}")
        try:
            # 1. 建立 API 實例並列出字幕
            api = YouTubeTranscriptApi()
            transcript_list = api.list(video_id)

            # Debug: 印出所有可用語言，方便除錯
            print("可用字幕語言:", [t.language_code for t in transcript_list])

            # 2. 智慧尋找最佳字幕
            # find_generated_transcript=True 允許抓取自動產生的字幕 (這是關鍵！)
            # 優先找中文系列 (zh-TW, zh-Hant, zh-HK, zh-Hans, zh)，再來是英文，最後日文
            transcript = transcript_list.find_transcript(['zh-TW', 'zh-Hant', 'zh-HK', 'zh-Hans', 'zh', 'en', 'ja'])
            print(f"\n成功抓取到語言: {transcript.language_code}")
            
            # 3. 抓取內容
            content = transcript.fetch()  # Returns list of FetchedTranscriptSnippet objects
            # Extract text from objects (v1.2.3 format)
            text_segments = [item.text for item in content]
            content = " ".join(text_segments)
            
            print(f"成功抓取字幕 ({transcript.language_code})，長度: {len(content)}")
            return f"【YouTube 字幕內容 (ID: {video_id}, Lang: {transcript.language_code})】\n{content[:5000]}"
            
        except NoTranscriptFound:
            print("失敗: 真的完全沒有字幕")
            return "YouTube 影片分析失敗：該影片沒有任何可用的字幕軌 (含自動產生)。"
        except TranscriptsDisabled:
            print("失敗: 字幕被停用")
            return "YouTube 影片分析失敗：創作者已停用字幕功能。"
        except Exception as e:
            # 如果上面找特定語言失敗，這裡會嘗試抓最後一根稻草
            try:
                # 使用新版語法：api.list(video_id)
                # 嘗試直接找英文或隨便一個可用的
                fallback_list = api.list(video_id)
                transcript = fallback_list.find_transcript(['en']) 
            except:
                pass # 真的盡力了
                
            print(f"YouTube 抓取未知錯誤: {str(e)}")
            return f"YouTube 字幕抓取發生錯誤 (可能無支援語言): {str(e)}。"

    # --- 策略 B: 一般網頁爬蟲 (沿用之前的邏輯) ---
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10, verify=False)
        response.encoding = response.apparent_encoding
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
            
            paragraphs = soup.find_all('p')
            content = "\n".join([p.get_text().strip() for p in paragraphs if len(p.get_text()) > 10])
            
            if not content:
                content = "網頁無文字內容 (可能是 IG 或圖片為主)。"
            
            return f"【網頁內容摘要】\n標題: {title}\n內容: {content[:3000]}"
            
    except Exception as e:
        return f"網頁爬取失敗: {str(e)}"

    return "無法識別的網址或內容。"

def add_recipe(name: str, main_ing: str, season: str, tags: str, link: str, note: str = ""):
    """
    將食譜存入 'recipes' 頁籤。
    
    Args:
        name (str): 料理名稱。
        main_ing (str): 主食材 (例如: 雞肉, 馬鈴薯)。
        season (str): 適合季節 (例如: 夏季, 冬季, 四季, 寒流)。
        tags (str): 標籤 (例如: 日式, 快速, 減脂)。
        link (str): 原始連結。
        note (str): 備註或做法摘要。
    """
    service = get_google_service('sheets', 'v4') 
    if not service:
        return "錯誤：無法連線至 Google Sheets"

    try:
        # 欄位: Name, Main_Ing, Season, Tags, Link, Note
        values = [[name, main_ing, season, tags, link, note]]
        
        body = {'values': values}
        
        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range="recipes!A:F",
            valueInputOption="USER_ENTERED",
            body=body
        ).execute()
        
        return f"🍽️ 食譜已登錄：{name} (季節:{season}, 標籤:{tags})"

    except Exception as e:
        return f"食譜儲存失敗: {str(e)}"
    

# --- 獨立測試區 (Debugging) ---
if __name__ == '__main__':
    print("=== 開始測試工具模組 ===")

    # 測試 1: 讀取最近紀錄
    #print(read_recent_logs())
    #print(get_todo_tasks())
    #print(get_weather_forecast())
    #print(get_unread_inbox())
    #print(scrape_web_content("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))

    # 測試 2: 測試 Sheets 記錄
    #print("\n[Test] 正在寫入 Google Sheets...")
    #test_result = log_life_event("測試類別", "這是一條測試訊息", "來自 tools.py 直接執行")
    #print(f"結果: {test_result}")
    
    #if "記錄失敗" in test_result:
    #    print(">>> 請檢查：1. token.json 是否已刪除重製？ 2. .env 裡的 SPREADSHEET_ID 是否正確？ 3. Sheet 分頁名稱是否為 logs？")
    #else:
    #    print(">>> Sheets 測試成功！")
    
