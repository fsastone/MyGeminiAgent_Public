# tools/weather.py
import requests
import urllib3
from datetime import datetime
from services.google_api import CWA_API_KEY
import re

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 地點模糊對應表
LOCATION_FIX = {
    "台北": "臺北市",
    "台北市": "臺北市",
    "臺北": "臺北市"
}

def _normalize_location(loc: str) -> str:
    # 1. 查表替換
    if loc in LOCATION_FIX:
        return LOCATION_FIX[loc]
    # 2. 自動補字 (若使用者只說 "新北")
    if not loc.endswith("市") and not loc.endswith("縣"):
        # 簡單推測，大部分是市，少部分是縣(如新竹縣/市)，這裡做最簡單的防呆
        # 建議讓 AI 盡量傳完整，這裡做最後一道防線
        if len(loc) == 2: return f"{loc}市"
    return loc

def get_weather_forecast(location: str = "臺北市"):
    """呼叫中央氣象署 API 取得精簡版天氣預報 (36小時)。"""
    if not CWA_API_KEY: return "錯誤：找不到 CWA_API_KEY"

    target_location = _normalize_location(location)

    # 將參數從 URL 字串中拆出來，放入 params 字典
    # 這樣 requests 會自動處理中文編碼 ("臺北市" -> "%E8%87%BA...")
    base_url = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001"
    params = {
        "Authorization": CWA_API_KEY,
        "format": "JSON",
        "locationName": target_location,
        "sort": "time"
    }

    try:
        # 使用 params 參數傳遞
        response = requests.get(base_url, params=params, verify=False)
        data = response.json()
        
        if not data.get('success') == 'true':
            return f"氣象署 API 回傳錯誤: {data}"

        # 檢查是否真的有抓到該地點的資料
        if not data['records']['location']:
            return f"找不到地點 '{target_location}' (原始輸入:{location}) 的資料，請確認行政區名稱。"

        location_data = data['records']['location'][0]
        elements = location_data['weatherElement']
        
        report_lines = []
        
        # 動態計算要抓幾個時段
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
            
            line = f"- {time_desc} {wx_icon}{wx_name} {pop_icon}{pop_val}% 🌡️{min_t} ~ {max_t}℃"
            report_lines.append(line)
            
        header = f"【{location}今日天氣】"
        body = "\n".join(report_lines)
    
        return f"{header}\n{body}"

    except Exception as e:
        # 加入錯誤追蹤 print
        print(f"❌ 天氣 API 報錯細節: {str(e)}", flush=True)
        return f"天氣查詢失敗: {str(e)}"

