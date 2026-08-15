"""Standalone Flask application for the Kazumi Mini App.

This module intentionally has no dependency on ``main``.  The web PM2 process
therefore cannot import, initialise, or share the Telegram polling runtime.
"""

from pathlib import Path

from flask import Flask, jsonify, send_from_directory

from kazumi.webapp_api import register_webapp_api


def create_web_app() -> Flask:
    dist_folder = Path(__file__).resolve().parents[1] / "webapp" / "dist"
    app = Flask(__name__, static_folder=str(dist_folder), static_url_path="")
    register_webapp_api(app)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_webapp(path: str):
        if path.startswith("api/"):
            return jsonify({"ok": False, "error": "API Route Not Found"}), 404
        if path and (dist_folder / path).is_file():
            return send_from_directory(app.static_folder, path)
        return send_from_directory(app.static_folder, "index.html")

    return app
