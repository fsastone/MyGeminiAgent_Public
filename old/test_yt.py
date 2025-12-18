from youtube_transcript_api import YouTubeTranscriptApi
import youtube_transcript_api as ymod
import inspect
print("Python exe:", inspect.getsourcefile)  # placeholder to confirm running context
print("youtube_transcript_api module file:", getattr(ymod, '__file__', None))
print("YouTubeTranscriptApi members:", [m for m in dir(YouTubeTranscriptApi) if not m.startswith('_')])

video_id = "dQw4w9WgXcQ" # Rick Astley 的影片 ID

print(f"正在測試影片 ID: {video_id}")

try:
    # call as instance method for this installed version
    api = YouTubeTranscriptApi()
    transcript_list = api.list(video_id)
    
    print("成功呼叫 list_transcripts！")
    print("這部影片可用的字幕語言有：")
    for t in transcript_list:
        print(f"- [{t.language_code}] {t.language} (是否為自動產生: {t.is_generated})")

    # 模擬 tools.py 的抓取邏輯
    transcript = transcript_list.find_transcript(['zh-TW', 'zh-Hant', 'zh', 'en'])
    print(f"\n成功抓取到語言: {transcript.language_code}")
    
    # 試抓前幾句
    content = transcript.fetch()
    # FetchedTranscriptSnippet uses attributes (e.g. .text)
    try:
        t0 = content[0].text
        t1 = content[1].text
        print(f"字幕預覽: {t0} {t1}...")
    except Exception:
        # fallback: show raw items if structure differs
        print("字幕預覽 (raw):", content[:2])

except Exception as e:
    print(f"測試失敗: {e}")