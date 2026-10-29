"""Small, dependency-free HTTP service for AKS deployment demonstrations."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
import json
import os
from urllib.parse import urlsplit

VERSION = version("aks-pilot-demo")
PAGE = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AKS Pilot Demo</title><style>body{background:#0b1423;color:#e8edf5;font:18px system-ui;margin:12vh auto;padding:24px;max-width:800px}small{color:#7dd3fc}h1{font-size:48px;margin:16px 0}p{color:#aebfd5;line-height:1.7}code{color:#7dd3fc}article{border:1px solid #31425d;border-radius:18px;padding:32px}a{color:#7dd3fc}</style><article><small>AZURE KUBERNETES SERVICE / RELEASE DEMO</small><h1>From Git to your cluster.</h1><p>A packaged, non-root Python service. The image digest identifies the build; the Git commit identifies the desired deployment.</p><p>Running release <code>VERSION_VALUE</code></p><p><a href="/api/version">Release JSON</a> · <a href="/healthz">Liveness</a> · <a href="/readyz">Readiness</a></p></article></html>""".replace("VERSION_VALUE",VERSION)

def response(path):
    route=urlsplit(path).path
    if route=="/": return 200,"text/html; charset=utf-8",PAGE.encode()
    if route in ("/healthz","/readyz"):
        return 200,"application/json",json.dumps({"status":"ok","version":VERSION}).encode()
    if route=="/api/version":
        return 200,"application/json",json.dumps({"service":"aks-pilot-demo","version":VERSION,"hostname":os.environ.get("HOSTNAME","local")}).encode()
    return 404,"application/json",b'{"error":"not_found"}'

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        status,kind,body=response(self.path)
        self.send_response(status)
        self.send_header("Content-Type",kind)
        self.send_header("Content-Length",str(len(body)))
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.end_headers()
        self.wfile.write(body)
    def do_HEAD(self):
        status,kind,body=response(self.path)
        self.send_response(status)
        self.send_header("Content-Type",kind)
        self.send_header("Content-Length",str(len(body)))
        self.end_headers()

def main():
    server=ThreadingHTTPServer(("0.0.0.0",8080),Handler)
    server.daemon_threads=True
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()

if __name__=="__main__": main()
