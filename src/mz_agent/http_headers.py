"""MzAgent 默认 HTTP 请求头。"""

from __future__ import annotations

DEFAULT_USER_AGENT = "MzAgent/0.1.26 (+https://github.com/sigerio/MzAgentSub)"


def build_default_http_headers(
    extra_headers: dict[str, str] | None = None,
) -> dict[str, str]:
    headers = dict(extra_headers or {})
    if any(key.lower() == "user-agent" for key in headers):
        return headers
    return {
        "User-Agent": DEFAULT_USER_AGENT,
        **headers,
    }
