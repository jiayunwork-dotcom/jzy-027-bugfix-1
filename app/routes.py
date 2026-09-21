"""HTTP 路由：具名档登记 / 查询 + 标定 + 正算。

    POST /api/spans                 登记具名几何档
    GET  /api/spans                 列出全部档（几何全文）
    GET  /api/spans/<name>          查询单档
    POST /api/calibrate             匿名标定（自带几何 + 测量）
    POST /api/spans/<name>/calibrate 对具名档补一个测量即可标定
    POST /api/forward               给定 H 正算整档曲线
    POST /api/spans/<name>/forward  对具名档补 H 正算
    GET  /healthz
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from .errors import CalibrationError, ValidationError
from . import service
from .storage import SpanStore

bp = Blueprint("api", __name__)


def _json() -> dict:
    if not request.is_json:
        raise CalibrationError("请求体必须是 application/json")
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise CalibrationError("请求体必须是 JSON 对象")
    return data


def _get(data: dict, key: str, default=None):
    if key not in data:
        raise ValidationError(f"缺少必填字段 {key}")
    return data[key]


def _store() -> SpanStore:
    return current_app.config["SPAN_STORE"]


# ---- 具名档 -------------------------------------------------------------
@bp.post("/api/spans")
def create_span():
    data = _json()
    rec = _store().create(
        _get(data, "name"),
        span=_get(data, "span"),
        height_difference=data.get("height_difference", 0.0),
        w=_get(data, "w"),
        overwrite=bool(data.get("overwrite", False)),
    )
    return jsonify(rec), 201


@bp.get("/api/spans")
def list_spans():
    return jsonify({"spans": _store().list()})


@bp.get("/api/spans/<name>")
def get_span(name: str):
    return jsonify(_store().get(name))


# ---- 标定 ---------------------------------------------------------------
@bp.post("/api/calibrate")
def calibrate_anonymous():
    data = _json()
    span = _get(data, "span")
    x = data.get("x", span / 2.0)  # 默认跨中
    return jsonify(
        service.calibrate(
            span=span,
            height_difference=data.get("height_difference", 0.0),
            w=_get(data, "w"),
            sag=_get(data, "sag"),
            x=x,
            points=data.get("points"),
        )
    )


@bp.post("/api/spans/<name>/calibrate")
def calibrate_named(name: str):
    span_rec = _store().get(name)
    data = _json()
    x = data.get("x", span_rec["span"] / 2.0)
    return jsonify(
        service.calibrate(
            span=span_rec["span"],
            height_difference=span_rec["height_difference"],
            w=span_rec["w"],
            sag=_get(data, "sag"),
            x=x,
            points=data.get("points"),
        )
    )


# ---- 正算 ---------------------------------------------------------------
def _points(data: dict):
    return data.get("points")


@bp.post("/api/forward")
def forward_anonymous():
    data = _json()
    return jsonify(
        service.forward_profile(
            H=_get(data, "H"),
            w=_get(data, "w"),
            span=_get(data, "span"),
            height_difference=data.get("height_difference", 0.0),
            points=_points(data),
        )
    )


@bp.post("/api/spans/<name>/forward")
def forward_named(name: str):
    span_rec = _store().get(name)
    data = _json()
    return jsonify(
        service.forward_profile(
            H=_get(data, "H"),
            w=span_rec["w"],
            span=span_rec["span"],
            height_difference=span_rec["height_difference"],
            points=_points(data),
        )
    )


@bp.get("/healthz")
def healthz():
    return jsonify({"status": "ok"})
