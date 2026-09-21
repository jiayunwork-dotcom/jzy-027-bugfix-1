"""具名几何档的本地文件读写。

只持久化跨距几何（档距、高差、w、名字），标定当次完成、不另建
流水库。所有档存放在一个 JSON 文件里：
    { "档名": {"span": .., "height_difference": .., "w": ..}, ... }

写入用「临时文件 + os.replace」原子替换，避免并发读到半截文件。
"""

from __future__ import annotations

import json
import os
import tempfile

from .errors import SpanExistsError, SpanNotFoundError
from .validation import check_geometry

_DEFAULT_PATH = os.environ.get("CATENARY_STORE", "data/spans.json")


class SpanStore:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or _DEFAULT_PATH

    # ---- 底层 --------------------------------------------------------
    def _load(self) -> dict:
        if not os.path.exists(self.path):
            return {}
        with open(self.path, "r", encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"几何档文件损坏: {self.path}") from exc
        if not isinstance(data, dict):
            raise RuntimeError(f"几何档文件格式错误: {self.path}")
        return data

    def _write(self, data: dict) -> None:
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".spans-", suffix=".json", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
            os.replace(tmp, self.path)
        except BaseException:
            os.unlink(tmp)
            raise

    # ---- 对外 --------------------------------------------------------
    def create(self, name: str, *, span: float, height_difference: float, w: float,
               overwrite: bool = False) -> dict:
        if not isinstance(name, str) or not name.strip():
            from .errors import ValidationError

            raise ValidationError("档名 name 必须是非空字符串")
        name = name.strip()
        check_geometry(span=span, height_difference=height_difference, w=w)

        data = self._load()
        if name in data and not overwrite:
            raise SpanExistsError(f"档名 {name!r} 已存在")
        record = {
            "name": name,
            "span": float(span),
            "height_difference": abs(float(height_difference)),
            "w": float(w),
        }
        data[name] = {k: record[k] for k in ("span", "height_difference", "w")}
        self._write(data)
        return record

    def get(self, name: str) -> dict:
        data = self._load()
        if name not in data:
            known = ", ".join(sorted(data)) or "（空）"
            raise SpanNotFoundError(f"档名 {name!r} 不存在；已登记档: {known}")
        rec = data[name]
        return {
            "name": name,
            "span": rec["span"],
            "height_difference": rec["height_difference"],
            "w": rec["w"],
        }

    def list(self) -> list[dict]:
        data = self._load()
        return [
            {
                "name": name,
                "span": rec["span"],
                "height_difference": rec["height_difference"],
                "w": rec["w"],
            }
            for name, rec in sorted(data.items())
        ]
