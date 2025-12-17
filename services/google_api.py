# services/google_api.py
import os
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# 載入環境變數
load_dotenv()

# 全域設定
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/tasks'
]
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
CWA_API_KEY = os.getenv("CWA_API_KEY")

def get_google_service(service_name, version):
    """
    動態取得 Google 服務連線 (含自動更新 Token 功能)。
    """
    creds = None
    # 注意：這裡假設 token.json 在專案根目錄
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
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