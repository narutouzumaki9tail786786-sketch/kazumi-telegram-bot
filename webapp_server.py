"""
Kazumi Web App API Standalone WSGI Server
Runs Flask web server on port 5010 for Mini App requests
"""
import logging
from wsgiref.simple_server import WSGIServer, WSGIRequestHandler
from socketserver import ThreadingMixIn

from kazumi.config import PORT
from kazumi.web_app import create_web_app

class ThreadedWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True
    allow_reuse_address = True


class QuietWSGIRequestHandler(WSGIRequestHandler):
    """Do not let internet scanners fill PM2 error logs with harmless 404s."""

    def log_message(self, format, *args):
        status = str(args[1]) if len(args) > 1 else ""
        if status.startswith("5"):
            logging.getLogger("kazumi.web").warning(format, *args)

if __name__ == "__main__":
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    print(f"🌸 Kazumi Web App WSGI Server starting on port {PORT}... 🌸", flush=True)
    try:
        app = create_web_app()
        httpd = ThreadedWSGIServer(('0.0.0.0', PORT), QuietWSGIRequestHandler)
        httpd.set_app(app)
        httpd.serve_forever()
    except Exception as e:
        print(f"❌ WSGI Server Error: {e}", flush=True)
