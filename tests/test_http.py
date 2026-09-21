"""HTTP 层与具名档存储的端到端测试（Flask test client）。"""

from __future__ import annotations

import math
import os

import pytest

from app import create_app
from app.catenary import Catenary


@pytest.fixture()
def client(tmp_path):
    store = tmp_path / "spans.json"
    app = create_app(str(store))
    app.config.update(TESTING=True)
    return app.test_client()


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok"}


def test_named_span_register_list_get(client):
    r = client.post("/api/spans", json={
        "name": "A档", "span": 240.0, "height_difference": 18.0, "w": 10.5})
    assert r.status_code == 201, r.get_json()
    assert r.get_json()["name"] == "A档"

    r = client.get("/api/spans")
    assert r.status_code == 200
    listed = r.get_json()["spans"]
    assert listed == [{
        "name": "A档", "span": 240.0, "height_difference": 18.0, "w": 10.5}]

    r = client.get("/api/spans/A档")
    assert r.status_code == 200
    assert r.get_json()["span"] == 240.0


def test_span_persists_across_app_instances(tmp_path):
    store = str(tmp_path / "spans.json")
    app1 = create_app(store)
    app1.test_client().post("/api/spans", json={
        "name": "持久档", "span": 150.0, "height_difference": 0.0, "w": 8.0})
    app2 = create_app(store)
    r = app2.test_client().get("/api/spans/持久档")
    assert r.status_code == 200
    assert r.get_json()["w"] == 8.0


def test_duplicate_and_unknown_span(client):
    body = {"name": "S", "span": 100.0, "height_difference": 0.0, "w": 9.0}
    assert client.post("/api/spans", json=body).status_code == 201
    r = client.post("/api/spans", json=body)
    assert r.status_code == 409
    assert r.get_json()["error"] == "span_exists"

    r = client.get("/api/spans/不存在")
    assert r.status_code == 404
    assert r.get_json()["error"] == "span_not_found"

    r = client.post("/api/spans/不存在/calibrate", json={"sag": 3.0})
    assert r.status_code == 404


def test_named_span_calibrate_only_needs_measurement(client):
    client.post("/api/spans", json={
        "name": "N", "span": 200.0, "height_difference": 12.0, "w": 10.0})
    # 先用已知 H 正算出跨中弧垂
    H, w, L, h = 2000.0, 10.0, 200.0, 12.0
    sag = Catenary(L, h, H / w).sag(L / 2.0)

    # 点名档时只补测量弧垂（测点默认跨中）
    r = client.post("/api/spans/N/calibrate", json={"sag": sag})
    assert r.status_code == 200, r.get_json()
    out = r.get_json()
    assert out["H"] == pytest.approx(H, rel=1e-9)
    assert out["c"] == pytest.approx(H / w, rel=1e-9)
    assert out["measurement"]["x"] == pytest.approx(L / 2.0)
    assert out["closure"]["passed"] is True
    assert out["vertex_x"] < L / 2.0  # 右端高，低点偏左
    assert "length" in out and out["length"] > L
    assert len(out["points"]) == 21  # 默认 21 点


