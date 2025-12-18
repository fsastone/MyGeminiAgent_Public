# tools/weather.py
import requests
import urllib3
from services.google_api import CWA_API_KEY

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_weather_forecast(location: str = "臺北市"):
    """呼叫中央氣象署 API 取得精簡版天氣預報。"""
    if not CWA_API_KEY: return "錯誤：找不到 CWA_API_KEY"

# 【修正 1】將參數從 URL 字串中拆出來，放入 params 字典
    # 這樣 requests 會自動處理中文編碼 ("臺北市" -> "%E8%87%BA...")
    base_url = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001"
    params = {
        "Authorization": CWA_API_KEY,
        "format": "JSON",
        "locationName": location,
        "sort": "time"
    }

    try:
        # 使用 params 參數傳遞
        response = requests.get(base_url, params=params, verify=False)
        data = response.json()
        
        if not data.get('success') == 'true':
            return f"氣象署 API 回傳錯誤: {data}"

        # 【修正 2】防呆機制：檢查是否真的有抓到該地點的資料
        if not data['records']['location']:
            return f"找不到地點 '{location}' 的氣象資料，請確認地點名稱是否正確。"

        location_data = data['records']['location'][0]
        elements = location_data['weatherElement']
        
        report_lines = []
        
        # 【修正 3】動態計算要抓幾個時段
        # 先抓出第一組 element 的 time 清單長度，以此為準
        # 我們希望抓 2 個，但如果 API 只給 1 個，就只抓 1 個 (min 函數)
        available_periods = len(elements[0]['time'])
        loop_count = min(2, available_periods)

        if loop_count == 0:
            return "氣象局目前暫無預報資料。"

        for i in range(loop_count):
            start_str = elements[0]['time'][i]['startTime'] 
            # 抓取小時 (例如 12:00:00 -> 12)
            hour = int(start_str.split(' ')[1].split(':')[0])
            
            # 1. 時段顯示名稱
            if 5 <= hour < 11: time_desc = "早晨"
            elif 11 <= hour < 13: time_desc = "中午"
            elif 13 <= hour < 17: time_desc = "下午"
            elif 17 <= hour < 19: time_desc = "傍晚"
            elif 19 <= hour < 23: time_desc = "晚間"
            else: time_desc = "深夜"

            # 2. 數值取得 (使用 try-except 避免結構改變時崩潰)
            try:
                wx_name = elements[0]['time'][i]['parameter']['parameterName']
                pop_val = int(elements[1]['time'][i]['parameter']['parameterName'])
                min_t = elements[2]['time'][i]['parameter']['parameterName']
                max_t = elements[4]['time'][i]['parameter']['parameterName']
            except (KeyError, IndexError, ValueError):
                continue # 若這筆資料有缺損，跳過

            # 3. Emoji 邏輯
            if "雷" in wx_name: wx_icon = "⛈️"
            elif "雨" in wx_name: wx_icon = "🌧️"
            elif "雲" in wx_name or "陰" in wx_name: wx_icon = "🌥️"
            else: 
                is_daytime = 6 <= hour < 18
                wx_icon = "☀️" if is_daytime else "🌙"

            pop_icon = "🌂" if pop_val == 0 else ("☂️" if pop_val <= 50 else "☔")
            
            line = f"- {time_desc} {wx_icon}{wx_name} {pop_icon}{pop_val}% 🌡️{min_t} - {max_t}℃"
            report_lines.append(line)
            
        header = f"【{location}今日天氣】"
        body = "\n".join(report_lines)
    
        return f"{header}\n{body}"

    except Exception as e:
        # 加入錯誤追蹤 print
        print(f"❌ 天氣 API 報錯細節: {str(e)}", flush=True)
        return f"天氣查詢失敗: {str(e)}"