"""入参检查：在进入任何几何计算之前把不合法的请求挡下来。

检查原则（对应需求）：
    * H、w、档距必须是正数，否则标定前直接停；
    * 高差必须是有限实数（有限高差总能搭出一条悬链，但还要过可达性
      这道几何闸，由 inversion 负责）；
    * 实测弧垂必须为正；
    * 测量位置 / 取样点必须落在 [0, L] 档内。
"""

from __future__ import annotations

import math

from .errors import ContradictionError, ValidationError

# 测点贴在多近视为「就在支座上」（相对档距）
_ENDPOINT_TOL = 1e-9


def _as_finite_number(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{name} 必须是数值")
    value = float(value)
    if not math.isfinite(value):
        raise ValidationError(f"{name} 必须是有限数值")
    return value


def require_positive(value, name: str) -> float:
    """要求严格为正的有限数值。"""
    value = _as_finite_number(value, name)
    if value <= 0.0:
        raise ValidationError(f"{name} 必须为正数，收到 {value:g}")
    return value


def require_real(value, name: str) -> float:
    """高差这类允许为 0 或负值的有限实数。"""
    return _as_finite_number(value, name)


def check_geometry(*, span: float, height_difference: float, w: float) -> None:
    """登记 / 提交一档几何时的检查。"""
    require_positive(span, "档距 span")
    require_real(height_difference, "高差 height_difference")
    require_positive(w, "单位长度重量 w")


def check_H(H: float) -> None:
    """正算入口的水平张力必须为正。"""
    require_positive(H, "水平张力 H")


def check_position(x: float, span: float, *, name: str = "取样点位置 x") -> float:
    """水平位置必须落在档内 [0, L]。"""
    x = _as_finite_number(x, name)
    if x < 0.0 or x > span:
        raise ValidationError(
            f"{name}={x:g} 越出档距范围 [0, {span:g}]",
            details={"x": x, "span": span},
        )
    return x


def check_measurement(
    *, sag: float, x: float, span: float, height_difference: float
) -> tuple[float, float]:
    """标定测量值检查：弧垂为正、测点在档内，并识别支座处的矛盾。

    返回 (sag, x)。测点若贴在支座上（相对容差 1e-9），弧垂按定义
    必须为 0；此时给出正弧垂属于「弧垂与高差 / 测点矛盾」，没有任何
    c 能同时满足，直接判失败而不是硬算一条曲线。
    """
    sag = require_positive(sag, "实测弧垂 sag")
    x = check_position(x, span, name="测量位置 x")

    at_endpoint = x <= _ENDPOINT_TOL * span or x >= (1.0 - _ENDPOINT_TOL) * span
    if at_endpoint:
        # 支座处弦线与索形重合，弧垂恒为 0，与高差大小无关。
        raise ContradictionError(
            "测量位置落在支座处，该处弧垂恒为 0，"
            f"与正的实测弧垂 {sag:g} 矛盾；不存在满足两端边界与该测量的张力",
            details={"x": x, "sag": sag, "height_difference": height_difference},
        )
    return sag, x


def check_sample_points(points, span: float) -> list[float]:
    """正算取样点列表：必须是列表，逐点在档内。"""
    if not isinstance(points, (list, tuple)):
        raise ValidationError("取样点 points 必须是数值列表")
    if len(points) == 0:
        raise ValidationError("取样点 points 不能为空")
    return [check_position(p, span) for p in points]
