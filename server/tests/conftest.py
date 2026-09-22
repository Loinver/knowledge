"""pytest 公共夹具。

后端所有 JSON 接口都包裹 `{ code, message, data }` 外壳，
实现见 `app/schemas/response.py`。测试断言聚焦业务数据，
因此这里给 `httpx.Response.json` 加一个**仅测试环境生效**的解包垫片：

- 成功响应（`code == "KG.OK"`）→ 直接返回 `data`，断言写法与改造前一致；
- 失败响应 → 原样返回完整外壳，便于断言 `code` / `params` / `data is None`。

需要校验外壳本身时用 `envelope(response)`，它绕过解包垫片。
"""

from __future__ import annotations

from typing import Any

import httpx

OK_CODE = "KG.OK"
_original_json = httpx.Response.json


def _json_unwrapped(self: httpx.Response, *args: Any, **kwargs: Any) -> Any:
    body = _original_json(self, *args, **kwargs)
    if isinstance(body, dict) and body.get("code") == OK_CODE and "data" in body:
        return body["data"]
    return body


httpx.Response.json = _json_unwrapped  # type: ignore[method-assign]


def envelope(response: httpx.Response) -> dict[str, Any]:
    """取未经解包的完整外壳，用于断言 code / message / data 结构。"""
    return _original_json(response)
