# 使用輕量級 Python 映像檔
FROM python:3.10-slim

# 【新增】設定時區環境變數
ENV TZ=Asia/Taipei

# 安裝時區資料 (因為 slim 版本可能精簡掉了，保險起見裝一下)
# 並建立 /etc/localtime 連結
RUN apt-get update && \
    apt-get install -y tzdata && \
    ln -fs /usr/share/zoneinfo/$TZ /etc/localtime && \
    echo $TZ > /etc/timezone && \
    apt-get clean

# 設定工作目錄
WORKDIR /app

# 複製需求檔並安裝
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製所有程式碼
# 注意：部屬時我們也會把 token.json 複製進去 (針對個人專案的簡易做法)
COPY . .

# 設定環境變數 (讓 Python 輸出直接顯示在 Log)
ENV PYTHONUNBUFFERED=1

# Cloud Run 會自動提供 PORT 環境變數，預設 8080
# 我們將使用 main.py 啟動
CMD exec python main.py