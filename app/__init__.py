"""Flask 应用工厂与统一 JSON 错误处理。"""

from __future__ import annotations

import os

from flask import Flask, jsonify

from .errors import CalibrationError
from .routes import bp
from .storage import SpanStore


def create_app(store_path: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config["SPAN_STORE"] = SpanStore(
        store_path or os.environ.get("CATENARY_STORE", "data/spans.json")
    )
    app.register_blueprint(bp)

    @app.errorhandler(CalibrationError)
    def _handle_domain(err: CalibrationError):
        payload = {"error": err.error_code, "message": err.message}
        if err.details:
            payload["details"] = err.details
        return jsonify(payload), err.status_code

    @app.errorhandler(404)
    def _handle_404(_err):
        return jsonify({"error": "not_found", "message": "路径不存在"}), 404

    @app.errorhandler(405)
    def _handle_405(_err):
        return jsonify({"error": "method_not_allowed", "message": "方法不允许"}), 405

    return app
