# tools/calendar_mgr.py
from datetime import datetime, timedelta
from services.google_api import get_google_service
from zoneinfo import ZoneInfo

def add_calendar_event(summary: str, start_time: str, duration_minutes: int = 60, description: str = "", remind_minutes: int = 0):
    """
    在 Google 日曆上建立活動。
    參數:
    - summary: 活動標題
    - start_time: 開始時間 (ISO 格式)
    - duration_minutes: 持續時間
    - description: 備註
    - remind_minutes: 提前幾分鐘提醒 (例如 60 代表前一小時)。若為 0，則使用 Google 日曆的預設提醒。
    """
    service = get_google_service('calendar', 'v3') 
    if not service: return "錯誤：無法連線至 Google Calendar"

    try:
        start_dt = datetime.fromisoformat(start_time)
        end_dt = start_dt + timedelta(minutes=duration_minutes)
        event = {
            'summary': summary,
            'description': description,
            'start': {'dateTime': start_time, 'timeZone': 'Asia/Taipei'},
            'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'Asia/Taipei'},
            'reminders': {'useDefault': True},
        }
        # 如果有指定提醒時間，則覆寫預設值
        if remind_minutes > 0:
            event['reminders'] = {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': remind_minutes}, # 手機/電腦跳出通知
                    # 若想要 Email 提醒也可以加一行: {'method': 'email', 'minutes': remind_minutes}
                ]
            }

        created_event = service.events().insert(calendarId='primary', body=event).execute()
        
        remind_msg = " (使用預設提醒)"
        if remind_minutes > 0:
            remind_msg = f" (已設定 {remind_minutes} 分鐘前提醒)"
            
        return f"成功建立活動：{created_event.get('htmlLink')}{remind_msg}"
        
    except Exception as e:
        return f"建立活動失敗: {e}"

def get_upcoming_events(days: int = 1):
    """
    讀取 Google 日曆上未來幾天的行程 (包含所有已勾選的日曆)。
    1. 遍歷帳號下所有 Calendar List。
    2. 合併不同日曆的行程並依時間排序。
    3. 顯示時標註來源日曆名稱，例如 [工作] 或 [家庭]。
    """
    service = get_google_service('calendar', 'v3') 
    if not service: return "錯誤：無法連線至 Google Calendar"

    try:
        now = datetime.now(ZoneInfo("Asia/Taipei"))
        time_min = now.isoformat()
        end_date = now + timedelta(days=days)
        time_max = end_date.isoformat()

        # 取得所有日曆列表
        # minAccessRole='owner' 或 'writer' 可以只抓自己的，
        # 但為了包含訂閱的日曆(如公司共用)，我們先抓全部，再用 selected 過濾
        cal_list_result = service.calendarList().list().execute()
        calendars = cal_list_result.get('items', [])

        all_events = []

        # 遍歷每一個日曆
        for cal in calendars:
            # 過濾 A: 只讀取 Google 日曆介面上「有勾選顯示」的日曆
            if not cal.get('selected', False): 
                continue
            
            # 過濾 B: 排除一些通常不需要 AI 報告的系統日曆 (可依需求調整)
            # 例如: "addressbook#contacts@group.v.calendar.google.com" 是聯絡人生日
            # "zh-tw.taiwan#holiday@group.v.calendar.google.com" 是台灣假期
            cal_id = cal['id']
            summary_name = cal['summary']
            if "contacts@group.v.calendar.google.com" in cal_id: continue
            if "holiday@group.v.calendar.google.com" in cal_id: continue

            # 查詢該日曆的活動
            try:
                events_result = service.events().list(
                    calendarId=cal_id, 
                    timeMin=time_min, 
                    timeMax=time_max,
                    maxResults=10, # 每個日曆最多抓10筆，避免爆量
                    singleEvents=True, 
                    orderBy='startTime'
                ).execute()
                
                items = events_result.get('items', [])
                
                # 將日曆名稱注入到 event 物件中，方便後續顯示
                for item in items:
                    item['source_calendar'] = summary_name
                    all_events.append(item)
                    
            except Exception as e:
                print(f"略過日曆 {summary_name}: {e}")
                continue
            
        if not all_events: return f"接下來 {days} 天內沒有安排行程。"
        
        # 重新排序：因為是分開抓的，必須把所有活動混在一起按時間重排
        # Key: 優先抓 dateTime (精確時間), 沒有則抓 date (全天)
        all_events.sort(key=lambda x: x['start'].get('dateTime', x['start'].get('date')))

        # 格式化輸出
        formatted_events = f"<b>【未來 {days} 天的行程總覽】</b>\n"

        for event in all_events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            cal_name = event.get('source_calendar', '未知')
            
            # 時間格式化
            try:
                if 'T' in start: # 有時間的行程
                    dt_obj = datetime.fromisoformat(start)
                    start_str = dt_obj.strftime("%m/%d %H:%M")
                else: # 全天行程
                    start_str = f"{start} (全天)" # 全天行程通常是 YYYY-MM-DD
            except:
                start_str = start

            summary = event.get('summary', '無標題')
            
            # 格式範例: • 01/05 14:00 [工作] 專案會議
            # 如果是主日曆(通常顯示為 Email)，可以簡化顯示名稱，或者就保留顯示區隔
            formatted_events += f"• {start_str} [{cal_name}] {summary}\n"
            
        return formatted_events

    except Exception as e:
        return f"讀取行程失敗: {e}"