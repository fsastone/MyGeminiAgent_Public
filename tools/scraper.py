# tools/scraper.py
import requests
from bs4 import BeautifulSoup
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from services.google_api import get_google_service, SPREADSHEET_ID
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_youtube_video_id(url):
    try:
        parsed = urlparse(url)
        if parsed.hostname == 'youtu.be': return parsed.path[1:]
        if parsed.hostname in ('www.youtube.com', 'youtube.com'):
            if parsed.path == '/watch':
                query = parse_qs(parsed.query)
                return query.get('v', [None])[0]
            if parsed.path.startswith('/shorts/'): return parsed.path.split('/')[2]
    except Exception: pass
    return None

def scrape_web_content(url: str):
    print(f"正在處理網址: {url}")
    video_id = get_youtube_video_id(url)
    
    # 策略 A: YouTube
    if video_id:
        try:
            api = YouTubeTranscriptApi()
            transcript_list = api.list(video_id)
            transcript = transcript_list.find_transcript(['zh-TW', 'zh-Hant', 'zh-HK', 'zh', 'en', 'ja'])
            content = " ".join([item.text for item in transcript.fetch()])
            return f"【YouTube 字幕內容】\n{content[:5000]}"
        except Exception as e:
            return f"YouTube 字幕抓取失敗: {str(e)}"

    # 策略 B: 一般網頁
    try:
        headers = {'User-Agent': 'Mozilla/5.0 ... Chrome/91.0'}
        response = requests.get(url, headers=headers, timeout=10, verify=False)
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'html.parser')
        title = soup.title.string.strip() if soup.title else "無標題"
        paragraphs = soup.find_all('p')
        content = "\n".join([p.get_text().strip() for p in paragraphs if len(p.get_text()) > 10])
        return f"【網頁內容摘要】\n標題: {title}\n內容: {content[:3000]}"
    except Exception as e: return f"網頁爬取失敗: {str(e)}"

def save_to_inbox(url: str, note: str = ""):
    """將網頁連結儲存到 'inbox' 頁籤。"""
    service = get_google_service('sheets', 'v4') 
    if not service: return "錯誤：無法連線至 Google Sheets"

    # 先爬取內容
    scrape_result = scrape_web_content(url)
    # 簡易解析標題 (假設 scrape_result 格式如上)
    title = "未命名頁面"
    if "標題:" in scrape_result:
        try: title = scrape_result.split("標題:")[1].split("\n")[0].strip()
        except: pass
    elif "YouTube 字幕內容" in scrape_result:
        title = "YouTube 影片"

    try:
        today = datetime.now().strftime("%Y-%m-%d")
        values = [[today, url, title, note, "Unread"]]
        body = {'values': values}
        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID, range="inbox!A:E",
            valueInputOption="USER_ENTERED", body=body
        ).execute()
        return f"✅ 已收藏至 Inbox。\n{scrape_result[:200]}..."
    except Exception as e: return f"儲存失敗: {str(e)}"

def get_unread_inbox(limit: int = 5):
    """讀取 Inbox 中尚未閱讀的項目。"""
    service = get_google_service('sheets', 'v4') 
    if not service: return "錯誤：無法連線"
    try:
        result = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="inbox!A:E").execute()
        rows = result.get('values', [])
        if not rows: return "Inbox 是空的。"
        unread_items = []
        for index, row in enumerate(rows[1:], start=2):
            while len(row) < 5: row.append("")
            if row[4].strip().lower() != "read":
                full_title = row[2]
                display_title = full_title[:15] + "..." if len(full_title) > 15 else full_title
                unread_items.append(f"• [{index}] {display_title}\n  ({row[1]})")
            if len(unread_items) >= limit: break
        if not unread_items: return "Inbox 目前沒有未讀項目。"
        return "【未讀清單】\n" + "\n".join(unread_items)
    except Exception as e: return f"讀取失敗: {str(e)}"

def mark_inbox_as_read(row_ids_str: str):
    """將 Inbox 項目標記為已讀。"""
    service = get_google_service('sheets', 'v4') 
    if not service: return "錯誤：無法連線"
    try:
        row_ids = [int(x.strip()) for x in row_ids_str.split(',') if x.strip().isdigit()]
        for row_id in row_ids:
            service.spreadsheets().values().update(
                spreadsheetId=SPREADSHEET_ID, range=f"inbox!E{row_id}",
                valueInputOption="USER_ENTERED", body={'values': [["Read"]]}
            ).execute()
        return f"已將 ID {row_ids} 標記為已讀。"
    except Exception as e: return f"更新失敗: {str(e)}"