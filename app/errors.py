"""统一的领域错误类型。

所有错误都携带稳定的英文 ``error`` 码（供调用方程序判断）与中文说明
（直接面向现场），并映射到合适的 HTTP 状态码。
"""

from __future__ import annotations


class CalibrationError(Exception):
    """标定 / 正算领域错误基类。"""

    status_code: int = 400
    error_code: str = "bad_request"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValidationError(CalibrationError):
    """入参在进入几何计算前就不合法（非正、非数值、越界等）。"""

    status_code = 400
    error_code = "invalid_parameter"


class UnreachableError(CalibrationError):
    """给定弧垂太小：反演出的 c 已越过可达边界，最低点落到档外。

    即按该测量结果，柔索在「最低点位于两支座之间」的前提下够不着两个
    支座——这是高差与张力的几何冲突，而不是弧垂数值自相矛盾。
    """

    status_code = 422
    error_code = "span_unreachable"


class ContradictionError(CalibrationError):
    """弧垂与高差 / 测点位置互相矛盾。

    典型情形：测点在支座处（弧垂按定义必须为 0），却给出了正的实测
    弧垂。此时不存在任何能同时满足两端边界和该测量的 c。
    """

    status_code = 422
    error_code = "sag_contradiction"


class SpanNotFoundError(CalibrationError):
    """点名的具名几何档不存在。"""

    status_code = 404
    error_code = "span_not_found"


class SpanExistsError(CalibrationError):
    """登记具名档时名字已被占用。"""

    status_code = 409
    error_code = "span_exists"
