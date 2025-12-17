# tools/common.py
from datetime import datetime
import bisect

def get_current_solar_term():
    """精準計算目前的節氣與下一個節氣。"""
    solar_terms_data = [
        (1, 5, "小寒"), (1, 20, "大寒"), (2, 4, "立春"), (2, 19, "雨水"),
        (3, 5, "驚蟄"), (3, 20, "春分"), (4, 4, "清明"), (4, 19, "穀雨"),
        (5, 5, "立夏"), (5, 21, "小滿"), (6, 5, "芒種"), (6, 21, "夏至"),
        (7, 7, "小暑"), (7, 22, "大暑"), (8, 7, "立秋"), (8, 23, "處暑"),
        (9, 7, "白露"), (9, 23, "秋分"), (10, 8, "寒露"), (10, 23, "霜降"),
        (11, 7, "立冬"), (11, 22, "小雪"), (12, 7, "大雪"), (12, 21, "冬至")
    ]
    now = datetime.now()
    year = now.year
    dates = []
    term_names = []
    for month, day, name in solar_terms_data:
        try:
            d = datetime(year, month, day)
            dates.append(d)
            term_names.append(name)
        except: pass

    idx = bisect.bisect_right(dates, now)
    current_term = term_names[idx - 1] if idx > 0 else term_names[-1]
    current_term_date = dates[idx - 1] if idx > 0 else dates[-1]

    if idx < len(dates):
        next_term = term_names[idx]
        next_term_date = dates[idx]
    else:
        next_term = solar_terms_data[0][2]
        next_term_date = datetime(year + 1, solar_terms_data[0][0], solar_terms_data[0][1])

    days_until = (next_term_date - now).days + 1
    msg = f"目前節氣：{current_term} (已過 {abs((now - current_term_date).days)} 天)\n"
    msg += f"下個節氣：{next_term} (再 {days_until} 天)"
    
    if days_until <= 2: msg += f"\n>>> 注意：即將進入 {next_term}，請注意氣候轉換與調養！"
    elif abs((now - current_term_date).days) <= 1: msg += f"\n>>> 注意：正值 {current_term} 節氣轉換期！"
    return msg