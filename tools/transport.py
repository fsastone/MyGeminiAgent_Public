import os
import json
import requests
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# 車站代碼常數 (可擴充)
STATION_IDS = {
    "台北": "1000", "臺北": "1000",
    "板橋": "1020", "桃園": "1040", "鶯歌": "1070",
    "中壢": "1080", "新竹": "1210", "南港": "0990", "松山": "0980",
    "樹林": "1030", "七堵": "0970", "汐止": "0980"
}

#本地測試請以下路徑儲存 Token
#TOKEN_FILE = ".tdx_token"
#雲端部署請以下路徑儲存 Token
TOKEN_FILE = "/tmp/tdx_token.json"

class TDXClient:
    def __init__(self):
        self.client_id = os.getenv("TDX_CLIENT_ID")
        self.client_secret = os.getenv("TDX_CLIENT_SECRET")
        self.base_url = "https://tdx.transportdata.tw/api/basic"

    def get_token(self):
        """取得或更新 Access Token"""
        # 1. 嘗試從檔案讀取舊 Token
        if os.path.exists(TOKEN_FILE):
            try:
                with open(TOKEN_FILE, 'r') as f:
                    data = json.load(f)
                    # 檢查是否過期 (預留 600秒緩衝)
                    if data.get('expires_at', 0) > time.time() + 600:
                        return data['access_token']
            except Exception:
                pass # 讀取失敗就重新申請

        # 2. 重新向 TDX 申請 Token
        auth_url = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
        headers = {"content-type": "application/x-www-form-urlencoded"}
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        
        try:
            print("正在向 TDX 申請新 Token...", flush=True)
            response = requests.post(auth_url, headers=headers, data=data)
            response.raise_for_status()
            token_data = response.json()
            
            access_token = token_data['access_token']
            expires_in = token_data['expires_in']
            
            # 3. 寫入檔案快取
            with open(TOKEN_FILE, 'w') as f:
                json.dump({
                    "access_token": access_token,
                    "expires_at": time.time() + expires_in
                }, f)
                
            return access_token
        except Exception as e:
            print(f"TDX Token 申請失敗: {e}")
            return None
    
    def make_request(self, url):
        token = self.get_token()
        if not token: return None
        
        # 加入 User-Agent 避免被某些防火牆擋
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"API 請求失敗 ({url}): {e}")
            return None

# 初始化全域 Client
tdx_client = TDXClient()

