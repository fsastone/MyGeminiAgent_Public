# tools/todo_list.py
from services.google_api import get_google_service

# 定義清單別名對應 (Key 為 AI 可能生成的詞，Value 為實際清單名稱)
LIST_MAPPING = {
    "default": "日常待辦",
    "tasks": "日常待辦",
    "日常": "日常待辦",
    "daily": "日常待辦",
    "中期": "中期計畫",
    "計畫": "中期計畫",
    "plan": "中期計畫"
}

def _get_tasklist_id(service, list_title: str):
    # 1. 前處理：正規化輸入名稱
    query_title = list_title.strip()
    
    # 2. 查表對應：如果 AI 給的是別名，轉換成真實名稱
    # 這裡做一個簡單的關鍵字包含檢查
    real_title = query_title
    for key, val in LIST_MAPPING.items():
        if key in query_title.lower():
            real_title = val
            break
            
    print(f"查詢清單 '{list_title}' -> 對應為 '{real_title}'")

    try:
        results = service.tasklists().list().execute()
        items = results.get('items', [])
        
        # 3. 精確比對
        for item in items:
            if item['title'] == real_title: 
                return item['id']
        
        # 4. 若找不到，嘗試退回預設清單或報錯
        # 這裡改為：若找不到指定清單，自動存入「日常待辦」並標註原意
        for item in items:
            if item['title'] == "日常待辦": # 這裡請填入你最常用的清單名稱
                return item['id']
                
        return "@default"
    except Exception: return None

def add_todo_task(title: str, notes: str = "", list_name: str = "Default"):
    """新增待辦事項。"""
    service = get_google_service('tasks', 'v1') 
    if not service: return "錯誤：無法連線 Google Tasks"

    tasklist_id = _get_tasklist_id(service, list_name)
    if not tasklist_id:
        return f"錯誤：找不到清單 '{list_name}' 且無法對應至預設清單。"

    try:
        task_body = {'title': title, 'notes': notes}
        result = service.tasks().insert(tasklist=tasklist_id, body=task_body).execute()
        return f"已建立任務於【{list_name} (ID對應成功)】：{result.get('title')}"
    except Exception as e:
        return f"建立失敗: {e}"

def get_todo_tasks(list_name: str = "日常待辦", max_results: int = 10):
    """查詢待辦事項。"""
    service = get_google_service('tasks', 'v1') 
    if not service: return "錯誤：無法連線 Google Tasks"

    tasklist_id = _get_tasklist_id(service, list_name)
    if not tasklist_id: return f"找不到名為 '{list_name}' 的清單。"

    try:
        results = service.tasks().list(
            tasklist=tasklist_id, showCompleted=False, maxResults=max_results
        ).execute()
        items = results.get('items', [])
        if not items: return f"清單【{list_name}】目前沒有未完成項目。"

        formatted_tasks = f"【{list_name} 清單】\n"
        for item in items:
            title = item.get('title')
            notes = item.get('notes', '')
            note_str = f" ({notes})" if notes else ""
            formatted_tasks += f"• {title}{note_str}\n"
        return formatted_tasks
    except Exception as e:
        return f"查詢失敗: {e}"