def get_weekly_forecast(location: str = "臺北市"):
    """
    呼叫 F-D0047-091 (臺灣各縣市未來1週天氣預報)
    V6 智慧摘要版：
    1. 數據：顯示具體的「低溫-高溫」區間。
    2. 視覺：依據「平均溫度」繪製雙字元寬長條圖，呈現一週冷熱趨勢。
    3. 趨勢：自動計算本週均溫極值，動態調整長條圖比例。
    """
    if not CWA_API_KEY: return "錯誤：找不到 CWA_API_KEY"
    
    target_location = _normalize_location(location)
    
    # F-D0047-091: 鄉鎮未來1週天氣預報-臺灣各縣市未來1週天氣預報
    base_url = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-D0047-091"
    params = {
        "Authorization": CWA_API_KEY,
        "format": "JSON",
        "locationName": target_location,
        "sort": "time"
    }

    try:
        response = requests.get(base_url, params=params, verify=False)
        data = response.json()
        
        if not data.get('success') == 'true':
            return f"一週預報 API 回傳錯誤: {data}"
            
        records = data.get('records', {})
        loc_list = []
        
        # 結構通常為: records -> Locations[0] -> Location
        if 'Locations' in records:
            datasets = records['Locations']
            if isinstance(datasets, list) and len(datasets) > 0:
                dataset = datasets[0]
                loc_list = dataset.get('Location', dataset.get('location', []))
        elif 'locations' in records:
            loc_list = records['locations'][0]['location'] if isinstance(records['locations'], list) else records['locations']
        
        if not loc_list: return "解析失敗：找不到 Location 資料。"

        # 篩選地點
        target_data = None
        for item in loc_list:
            name = item.get('LocationName', item.get('locationName'))
            if name == target_location:
                target_data = item
                break
        
        if not target_data: return f"找不到地點 '{target_location}' 的資料。"
        
        # 取得氣象因子
        weather_elements = target_data.get('WeatherElement', target_data.get('weatherElement'))
        if not weather_elements: return f"解析失敗：找不到 WeatherElement 欄位。"
        
        # --- 資料收集 ---
        forecast_list = [] # 暫存每一天的資料物件
        for el in weather_elements:
            el_name = el.get('ElementName', el.get('elementName'))
            time_list = el.get('Time', el.get('time', []))
            
            target_key = "value"
            store_key = None

            if el_name in ["最高溫度", "MaxTemperature"]:
                target_key, store_key = "MaxTemperature", "MaxT"
            elif el_name in ["最低溫度", "MinTemperature"]:
                target_key, store_key = "MinTemperature", "MinT"
            elif el_name in ["天氣預報綜合描述", "WeatherDescription"]:
                target_key, store_key = "WeatherDescription", "WxDesc"
            else:
                continue

            for item in time_list:
                st = item.get('StartTime', item.get('startTime'))
                if not st: continue
                try:
                    dt_obj = datetime.fromisoformat(st)
                except ValueError: continue

                # 只抓白天 (06:00 - 18:00)
                if 6 <= dt_obj.hour < 18:
                    key = dt_obj.isoformat()
                    
                    # 檢查 list 中是否已存在該時間點
                    day_data = next((d for d in forecast_list if d['time'] == key), None)
                    if not day_data:
                        day_data = {'time': key, 'dt': dt_obj}
                        forecast_list.append(day_data)
                    
                    e_values = item.get('ElementValue', item.get('elementValue', []))
                    val = "?"
                    if isinstance(e_values, list) and len(e_values) > 0:
                        val = e_values[0].get(target_key, "?")
                    
                    day_data[store_key] = val

        forecast_list.sort(key=lambda x: x['time'])
        if not forecast_list: return "無法提取白天預報資料。"

        # --- 數據計算 (Avg 與 降雨) ---
        # --- 數據清洗與計算 (關鍵：轉成 int 以利排版) ---
        weekly_avg_temps = []
        valid_days_count = 0
        cold_days = 0   # < 18度
        hot_days = 0    # > 28度
        comfort_days = 0 # 18~28度
        
        for day in forecast_list:
            try:
                max_t = int(day.get('MaxT', 0))
                min_t = int(day.get('MinT', 0))
                day['MaxT_Int'] = max_t
                day['MinT_Int'] = min_t
                # 計算均溫：(高+低)/2
                avg_t = (max_t + min_t) / 2
                day['AvgT'] = avg_t
                weekly_avg_temps.append(avg_t)
                valid_days_count += 1
                # 統計天數 (用於摘要)
                if avg_t < 18: cold_days += 1
                elif avg_t > 28: hot_days += 1
                else: comfort_days += 1
            except ValueError:
                day['MaxT_Int'] = 0
                day['MinT_Int'] = 0
                day['AvgT'] = 0
                
            # 提取降雨機率
            desc = day.get('WxDesc', '')
            pop_match = re.search(r"降雨機率(\d+)%", desc)
            day['PoP'] = int(pop_match.group(1)) if pop_match else 0
            
            # 簡化天氣描述 (只取狀態，如"多雲時陰")
            # 濾掉 "溫度..." 之後的廢話
            simple_wx = desc.split("。")[0]
            day['SimpleWx'] = simple_wx

        # --- 視覺化核心邏輯 (16 階解析度) ---
        # 找出本週均溫的「絕對區間」，以此作為繪圖的 0% ~ 100%
        # 為了避免線條太滿或太短，我們給上下界一點緩衝 (Buffer)
        if weekly_avg_temps:
            abs_min_avg = min(weekly_avg_temps) - 2 # 緩衝 2度
            abs_max_avg = max(weekly_avg_temps) + 2 # 緩衝 2度
            temp_range = abs_max_avg - abs_min_avg
        else:
            abs_min_avg, temp_range = 10, 10

        def get_double_char_bar(current_temp):
            """使用兩個字元顯示 16 階精細度的溫度條"""
            if temp_range <= 0: return "  "
            
            # 1. 計算總分 (0 ~ 16)
            ratio = (current_temp - abs_min_avg) / temp_range
            ratio = max(0, min(1, ratio)) # 限制 0~1
            score = int(ratio * 16)       # 映射到 0~16 階
            
            # 2. 定義積木 (包含全滿的 █)
            # blocks[0]是空白, blocks[8]是全滿
            blocks = " ▏▎▍▌▋▊▉█" 
            
            # 3. 分配給兩個字元
            # 第一個字元：最多拿 8 分
            score1 = min(8, score)
            # 第二個字元：拿剩下的分數 (最多也是 8 分)
            score2 = max(0, score - 8)
            
            return blocks[score1] + blocks[score2]

        # --- 最終輸出格式 ---
        week_days_list = ["一", "二", "三", "四", "五", "六", "日"]
        
        # 條件判斷
        if cold_days >= 5:
            summary = "🥶 本週皆偏寒冷，請務必注意保暖！"
        elif hot_days >= 5:
            summary = "🥵 本週皆偏炎熱，外出請注意補充水分。"
        elif comfort_days == valid_days_count: # 全部天數都在舒適區間
            summary = "😊 本週氣溫介於 18~28 度，天氣舒適宜人！"
        else:
            # 預設：顯示最冷與最熱
            hottest = max(forecast_list, key=lambda x: x.get('AvgT', 0))
            coldest = min(forecast_list, key=lambda x: x.get('AvgT', 0))
            h_day = week_days_list[hottest['dt'].weekday()]
            c_day = week_days_list[coldest['dt'].weekday()]
            summary = f"本週趨勢：週{h_day}最熱，週{c_day}最冷。"
        
        formatted_report = f"【{target_location} 一週天氣預報】\n{summary}\n\n"
        
        for day in forecast_list:
            d_str = day['dt'].strftime("%m/%d")
            w_str = week_days_list[day['dt'].weekday()]
            
            avg = day['AvgT']
            if avg >= 28: t_icon = "🔴"
            elif avg >= 24: t_icon = "🟠"
            elif avg >= 18: t_icon = "🟢"
            else: t_icon = "🔵"
            
            pop = day['PoP']
            # 使用 f-string 02d 補零，例如 5 -> 05
            pop_str = f"{pop:02d}%"
            if pop >= 60: wx_icon = "☔"
            elif pop >= 30: wx_icon = "🌧️"
            elif "晴" in day['SimpleWx']: wx_icon = "☀️"
            elif "多雲" in day['SimpleWx']: wx_icon = "🌥️"
            else: wx_icon = "☁️"

            # 溫度 (現在可以使用 :02d 了，因為 MinT_Int 是 int)
            # 格式範例: 15~20° (補零後: 15~20°)
            # 若為個位數: 08~09°
            min_str = f"{day['MinT_Int']:02d}"
            max_str = f"{day['MaxT_Int']:02d}"
            temp_str = f"{min_str}~{max_str}℃"
            
            # 取得雙字元長條圖
            bar_chart = get_double_char_bar(avg)
            
            # 格式: 12/23(二) 🔴 05% ☀️ 18~26° █▌
            formatted_report += f"{d_str} ({w_str}) {t_icon} | {wx_icon} {pop_str} | {temp_str} {bar_chart}\n"

        return formatted_report

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"天氣查詢失敗: {str(e)}"