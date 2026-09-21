"""由实测弧垂反演形状参数 c 与水平张力 H。

f(c) = catenary.sag(x_m) 对 c 严格单调递减（c 越大索越紧、垂度越小，
c -> inf 时 f -> 0，c -> 0 时 f -> inf），所以任意正的、档内测点的弧垂
在纯几何上对应唯一的 c。用几何（对数）二分求根，避免对等高档闭式的
依赖——同一套双曲关系同时覆盖等高与不等高。

求到根之后再过**可达性**这道物理闸：最低点必须位于两支座之间，
即 c <= c_max(L, h)。测点在档内时，可达边界对应一个最小可实现弧垂
f_min；实测弧垂小于 f_min，意味着为了够到这么小的垂度，最低点被
推到了较低支座之外——柔索在该高差下「够不着」两个支座，标定失败。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .catenary import Catenary, reachable_c
from .errors import UnreachableError

# 求根相对收敛容差（远严于对外承诺的闭合容差 1e-6）
_ROOT_RTOL = 1e-13
_MAX_ITERS = 300


@dataclass(frozen=True)
class InversionResult:
    c: float
    H: float
    catenary: Catenary
    computed_sag: float
    c_max: float
    min_sag: float


def _solve_c(span: float, height_difference: float, x: float, sag: float) -> float:
    """在 (0, inf) 上对 sag(c) = sag 求根（几何二分）。

    利用单调性：先把 bracket 撑到 f(hi) < sag < f(lo)，再二分。
    """
    hi = max(1.0, span)  # 从档距量级起步
    cat_hi = Catenary(span, height_difference, hi)
    while cat_hi.sag(x) > sag:
        hi *= 2.0
        cat_hi = Catenary(span, height_difference, hi)
        if hi > 1e18:  # pragma: no cover - 防御性
            break
    lo = hi / 2.0
    cat_lo = Catenary(span, height_difference, lo)
    while cat_lo.sag(x) < sag:
        lo /= 2.0
        cat_lo = Catenary(span, height_difference, lo)

    for _ in range(_MAX_ITERS):
        mid = (lo * hi) ** 0.5
        f_mid = Catenary(span, height_difference, mid).sag(x)
        if f_mid > sag:
            lo = mid  # 垂度偏大 -> c 偏小
        else:
            hi = mid
        if (hi - lo) <= _ROOT_RTOL * hi:
            break
    return (lo * hi) ** 0.5


def invert_sag(
    *,
    span: float,
    height_difference: float,
    w: float,
    x: float,
    sag: float,
) -> InversionResult:
    """由测点 (x 处的实测弧垂 sag) 反演 c、H，并做可达性判定。

    入参合法性（正数、档内等）由 validation 层先行保证。
    """
    c = _solve_c(span, height_difference, x, sag)
    cat = Catenary(span, height_difference, c)
    c_max = reachable_c(span, height_difference)

    if c > c_max * (1.0 + 1e-9):
        # 根越过可达边界：最低点已在较低支座之外。
        min_sag = Catenary(span, height_difference, c_max).sag(x)
        low_end = "左" if height_difference > 0 else "右"
        raise UnreachableError(
            "该测量弧垂与两端高差无法同时满足：反演得到的最低点已越出较低"
            f"支座（{low_end}端）落到档外，柔索在该高差下够不着两个支座。"
            f"该测点在当前高差下最小可实现弧垂约为 {min_sag:.6g}，"
            f"实测仅 {sag:.6g}。",
            details={
                "c": c,
                "c_max": c_max,
                "minimum_measurable_sag": min_sag,
                "measured_sag": sag,
                "x": x,
                "height_difference": height_difference,
            },
        )

    # 等高时任意正 c 可达，测点处最小可实现弧垂为 0
    min_sag = (
        0.0
        if math.isinf(c_max)
        else Catenary(span, height_difference, c_max).sag(x)
    )

    return InversionResult(
        c=c,
        H=w * c,
        catenary=cat,
        computed_sag=cat.sag(x),
        c_max=c_max,
        min_sag=min_sag,
    )
