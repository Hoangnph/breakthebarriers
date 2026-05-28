import http.server
import socketserver

PORT = 8000

class UTF8AndNoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Inject strict caching prevention headers
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def guess_type(self, path):
        ctype = super().guess_type(path)
        if ctype == 'text/html':
            return 'text/html; charset=utf-8'
        if ctype == 'application/json':
            return 'application/json; charset=utf-8'
        return ctype

if __name__ == '__main__':
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), UTF8AndNoCacheHandler) as httpd:
        print(f"Serving premium web app at http://localhost:{PORT}")
        print("Explicit UTF-8 charsets and No-Cache controls enabled.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")
