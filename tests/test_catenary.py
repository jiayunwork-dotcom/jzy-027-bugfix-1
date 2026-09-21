"""锁住悬链几何核心行为的测试。

对应验收清单：
  1. 等高跨中弧垂对上闭式 c(cosh(L/2c)-1)
  2. 正算再反演 H 闭合（钉死的相对容差）
  3. 高差加大则最低点偏向低端，不能还报跨中
  4. 大垂度档抛物近似系统偏短
  5. H 非正被拒
  6. 档距非正被拒
  7. 弧垂与高差矛盾时失败而不是硬画
另含：索长恒等式、越界取样、够不着、非正弧垂等。
"""

from __future__ import annotations

import math

import pytest

from app.catenary import Catenary, reachable_c
from app.errors import ContradictionError, UnreachableError, ValidationError
from app.inversion import invert_sag
from app.service import CLOSURE_RTOL, calibrate, forward_profile
from app.validation import (
    check_H,
    check_measurement,
    check_position,
    check_sample_points,
)


# ----------------------------------------------------------------------
# 1. 等高跨中弧垂对上闭式
# ----------------------------------------------------------------------
@pytest.mark.parametrize("c", [10.0, 40.0, 100.0, 250.0])
def test_level_mid_sag_matches_closed_form(c):
    L = 100.0
    cat = Catenary(span=L, height_difference=0.0, c=c)
    closed = c * (math.cosh(L / (2.0 * c)) - 1.0)
    assert cat.sag(L / 2.0) == pytest.approx(closed, rel=1e-14)
    # 端点弧垂为零
    assert cat.sag(0.0) == pytest.approx(0.0, abs=1e-12)
    assert cat.sag(L) == pytest.approx(0.0, abs=1e-12)
    # 边界条件：索形两端对准支座
    assert cat.y(0.0) == pytest.approx(0.0, abs=1e-12)
    assert cat.y(L) == pytest.approx(0.0, abs=1e-12)


def test_level_vertex_at_midspan():
    cat = Catenary(100.0, 0.0, 40.0)
    assert cat.vertex_x() == pytest.approx(50.0, abs=1e-12)


def test_level_calibration_result_is_json_safe():
    import json

    out = calibrate(span=100.0, height_difference=0.0, w=9.81, sag=12.0, x=50.0)
    # 等高档 c_max=+inf 必须被归一成 None，最小可实现弧垂为 0
    assert out["c_max_reachable"] is None
    assert out["minimum_measurable_sag"] == 0.0
    parsed = json.loads(json.dumps(out))  # 不含 NaN/Infinity
    assert parsed["closure"]["passed"] is True


# ----------------------------------------------------------------------
# 2. 正算再反演 H 闭合（多个几何 / 测点，含不等高）
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "L,h,x,c0",
    [
        (100.0, 0.0, 50.0, 40.0),
        (100.0, 10.0, 50.0, 60.0),
        (200.0, 15.0, 130.0, 120.0),
        (50.0, -8.0, 20.0, 30.0),
        (300.0, 40.0, 160.0, 500.0),
    ],
)
def test_forward_invert_closure(L, h, x, c0):
    w = 9.81
    H0 = w * c0
    cat = Catenary(L, h, c0)
    f = cat.sag(x)  # 由已知 H 正算测点弧垂
    res = invert_sag(span=L, height_difference=h, w=w, x=x, sag=f)
    assert res.H == pytest.approx(H0, rel=1e-10)
    assert res.computed_sag == pytest.approx(f, rel=1e-10)


def test_service_closure_field_passes_tight_tolerance():
    # 先正算得到弧垂，再把它当测量值送回去标定（同一套几何）
    w = 12.0
    fwd = forward_profile(H=600.0, w=w, span=180.0, height_difference=12.0)
    x = 90.0
    sag = Catenary(180.0, 12.0, 600.0 / w).sag(x)
    cal = calibrate(span=180.0, height_difference=12.0, w=w, sag=sag, x=x)
    assert cal["closure"]["passed"] is True
    assert cal["closure"]["rel_error"] <= CLOSURE_RTOL
    assert cal["closure"]["rel_error"] < 1e-12
    assert cal["H"] == pytest.approx(600.0, rel=1e-10)
    # 正算与标定给出的索长、最低点一致
    assert cal["length"] == pytest.approx(fwd["length"], rel=1e-10)
    assert cal["vertex_x"] == pytest.approx(fwd["vertex_x"], rel=1e-10)


