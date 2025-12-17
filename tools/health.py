# tools/health.py
from datetime import datetime
from services.google_api import get_google_service, SPREADSHEET_ID

def read_sheet_data(sheet_name: str):
    """從記憶庫讀取特定的資料表。"""
    service = get_google_service('sheets', 'v4') 
    if not service: return "錯誤：無法連線至 Google Sheets"
    
    valid_sheets = ["training", "health_profile", "workout_history", "food_properties", "recipes"]
    if sheet_name not in valid_sheets: return f"錯誤：不支援的頁籤名稱 '{sheet_name}'。"

    try:
        range_name = f"{sheet_name}!A:E"
        # 針對 recipes 多讀一欄
        if sheet_name == "recipes": range_name = f"{sheet_name}!A:F"
            
        result = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=range_name).execute()
        rows = result.get('values', [])
        if not rows: return f"頁籤 '{sheet_name}' 是空的。"
        data_rows = rows[1:]
        
        formatted_text = f"【資料庫讀取：{sheet_name}】\n"
        
        if sheet_name == "training":
            formatted_text += "格式：[肌群] 動作名稱 (強度/10) - 注意事項\n"
            for row in data_rows:
                while len(row) < 4: row.append("")
                formatted_text += f"- [{row[0]}] {row[1]} (強度:{row[2]}) : {row[3]}\n"
                
        elif sheet_name == "health_profile":
            formatted_text += "格式：日期 | HP | 體質 | 變化 | 細節\n"
            for row in data_rows:
                while len(row) < 5: row.append("") 
                formatted_text += f"- {row[0]} | HP:{row[1]} | 體質:{row[2]} | 變化:{row[3]} | 細節:{row[4]}\n"

        elif sheet_name == "food_properties":
            formatted_text += "格式：食材 - 性味 - 忌諱體質\n"
            for row in data_rows:
                while len(row) < 3: row.append("")
                formatted_text += f"- {row[0]}: {row[1]} (忌:{row[2]})\n"
        
        elif sheet_name == "workout_history":
            formatted_text += "格式：日期 - 菜單 - RPE - 調整建議\n"
            for row in data_rows:
                while len(row) < 5: row.append("")
                formatted_text += f"- {row[0]}: {row[1]} (RPE:{row[2]}) | 建議:{row[3]}\n"
        
        elif sheet_name == "recipes":
            formatted_text += "格式：名稱 - 主食材 - 季節 - 標籤 - 連結 - 備註\n"
            for row in data_rows:
                while len(row) < 6: row.append("")
                formatted_text += f"- {row[0]}: {row[1]} (季節:{row[2]}, 標籤:{row[3]}) 連結: {row[4]} 備註: {row[5]}\n"
        return formatted_text
    except Exception as e: return f"讀取失敗 (Error): {str(e)}"

def log_workout_result(menu: str, rpe: int, note: str = ""):
    """記錄運動訓練成果。"""
    service = get_google_service('sheets', 'v4') 
    if not service: return "錯誤：無法連線至 Google Sheets"
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        adjustment = "強度過低" if rpe <= 4 else ("接近極限" if rpe >= 9 else "強度適中")
        values = [[today, menu, rpe, adjustment, note]]
        body = {'values': values}
        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID, range="workout_history!A:E",
            valueInputOption="USER_ENTERED", body=body
        ).execute()
        return f"訓練紀錄已歸檔。強度評估：{rpe}/10，建議：{adjustment}"
    except Exception as e: return f"記錄失敗: {str(e)}"

def log_health_status(hp: int, constitution: str, changes: str = "", details: str = ""):
    """記錄每日身體數值。"""
    service = get_google_service('sheets', 'v4') 
    if not service: return "錯誤：無法連線至 Google Sheets"
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        values = [[today, hp, constitution, changes, details]]
        body = {'values': values}
        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID, range="health_profile!A:E",
            valueInputOption="USER_ENTERED", body=body
        ).execute()
        return f"已記錄健康狀態：HP={hp}, 體質={constitution}"
    except Exception as e: return f"記錄失敗: {str(e)}"

def get_user_profile(domain: str = None):
    """讀取 User Profile。"""
    service = get_google_service('sheets', 'v4') 
    if not service: return "錯誤：無法連線至 Google Sheets"
    try:
        result = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="user_profile!A:D").execute()
        rows = result.get('values', [])
        if not rows: return "設定檔是空的。"
        formatted_text = "【使用者個人檔案】\n"
        for row in rows[1:]:
            while len(row) < 3: row.append("")
            dom, attr, val = row[0], row[1], row[2]
            if domain and domain.lower() not in dom.lower(): continue
            formatted_text += f"- [{dom}] {attr}: {val}\n"
        return formatted_text
    except Exception as e: return f"讀取設定檔失敗: {str(e)}"

def update_user_profile(domain: str, attribute: str, value: str):
    """更新 User Profile。"""
    service = get_google_service('sheets', 'v4') 
    if not service: return "錯誤：無法連線至 Google Sheets"
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        values = [[domain, attribute, value, today]]
        body = {'values': values}
        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID, range="user_profile!A:D",
            valueInputOption="USER_ENTERED", body=body
        ).execute()
        return f"已更新設定檔：[{domain}] {attribute} -> {value}"
    except Exception as e: return f"更新失敗: {str(e)}"

def add_recipe(name: str, main_ing: str, season: str, tags: str, link: str, note: str = ""):
    """將食譜存入 'recipes' 頁籤。"""
    service = get_google_service('sheets', 'v4') 
    if not service: return "錯誤：無法連線至 Google Sheets"
    try:
        values = [[name, main_ing, season, tags, link, note]]
        body = {'values': values}
        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID, range="recipes!A:F",
            valueInputOption="USER_ENTERED", body=body
        ).execute()
        return f"🍽️ 食譜已登錄：{name}"
    except Exception as e: return f"食譜儲存失敗: {str(e)}"