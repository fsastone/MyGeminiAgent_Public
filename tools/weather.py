# tools/weather.py
import requests
import urllib3
from services.google_api import CWA_API_KEY

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_weather_forecast(location: str = "臺北市"):
    """呼叫中央氣象署 API 取得精簡版天氣預報。"""
    if not CWA_API_KEY: return "錯誤：找不到 CWA_API_KEY"

    api_url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001?Authorization={CWA_API_KEY}&format=JSON&locationName={location}"
    try:
        response = requests.get(api_url, verify=False)
        data = response.json()
        if not data.get('success') == 'true': return f"氣象署 API 回傳錯誤: {data}"

        location_data = data['records']['location'][0]
        elements = location_data['weatherElement']
        report_lines = []
        for i in range(0, 2):
            start_str = elements[0]['time'][i]['startTime']
            hour = int(start_str.split(' ')[1].split(':')[0])
            
            if 5 <= hour < 11: time_desc = "早晨"
            elif 11 <= hour < 13: time_desc = "中午"
            elif 13 <= hour < 17: time_desc = "下午"
            elif 17 <= hour < 19: time_desc = "傍晚"
            elif 19 <= hour < 23: time_desc = "晚間"
            else: time_desc = "深夜"

            wx_name = elements[0]['time'][i]['parameter']['parameterName']
            pop_val = int(elements[1]['time'][i]['parameter']['parameterName'])
            min_t = elements[2]['time'][i]['parameter']['parameterName']
            max_t = elements[4]['time'][i]['parameter']['parameterName']

            if "雷" in wx_name: wx_icon = "⛈️"
            elif "雨" in wx_name: wx_icon = "🌧️"
            elif "雲" in wx_name or "陰" in wx_name: wx_icon = "🌥️"
            else:
                is_daytime = 6 <= hour < 18
                wx_icon = "☀️" if is_daytime else "🌙"
            pop_icon = "🌂" if pop_val == 0 else ("☂️" if pop_val <= 50 else "☔")
            
            line = f"- {time_desc} {wx_icon}{wx_name} {pop_icon}{pop_val}% 🌡️{min_t} ~ {max_t}℃"
            report_lines.append(line)
            
        header = f"【{location}今日天氣】"
        body = "\n".join(report_lines)
        return f"{header}\n{body}"
    except Exception as e:
        return f"天氣查詢失敗: {str(e)}"