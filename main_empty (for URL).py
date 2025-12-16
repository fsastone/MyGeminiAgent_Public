import os
from http.server import HTTPServer, BaseHTTPRequestHandler

# 一個最笨、最簡單的網頁伺服器，只為了告訴 Cloud Run "我活著"
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Hello! I am alive. waiting for the real bot code.")

    def do_POST(self):
        self.send_response(200)
        self.end_headers()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    print(f"Fake Bot running on port {port}")
    server.serve_forever()