@pytest.mark.parametrize("h", [-18.0, 18.0, 0.0])
def test_named_span_matches_anonymous_pointwise(client, h):
    """点名存档算出的曲线，与把同一份几何直接交进去算的，逐点一致。

    回归钉：存档曾把负高差存成 |h|，导致下坡档点名标定 / 正算的最低点
    与整条剖面关于跨中镜像。负高差一档必须钉死；正高差与等高行为不变。
    """
    L, w, H, x_m = 200.0, 10.0, 2000.0, 120.0
    client.post("/api/spans", json={
        "name": "对照档", "span": L, "height_difference": h, "w": w})
    # 存档必须原样保留高差符号
    assert client.get("/api/spans/对照档").get_json()["height_difference"] == h

    # ---- 标定：同一测量，点名 vs 匿名 ----
    sag = Catenary(L, h, H / w).sag(x_m)
    named = client.post("/api/spans/对照档/calibrate",
                        json={"sag": sag, "x": x_m}).get_json()
    anon = client.post("/api/calibrate", json={
        "span": L, "height_difference": h, "w": w, "sag": sag, "x": x_m}).get_json()
    assert named["vertex_x"] == pytest.approx(anon["vertex_x"], rel=1e-12)
    assert named["H"] == pytest.approx(anon["H"], rel=1e-12)
    assert named["length"] == pytest.approx(anon["length"], rel=1e-12)
    for p_named, p_anon in zip(named["points"], anon["points"]):
        assert p_named["x"] == p_anon["x"]
        assert p_named["y"] == pytest.approx(p_anon["y"], rel=1e-12)
        assert p_named["chord_y"] == pytest.approx(p_anon["chord_y"], rel=1e-12)
        assert p_named["sag"] == pytest.approx(p_anon["sag"], rel=1e-12)

    # ---- 正算：同一 H，点名 vs 匿名 ----
    named_fwd = client.post("/api/spans/对照档/forward", json={"H": H}).get_json()
    anon_fwd = client.post("/api/forward", json={
        "H": H, "w": w, "span": L, "height_difference": h}).get_json()
    assert named_fwd["vertex_x"] == pytest.approx(anon_fwd["vertex_x"], rel=1e-12)
    for p_named, p_anon in zip(named_fwd["points"], anon_fwd["points"]):
        assert p_named["y"] == pytest.approx(p_anon["y"], rel=1e-12)

    # ---- 最低点必须偏向地势低的一端（下坡档偏右，且不在跨中） ----
    if h < 0:
        assert named["vertex_x"] > L / 2.0
    elif h > 0:
        assert named["vertex_x"] < L / 2.0
    else:
        assert named["vertex_x"] == pytest.approx(L / 2.0)


def test_calibrate_level_midspan_math(client):
    L, c, w = 100.0, 40.0, 9.81
    sag = c * (math.cosh(L / (2 * c)) - 1)
    r = client.post("/api/calibrate",
                    json={"span": L, "height_difference": 0.0, "w": w, "sag": sag})
    assert r.status_code == 200, r.get_json()
    out = r.get_json()
    assert out["c"] == pytest.approx(c, rel=1e-11)
    assert out["H"] == pytest.approx(w * c, rel=1e-11)
    assert out["vertex_x"] == pytest.approx(50.0, abs=1e-9)
    assert out["computed_sag"] == pytest.approx(sag, rel=1e-12)
    assert out["closure"]["rel_error"] < 1e-12


def test_forward_then_calibrate_roundtrip(client):
    body = {"H": 800.0, "w": 10.0, "span": 160.0, "height_difference": -6.0}
    r = client.post("/api/forward", json=body)
    assert r.status_code == 200
    mid = [p for p in r.get_json()["points"] if abs(p["x"] - 80.0) < 1e-9][0]

    r2 = client.post("/api/calibrate", json={
        "span": 160.0, "height_difference": -6.0, "w": 10.0,
        "sag": mid["sag"], "x": 80.0})
    assert r2.status_code == 200
    assert r2.get_json()["H"] == pytest.approx(800.0, rel=1e-9)


def test_custom_sample_points_and_out_of_range(client):
    r = client.post("/api/forward", json={
        "H": 500.0, "w": 10.0, "span": 100.0, "height_difference": 0.0,
        "points": [0.0, 50.0, 100.0]})
    assert r.status_code == 200
    assert [p["x"] for p in r.get_json()["points"]] == [0.0, 50.0, 100.0]

    r = client.post("/api/forward", json={
        "H": 500.0, "w": 10.0, "span": 100.0, "points": [120.0]})
    assert r.status_code == 400
    assert "越出" in r.get_json()["message"]


def test_http_error_mapping(client):
    cases = [
        ({"H": -1, "w": 9.81, "span": 100}, 400, "invalid_parameter"),
        ({"H": 100, "w": 0, "span": 100}, 400, "invalid_parameter"),
        ({"span": 0, "w": 9.81, "sag": 2}, 400, "invalid_parameter"),
        ({"span": 100, "w": 9.81, "sag": -1}, 400, "invalid_parameter"),
        ({"span": 100, "height_difference": 30, "w": 9.81,
          "sag": 1.0, "x": 50}, 422, "span_unreachable"),
        ({"span": 100, "w": 9.81, "sag": 3, "x": 0}, 422, "sag_contradiction"),
    ]
    for body, code, err in cases:
        r = client.post("/api/calibrate", json=body)
        assert r.status_code == code, (body, r.get_json())
        assert r.get_json()["error"] == err


def test_missing_field_and_bad_json(client):
    r = client.post("/api/calibrate", json={"span": 100.0, "w": 9.81})
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid_parameter"

    r = client.post("/api/forward", data="not json")
    assert r.status_code == 400
