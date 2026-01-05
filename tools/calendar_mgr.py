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
    """讀取 Google 日曆上未來幾天的行程。"""
    service = get_google_service('calendar', 'v3') 
    if not service: return "錯誤：無法連線至 Google Calendar"

    try:
        now = datetime.now(ZoneInfo("Asia/Taipei"))
        time_min = now.isoformat()
        end_date = now + timedelta(days=days)
        time_max = end_date.isoformat()

        events_result = service.events().list(
            calendarId='primary', timeMin=time_min, timeMax=time_max,
            maxResults=20, singleEvents=True, orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        if not events: return f"接下來 {days} 天內沒有安排行程。"

        formatted_events = f"【未來 {days} 天的行程】\n"
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            
            # 簡單格式化顯示
            try:
                # 嘗試轉成比較易讀的格式
                if 'T' in start:
                    dt_obj = datetime.fromisoformat(start)
                    start_str = dt_obj.strftime("%m/%d %H:%M")
                else:
                    start_str = start # 全天行程通常是 YYYY-MM-DD
            except:
                start_str = start
            
            summary = event.get('summary', '無標題')
            description = event.get('description', '')
            details = f" ({description})" if description else ""
            formatted_events += f"• {start_str} | {summary}{details}\n"
            
        return formatted_events
    except Exception as e:
        return f"讀取日曆失敗 (Error): {str(e)}"