def get_train_status(mode: str = "check", dep: str = None, arr: str = None):
    """
    查詢台鐵列車動態。
    參數 mode:
    - mode: "routine_morning" (早通勤), "routine_evening" (晚通勤), "check" (一般查詢)
    - dep: 出發站名稱 (如 "鶯歌"), 若未指定則參考 mode
    - arr: 抵達站名稱 (如 "台北"), 若未指定則參考 mode
    """
    now = datetime.now()
    target_date = now.strftime("%Y-%m-%d")
    
    # 1. 決定起訖站與時間範圍
    if dep and arr:
        # 【新增功能】若用戶指定了起訖站，優先使用
        origin, dest = dep, arr
        start_time = now
        end_time = now + timedelta(hours=1) # 預設查未來 1 小時
        title = f"即時資訊【{origin} >> {dest}】"
    
    elif mode == "routine_morning":
        origin, dest = "鶯歌", "台北"
        start_time = datetime.strptime(f"{target_date} 07:40", "%Y-%m-%d %H:%M")
        end_time = datetime.strptime(f"{target_date} 08:10", "%Y-%m-%d %H:%M")
        title = "上班通勤【鶯歌 >> 台北】"
    
    elif mode == "routine_evening":
        origin, dest = "台北", "鶯歌"
        start_time = datetime.strptime(f"{target_date} 18:00", "%Y-%m-%d %H:%M")
        end_time = datetime.strptime(f"{target_date} 18:50", "%Y-%m-%d %H:%M")
        title = "下班通勤【台北 >> 鶯歌】"
    
    else:
        # 預設 fallback
        origin, dest = "台北", "鶯歌"
        start_time = now
        end_time = now + timedelta(hours=1)
        title = f"即時資訊【{origin} >> {dest}】"

    origin_id, dest_id = STATION_IDS.get(origin), STATION_IDS.get(dest)
    if not origin_id or not dest_id: 
        return f"錯誤：找不到車站代碼 (目前支援: {list(STATION_IDS.keys())})"

    # 2. 呼叫時刻表 API (V3 DailyTrainTimetable/OD)
    schedule_url = f"https://tdx.transportdata.tw/api/basic/v3/Rail/TRA/DailyTrainTimetable/OD/{origin_id}/to/{dest_id}/{target_date}"
    schedule_data = tdx_client.make_request(schedule_url)
    
    if not schedule_data: return "無法取得列車時刻表 (API 無回應)。"
    if 'TrainTimetables' not in schedule_data: return f"{title}\n目前時段無列車資訊。"

    # 3. 呼叫誤點 API (V2 LiveTrainDelay)
    delay_url = "https://tdx.transportdata.tw/api/basic/v2/Rail/TRA/LiveTrainDelay"
    delay_data = tdx_client.make_request(delay_url)
    
    delay_map = {}
    if delay_data:
        # 情況 A: V2 回傳 List (你提供的格式)
        if isinstance(delay_data, list):
            for item in delay_data:
                delay_map[item['TrainNo']] = item.get('DelayTime', 0)
        # 情況 B: V3 回傳 Dict
        elif isinstance(delay_data, dict) and 'LiveTrainDelayTimes' in delay_data:
            for item in delay_data['LiveTrainDelayTimes']:
                delay_map[item['TrainNo']] = item.get('DelayTime', 0)

    # 4. 資料整合
    train_list = []
    
    for train in schedule_data['TrainTimetables']:
        train_info = train['TrainInfo']
        train_no = train_info['TrainNo']
        stop_times = train['StopTimes'] # 這是包含起訖點與中間停靠站的列表
        
        # 【關鍵修復】精確找到「起點」與「終點」的時刻
        # StopTimes 結構是 [ {StationID:..., DepartureTime:...}, ... ]
        origin_stop = next((t for t in stop_times if t['StationID'] == origin_id), None)
        dest_stop = next((t for t in stop_times if t['StationID'] == dest_id), None)
        
        if not origin_stop or not dest_stop: continue
        
        dep_str = origin_stop['DepartureTime']
        arr_str = dest_stop['ArrivalTime']
        
        # 轉成 datetime 比較
        try:
            dep_dt = datetime.strptime(f"{target_date} {dep_str}", "%Y-%m-%d %H:%M")
        except ValueError: continue # 跨日或格式錯誤跳過
        
        # 篩選時間
        if start_time <= dep_dt <= end_time:
            # 計算行車時間
            # arr_str 可能是 16:08，需轉 datetime
            arr_dt = datetime.strptime(f"{target_date} {arr_str}", "%Y-%m-%d %H:%M")
            duration = int((arr_dt - dep_dt).total_seconds() / 60)
            
            # 誤點資訊
            delay_min = int(delay_map.get(train_no, 0))
            
            # 車種顯示
            t_type = train_info.get('TrainTypeName', {}).get('Zh_tw', '')
            type_note = ""
            if any(x in t_type for x in ["自強", "普悠瑪", "太魯閣"]): type_note = " (自)"
            elif "莒光" in t_type: type_note = " (莒)"
            
            train_list.append({
                "dep": dep_str,
                "arr": arr_str,
                "duration": duration,
                "delay": delay_min,
                "type": type_note
            })

    # 排序
    train_list.sort(key=lambda x: x['dep'])
    
    if not train_list: return f"{title}\n此時段無列車行駛。"

    # 5. 格式化輸出
    output_lines = []
    has_delay = False
    
    for t in train_list:
        delay = t['delay']
        
        # 燈號與誤點顯示
        delay_text = ""
        if delay == 0:
            icon = "🟢"
            delay_text = ""
        elif delay <= 10:
            icon = "🟠"
            delay_text = f" + {delay}"
            has_delay = True
        else:
            icon = "🔴"
            delay_text = f" + {delay}"
            has_delay = True
            
        # 格式: 🟢 07:41 > 31 分 >> 08:12 (自)
        line = f"{icon} {t['dep']} > {t['duration']:02d} 分 >> {t['arr']}{delay_text}{t['type']}"
        output_lines.append(line)

    # 簡報模式 (僅通勤模式且全綠燈時)
    if "routine" in mode and not has_delay:
        return f"{title}\n🟢 區間內 {len(train_list)} 班列車全數運行正常。"

    return f"{title}\n" + "\n".join(output_lines)