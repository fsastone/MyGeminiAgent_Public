# tools/todo_list.py
from services.google_api import get_google_service

def _get_tasklist_id(service, list_title: str):
    try:
        results = service.tasklists().list().execute()
        items = results.get('items', [])
        for item in items:
            if item['title'] == list_title: return item['id']
        if list_title == "Default" or list_title == "@default": return "@default"
        return None
    except Exception: return None

def add_todo_task(title: str, notes: str = "", list_name: str = "Default"):
    """新增待辦事項。"""
    service = get_google_service('tasks', 'v1') 
    if not service: return "錯誤：無法連線 Google Tasks"

    tasklist_id = _get_tasklist_id(service, list_name)
    if not tasklist_id:
        tasklist_id = "@default"
        notes = f"[原欲存入: {list_name}] {notes}"

    try:
        task_body = {'title': title, 'notes': notes}
        result = service.tasks().insert(tasklist=tasklist_id, body=task_body).execute()
        return f"已建立任務於【{list_name}】：{result.get('title')}"
    except Exception as e:
        return f"建立失敗: {e}"

def get_todo_tasks(list_name: str = "Default", max_results: int = 10):
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