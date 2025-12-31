# tools/calendar_mgr.py
from datetime import datetime, timedelta
from services.google_api import get_google_service
from zoneinfo import ZoneInfo

def add_calendar_event(summary: str, start_time: str, duration_minutes: int = 60, description: str = ""):
    """在 Google 日曆上建立活動。"""
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
        }
        created_event = service.events().insert(calendarId='primary', body=event).execute()
        return f"成功建立活動：{created_event.get('htmlLink')}"
    except Exception as e:
        return f"建立活動失敗: {e}"

def get_upcoming_events(days: int = 1):
    """讀取 Google 日曆上未來幾天的行程。"""
    service = get_google_service('calendar', 'v3') 
    if not service: return "錯誤：無法連線至 Google Calendar"

    try:
        now = datetime.now(ZoneInfo("Asia/Taipei"))
        time_min = now.isoformat() + 'Z'
        end_date = now + timedelta(days=days)
        time_max = end_date.isoformat() + 'Z'

        events_result = service.events().list(
            calendarId='primary', timeMin=time_min, timeMax=time_max,
            maxResults=20, singleEvents=True, orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        if not events: return f"接下來 {days} 天內沒有安排行程。"

        formatted_events = f"【未來 {days} 天的行程】\n"
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            summary = event.get('summary', '無標題')
            description = event.get('description', '')
            details = f" ({description})" if description else ""
            formatted_events += f"• {start} | {summary}{details}\n"
            
        return formatted_events
    except Exception as e:
        return f"讀取日曆失敗 (Error): {str(e)}"