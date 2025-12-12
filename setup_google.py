import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# 定義我們要索取的權限範圍 (Scopes)
# 包含：讀寫日曆、讀寫試算表
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/tasks'
]

def authenticate_google():
    creds = None
    # 1. 檢查是否已經有 token.json (之前的通行證)
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    # 2. 如果沒有 token 或過期了，就重新登入
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("憑證過期，嘗試自動刷新...")
            creds.refresh(Request())
        else:
            print("需要進行瀏覽器登入授權...")
            # 載入我們剛下載的 credentials.json
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            # 啟動本地伺服器接收回傳碼
            creds = flow.run_local_server(port=0)

        # 3. 登入成功後，把新的 token 存起來，下次就不用再登入了
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            print("登入成功！Token 已儲存為 token.json")

if __name__ == '__main__':
    authenticate_google()