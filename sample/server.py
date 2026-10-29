from http.server import HTTPServer, BaseHTTPRequestHandler
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"AKS pilot ready\n")
HTTPServer(("0.0.0.0",8080),Handler).serve_forever()