# ----------------------------------------------------------------------
# 3. 高差加大则最低点偏向低端
# ----------------------------------------------------------------------
def test_vertex_shifts_to_lower_end():
    L = 100.0
    x0 = Catenary(L, 0.0, 60.0).vertex_x()
    x_hi_right = Catenary(L, 30.0, 60.0).vertex_x()  # 右端高 -> 低点偏左
    x_hi_left = Catenary(L, -30.0, 60.0).vertex_x()  # 左端高 -> 低点偏右
    assert x0 == pytest.approx(50.0)
    assert x_hi_right < 50.0
    assert x_hi_left > 50.0
    assert x_hi_right == pytest.approx(L - x_hi_left, abs=1e-9)  # 镜像对称


def test_vertex_shift_monotonic_with_height_difference():
    L, c = 100.0, 60.0
    xs = [Catenary(L, h, c).vertex_x() for h in (0.0, 5.0, 10.0, 20.0, 28.0)]
    assert all(xs[i] > xs[i + 1] for i in range(len(xs) - 1))


# ----------------------------------------------------------------------
# 4. 大垂度：抛物近似系统偏短
# ----------------------------------------------------------------------
def test_parabolic_underestimates_large_sag():
    L, c = 100.0, 20.0
    cat = Catenary(L, 0.0, c)
    catenary_sag = cat.sag(L / 2.0)
    parabolic_sag = L * L / (8.0 * c)  # w L^2 /(8H) = L^2/(8c)
    assert catenary_sag == pytest.approx(102.6458, abs=1e-3)
    assert parabolic_sag < catenary_sag
    assert (catenary_sag - parabolic_sag) / catenary_sag > 0.30  # 短 30% 以上


def test_small_sag_is_only_a_limit_not_the_formula():
    # 小垂度时悬链与抛物接近（抛物是极限），但即便如此两者也不相等
    L, c = 100.0, 2000.0
    cat = Catenary(L, 0.0, c)
    catenary_sag = cat.sag(L / 2.0)
    parabolic_sag = L * L / (8.0 * c)
    assert catenary_sag > parabolic_sag  # 悬链恒略大
    assert catenary_sag == pytest.approx(parabolic_sag, rel=1e-4)  # 但很接近


# ----------------------------------------------------------------------
# 5 / 6. H 非正、档距非正、w 非正被拒
# ----------------------------------------------------------------------
def test_nonpositive_H_rejected():
    for bad in (0.0, -100.0):
        with pytest.raises(ValidationError):
            check_H(bad)
    with pytest.raises(ValidationError):
        forward_profile(H=-1.0, w=9.81, span=100.0, height_difference=0.0)
    with pytest.raises(ValidationError):
        forward_profile(H=0.0, w=9.81, span=100.0, height_difference=0.0)


@pytest.mark.parametrize("bad_span", [0.0, -50.0])
def test_nonpositive_span_rejected(bad_span):
    with pytest.raises(ValidationError):
        calibrate(span=bad_span, height_difference=0.0, w=9.81, sag=3.0, x=1.0)
    with pytest.raises(ValidationError):
        forward_profile(H=500.0, w=9.81, span=bad_span, height_difference=0.0)


def test_nonpositive_w_rejected():
    with pytest.raises(ValidationError):
        calibrate(span=100.0, height_difference=0.0, w=0.0, sag=3.0, x=50.0)
    with pytest.raises(ValidationError):
        calibrate(span=100.0, height_difference=0.0, w=-2.0, sag=3.0, x=50.0)


def test_nonfinite_and_wrong_type_rejected():
    with pytest.raises(ValidationError):
        forward_profile(H=float("nan"), w=9.81, span=100.0, height_difference=0.0)
    with pytest.raises(ValidationError):
        calibrate(span="100", height_difference=0.0, w=9.81, sag=3.0, x=50.0)


