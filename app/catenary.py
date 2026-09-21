"""柔索悬链双曲几何——正算核心。

约定（单位自洽，例如 m、N、N/m）：
    左支座 A 取在原点 (0, 0)，右支座 B 在 (L, h)。
        L : 档距（水平跨度），> 0
        h : 两端高差 y_B - y_A，可正可负；h>0 表示右端更高
        w : 单位长度重量，> 0
        H : 水平张力，> 0
        c = H / w : 悬链形状参数（长度量纲）

倒悬链（重力下向下垂）取对中形式，令 a = L/(2c)：
    p = asinh( h / (2 c sinh a) )                     （倾斜参数）
    y(x) = c [ cosh((x - L/2)/c + p) - cosh(p - a) ]
自动满足 y(0)=0、y(L)=h；最低点位于 x_v = L/2 - c p。
等高时 p=0，最低点落在跨中。

弧垂（测量垂度）按架线定义取为弦线相对索形的竖直距离：
    f(x) = 弦线高度 h x / L - y(x)
等高时跨中 f = c(cosh a - 1)。

索长：
    S = c [sinh(p+a) - sinh(p-a)] = 2 c cosh p sinh a
即「c 乘两端无因次水平坐标的双曲正弦之差」。

本模块是正算与反演共用的唯一一套双曲关系；inversion 也调用这里的
:func:`sag`，保证二者不可能各写一套。
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Catenary:
    """一根由几何 (L, h) 与形状参数 c 完全确定的悬链。"""

    span: float
    height_difference: float
    c: float

    # ---- 基本双曲量 -------------------------------------------------
    def _params(self) -> tuple[float, float]:
        """返回 (p, a)；对极端小 c 做溢出保护。"""
        L, h, c = self.span, self.height_difference, self.c
        a = L / (2.0 * c)
        try:
            p = math.asinh(h / (2.0 * c * math.sinh(a)))
        except OverflowError:
            # sinh(a) 溢出而 h 有限时，参数 -> 0，故 p -> 0
            p = 0.0
        return p, a

    def y(self, x: float) -> float:
        """索形高度，y(0)=0、y(L)=h。

        用恒等式 cosh M - cosh N = 2 sinh((M+N)/2) sinh((M-N)/2)
        求值，避免两个大数直接相减丢失精度。
        """
        p, a = self._params()
        m = (x - self.span / 2.0) / self.c + p
        n = p - a
        try:
            return 2.0 * self.c * math.sinh((m + n) / 2.0) * math.sinh((m - n) / 2.0)
        except OverflowError:
            return -math.inf

    def chord_y(self, x: float) -> float:
        """弦线（两支座连线）高度。"""
        return self.height_difference * x / self.span

    def sag(self, x: float) -> float:
        """x 处弧垂（竖直方向）= 弦线 - 索形。"""
        v = self.y(x)
        if v == -math.inf:
            return math.inf
        return self.chord_y(x) - v

    def vertex_x(self) -> float:
        """最低点的水平位置（相对左支座），允许落在档外。"""
        p, _ = self._params()
        return self.span / 2.0 - self.c * p

    def vertex_y(self) -> float:
        """最低点的高度（可能低于左支座零点）。"""
        return self.y(self.vertex_x())

    def length(self) -> float:
        """整档索长 S = 2 c cosh p sinh a。"""
        p, a = self._params()
        try:
            return 2.0 * self.c * math.cosh(p) * math.sinh(a)
        except OverflowError:
            return math.inf

    # ---- 可达性 -----------------------------------------------------
    def vertex_inside(self, tol: float = 1e-9) -> bool:
        """最低点是否落在两支座之间（含支座）。"""
        xv = self.vertex_x()
        return -tol * self.span <= xv <= (1.0 + tol) * self.span

    def reachable_c(self) -> float:
        """本几何 (L, h) 的可达上界 c_max。

        最低点恰在较低支座处为边界：令 v>=0 解
            (cosh v - 1)/v = |h|/L,   c_max = L / v
        等高时 |h|=0，任意 c 都可达，返回 +inf。
        """
        return reachable_c(self.span, self.height_difference)

    def is_reachable(self) -> bool:
        """c 是否未越过可达边界（最低点在档内）。"""
        cm = self.reachable_c()
        return self.c <= cm * (1.0 + 1e-9)


def reachable_c(span: float, height_difference: float) -> float:
    """几何 (L, h) 的形状参数可达上界 c_max。"""
    r = abs(height_difference) / span
    if r == 0.0:
        return math.inf
    lo, hi = 1e-14, 1.0
    while (math.cosh(hi) - 1.0) / hi < r:
        hi *= 2.0
        if hi > 1e6:  # pragma: no cover - 仅防御性
            break
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if (math.cosh(mid) - 1.0) / mid < r:
            lo = mid
        else:
            hi = mid
    v = 0.5 * (lo + hi)
    return span / v


def make_catenary(H: float, w: float, span: float, height_difference: float) -> Catenary:
    """由水平张力 H 与单位长度重量 w 构造悬链（c = H/w）。"""
    return Catenary(span=span, height_difference=height_difference, c=H / w)
