"""编排层：把双曲正算、弧垂反演、入参检查串成「标定 / 正算」两件事。

正算与反演都经由 :mod:`app.catenary` 的同一套双曲关系，因此
「H 正算出弧垂 -> 弧垂反演 H」天然闭合；标定结果里把这条闭合
误差显式算出来留档，作为验收主尺子的直接证据。
"""

from __future__ import annotations

import math

from .catenary import Catenary, reachable_c
from .errors import UnreachableError
from .inversion import invert_sag
from .validation import check_H, check_geometry, check_sample_points

# 对外承诺的正算-反演相对闭合容差
CLOSURE_RTOL = 1e-6

_PROFILE_N = 21  # 默认沿档距均匀取样点数


def _jsonable(value):
    """把 ±inf / nan 归一成 None（这些不是合法 JSON 标量）。"""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def _default_points(span: float) -> list[float]:
    return [span * i / (_PROFILE_N - 1) for i in range(_PROFILE_N)]


def _profile(cat: Catenary, points: list[float]) -> list[dict]:
    return [
        {
            "x": x,
            "y": cat.y(x),
            "chord_y": cat.chord_y(x),
            "sag": cat.sag(x),
        }
        for x in points
    ]


def _base(cat: Catenary, H: float, w: float) -> dict:
    xv = cat.vertex_x()
    return {
        "H": H,
        "w": w,
        "c": cat.c,
        "span": cat.span,
        "height_difference": cat.height_difference,
        "vertex_x": xv,
        "vertex_y": cat.vertex_y(),
        "vertex_inside": cat.vertex_inside(),
        "length": cat.length(),
        "c_max_reachable": cat.reachable_c(),
    }


def forward_profile(
    *, H: float, w: float, span: float, height_difference: float,
    points: list[float] | None = None,
) -> dict:
    """给定 H 顺张力铺整条曲线，并在取样点处给出高度 / 弧垂。"""
    check_H(H)
    check_geometry(span=span, height_difference=height_difference, w=w)
    pts = (
        check_sample_points(points, span)
        if points is not None
        else _default_points(span)
    )

    cat = Catenary(span, height_difference, H / w)
    if not cat.is_reachable():
        c_max = reachable_c(span, height_difference)
        raise UnreachableError(
            "给定张力下最低点已越出较低支座落到档外，该档在此高差下"
            f"够不着两个支座；需 c=H/w <= {c_max:.6g}（当前 c={cat.c:.6g}）。",
            details={"c": cat.c, "c_max": c_max},
        )

    return _jsonable({
        **_base(cat, H, w),
        "points": _profile(cat, pts),
    })


def calibrate(
    *, span: float, height_difference: float, w: float,
    sag: float, x: float, points: list[float] | None = None,
) -> dict:
    """量弧垂反演 H，再按该 H 铺出整档曲线，并做闭合校验。

    测量值的合法性（弧垂正、测点在档内、支座矛盾等）在 invert 前由
    validation 完成；可达性（够不着）由 inversion 判定。
    """
    check_geometry(span=span, height_difference=height_difference, w=w)
    # 延迟导入以避免模块初始化期的循环引用（validation 不依赖 service）
    from .validation import check_measurement

    sag, x = check_measurement(
        sag=sag, x=x, span=span, height_difference=height_difference
    )

    result = invert_sag(
        span=span, height_difference=height_difference, w=w, x=x, sag=sag
    )
    cat = result.catenary

    # ---- 正算再反演闭合：用解出的 H 在同测点正算弧垂，再反演 H ----
    forward_sag = cat.sag(x)
    re = invert_sag(
        span=span, height_difference=height_difference, w=w,
        x=x, sag=forward_sag,
    )
    H_return = re.H
    closure_abs = abs(H_return - result.H)
    closure_rel = closure_abs / result.H if result.H else float("inf")

    pts = (
        check_sample_points(points, span)
        if points is not None
        else _default_points(span)
    )

    return _jsonable({
        **_base(cat, result.H, w),
        "measurement": {"x": x, "measured_sag": sag},
        "computed_sag": result.computed_sag,
        "sag_residual": forward_sag - sag,
        "c_max_reachable": result.c_max,
        "minimum_measurable_sag": result.min_sag,
        "closure": {
            "H_solved": result.H,
            "H_returned": H_return,
            "abs_error": closure_abs,
            "rel_error": closure_rel,
            "rtol": CLOSURE_RTOL,
            "passed": closure_rel <= CLOSURE_RTOL,
        },
        "points": _profile(cat, pts),
    })