# ----------------------------------------------------------------------
# 7. 弧垂与高差矛盾：支座处给正弧垂 -> 失败，绝不硬画
# ----------------------------------------------------------------------
@pytest.mark.parametrize("x_endpoint,h", [(0.0, 0.0), (100.0, 0.0),
                                          (0.0, 30.0), (100.0, 30.0)])
def test_contradiction_at_support_fails(x_endpoint, h):
    with pytest.raises(ContradictionError):
        check_measurement(sag=5.0, x=x_endpoint, span=100.0, height_difference=h)
    with pytest.raises(ContradictionError):
        calibrate(span=100.0, height_difference=h, w=9.81, sag=5.0, x=x_endpoint)


def test_nonpositive_sag_rejected():
    with pytest.raises(ValidationError):
        calibrate(span=100.0, height_difference=0.0, w=9.81, sag=0.0, x=50.0)
    with pytest.raises(ValidationError):
        calibrate(span=100.0, height_difference=0.0, w=9.81, sag=-1.0, x=50.0)


# ----------------------------------------------------------------------
# 够不着：高差把可达弧垂下限抬高，测量过小 -> Unreachable，而不是编 H
# ----------------------------------------------------------------------
def test_unreachable_when_sag_below_height_difference_limit():
    L, h, w = 100.0, 30.0, 9.81
    c_max = reachable_c(L, h)
    f_min = Catenary(L, h, c_max).sag(L / 2.0)
    # 边界上最低点恰在低端支座
    assert Catenary(L, h, c_max).vertex_x() == pytest.approx(0.0, abs=1e-6)
    with pytest.raises(UnreachableError):
        invert_sag(span=L, height_difference=h, w=w, x=L / 2.0,
                   sag=f_min * 0.5)
    # 恰好在边界之上一点是可行的
    res = invert_sag(span=L, height_difference=h, w=w, x=L / 2.0,
                     sag=f_min * 1.05)
    assert res.c <= c_max
    assert 0.0 <= res.catenary.vertex_x() <= L


def test_forward_rejects_unreachable_tight_cable():
    # 高差 30，c 必须 <= c_max≈171；给个很大 c（极紧）直接拒
    with pytest.raises(UnreachableError):
        forward_profile(H=1e6, w=9.81, span=100.0, height_difference=30.0)


# ----------------------------------------------------------------------
# 索长 = c(sinh(p+a)-sinh(p-a))，且大于档距
# ----------------------------------------------------------------------
@pytest.mark.parametrize("h", [0.0, 10.0, -22.0])
def test_length_formula_and_positive_excess(h):
    L, c = 120.0, 45.0
    cat = Catenary(L, h, c)
    A = L / (2.0 * c)
    p = math.asinh(h / (2.0 * c * math.sinh(A)))
    direct = c * (math.sinh(p + A) - math.sinh(p - A))
    assert cat.length() == pytest.approx(direct, rel=1e-13)
    assert cat.length() > L


# ----------------------------------------------------------------------
# 取样越界拒绝
# ----------------------------------------------------------------------
def test_sample_point_outside_span_rejected():
    with pytest.raises(ValidationError):
        check_position(-0.01, 100.0)
    with pytest.raises(ValidationError):
        check_position(100.01, 100.0)
    with pytest.raises(ValidationError):
        forward_profile(H=500.0, w=9.81, span=100.0, height_difference=0.0,
                        points=[10.0, 110.0])
    with pytest.raises(ValidationError):
        check_sample_points([], 100.0)


# ----------------------------------------------------------------------
# 正算剖面：端点高度与曲线自洽
# ----------------------------------------------------------------------
def test_profile_endpoint_heights():
    res = forward_profile(H=500.0, w=10.0, span=100.0, height_difference=25.0,
                          points=[0.0, 25.0, 50.0, 75.0, 100.0])
    ys = {round(p["x"], 6): p["y"] for p in res["points"]}
    assert ys[0.0] == pytest.approx(0.0, abs=1e-10)
    assert ys[100.0] == pytest.approx(25.0, abs=1e-10)
    assert res["vertex_inside"] is True
