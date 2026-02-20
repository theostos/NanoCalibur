"""HTTP and FastMCP bridge utilities for NanoCalibur headless servers."""

from __future__ import annotations

import json
import urllib.request
from typing import Any, Callable, Dict, Optional, Type


class NanoCaliburHTTPClient:
    """Simple JSON HTTP client for a NanoCalibur headless HTTP server."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def list_tools(self) -> list[Dict[str, Any]]:
        """List externally callable tools exposed by the runtime.

        Returns:
            Tool metadata dictionaries as returned by ``GET /tools``.
        """
        payload = self._request("GET", "/tools")
        tools = payload.get("tools")
        if not isinstance(tools, list):
            return []
        return [tool for tool in tools if isinstance(tool, dict)]

    def call_tool(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Invoke one tool call by name.

        Args:
            name: Registered tool name.
            arguments: Optional JSON-serializable tool arguments.

        Returns:
            Decoded JSON response payload.

        Raises:
            ValueError: If ``name`` is empty.
            URLError: If the HTTP request fails.
        """
        if not isinstance(name, str) or not name:
            raise ValueError("Tool name must be a non-empty string.")
        payload = {
            "name": name,
            "arguments": arguments or {},
        }
        return self._request("POST", "/tools/call", payload)

    def get_state(self) -> Dict[str, Any]:
        """Fetch authoritative runtime state from ``GET /state``."""
        return self._request("GET", "/state")

    def get_frame(self) -> Dict[str, Any]:
        """Fetch symbolic frame payload from ``GET /frame``."""
        return self._request("GET", "/frame")

    def step(self, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Advance one headless simulation step.

        Args:
            payload: Optional input payload accepted by ``POST /step``.

        Returns:
            Decoded JSON response payload.
        """
        return self._request("POST", "/step", payload or {})

    def _request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = {"Accept": "application/json"}
        body: Optional[bytes] = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(url, data=body, method=method, headers=headers)
        with urllib.request.urlopen(request, timeout=10) as response:
            decoded = response.read().decode("utf-8")

        if not decoded.strip():
            return {}
        parsed = json.loads(decoded)
        if not isinstance(parsed, dict):
            raise RuntimeError(f"Expected JSON object from {url}")
        return parsed


def build_fastmcp_from_http(
    base_url: str,
    *,
    server_name: str = "NanoCalibur",
    mcp_cls: Optional[Type[Any]] = None,
) -> Any:
    """Create a FastMCP server proxying tools from a NanoCalibur HTTP server.

    Parameters
    ----------
    base_url:
        Base URL of the running NanoCalibur headless HTTP server.
    server_name:
        Name passed to FastMCP constructor.
    mcp_cls:
        Optional FastMCP-compatible class override (useful for tests).

    Returns:
        Configured MCP server instance.

    Raises:
        RuntimeError: If ``fastmcp`` is unavailable or registration API is unsupported.

    Example:
        >>> mcp = build_fastmcp_from_http("http://127.0.0.1:7070")
    """

    if mcp_cls is None:
        try:
            from fastmcp import FastMCP  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on optional dependency
            raise RuntimeError(
                "fastmcp is not installed. Install it or pass mcp_cls explicitly."
            ) from exc
        mcp_cls = FastMCP

    client = NanoCaliburHTTPClient(base_url)
    mcp = mcp_cls(server_name)

    for tool in client.list_tools():
        tool_name = tool.get("name")
        if not isinstance(tool_name, str) or not tool_name:
            continue
        tool_description = tool.get("tool_docstring")
        if not isinstance(tool_description, str):
            tool_description = ""

        proxy_fn = _make_tool_proxy(client, tool_name, tool_description)

        if hasattr(mcp, "tool"):
            decorator = _get_tool_decorator(
                mcp,
                tool_name=tool_name,
                tool_description=tool_description,
            )
            decorator(proxy_fn)
            continue

        if hasattr(mcp, "add_tool"):
            mcp.add_tool(proxy_fn, name=tool_name, description=tool_description)
            continue

        raise RuntimeError(
            "Provided MCP class does not expose a supported registration API "
            "(expected .tool(...) or .add_tool(...))."
        )

    return mcp


def _make_tool_proxy(
    client: NanoCaliburHTTPClient,
    tool_name: str,
    tool_description: str,
) -> Callable[..., Dict[str, Any]]:
    def _tool_proxy(**kwargs: Any) -> Dict[str, Any]:
        return client.call_tool(tool_name, dict(kwargs))

    _tool_proxy.__name__ = _sanitize_identifier(f"tool_{tool_name}")
    _tool_proxy.__doc__ = tool_description or f"Proxy tool '{tool_name}'"
    return _tool_proxy


def _get_tool_decorator(mcp: Any, *, tool_name: str, tool_description: str):
    try:
        return mcp.tool(name=tool_name, description=tool_description)
    except TypeError:
        return mcp.tool()


def _sanitize_identifier(value: str) -> str:
    out = []
    for ch in value:
        if ch.isalnum() or ch == "_":
            out.append(ch)
        else:
            out.append("_")
    normalized = "".join(out)
    if not normalized:
        return "tool_proxy"
    if normalized[0].isdigit():
        return f"tool_{normalized}"
    return normalized
