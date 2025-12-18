import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# 定義權限範圍 (跟之前一樣)
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/tasks'
]

def get_calendar_service():
    """取得 Google Calendar 的操作服務"""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not creds or not creds.valid:
        raise Exception("憑證無效或過期，請重新執行 setup_google.py")

    # 建立並回傳 Calendar API 的服務物件
    service = build('calendar', 'v3', credentials=creds)
    return service