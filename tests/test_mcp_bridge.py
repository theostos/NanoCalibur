import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from nanocalibur.mcp_bridge import NanoCaliburHTTPClient, build_fastmcp_from_http


class _FakeEngineHandler(BaseHTTPRequestHandler):
    count = 0

    def do_GET(self):  # noqa: N802
        if self.path == "/tools":
            self._send_json(
                {
                    "tools": [
                        {
                            "name": "nudge",
                            "tool_docstring": "Move hero right",
                            "action": "nudge",
                        }
                    ]
                }
            )
            return
        if self.path == "/state":
            self._send_json({"state": {"globals": {"count": self.__class__.count}}})
            return
        if self.path == "/frame":
            self._send_json({"frame": {"rows": [".@.."]}})
            return
        self._send_json({"error": "not found"}, status=404)

    def do_POST(self):  # noqa: N802
        if self.path in {"/tools/call", "/step"}:
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            payload = json.loads(raw.decode("utf-8") or "{}") if raw else {}
            if self.path == "/tools/call":
                if payload.get("name") == "nudge":
                    self.__class__.count += 1
            if self.path == "/step":
                calls = payload.get("toolCalls") or []
                for call in calls:
                    if call == "nudge":
                        self.__class__.count += 1
                    elif isinstance(call, dict) and call.get("name") == "nudge":
                        self.__class__.count += 1
            self._send_json({"state": {"globals": {"count": self.__class__.count}}})
            return
        self._send_json({"error": "not found"}, status=404)

    def log_message(self, format, *args):  # noqa: A003
        return

    def _send_json(self, payload, status=200):
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def _start_server():
    _FakeEngineHandler.count = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeEngineHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


class _FakeFastMCP:
    def __init__(self, name: str):
        self.name = name
        self.tools = {}

    def tool(self, *, name=None, description=""):
        def _decorate(fn):
            self.tools[name or fn.__name__] = {
                "fn": fn,
                "description": description,
            }
            return fn

        return _decorate


def test_http_client_wraps_headless_http_endpoints():
    server, thread = _start_server()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        client = NanoCaliburHTTPClient(base_url)
        tools = client.list_tools()
        assert tools[0]["name"] == "nudge"

        result = client.call_tool("nudge", {})
        assert result["state"]["globals"]["count"] == 1

        stepped = client.step({"toolCalls": ["nudge"]})
        assert stepped["state"]["globals"]["count"] == 2

        state = client.get_state()
        assert state["state"]["globals"]["count"] == 2
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_build_fastmcp_from_http_registers_proxy_tools():
    server, thread = _start_server()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        mcp = build_fastmcp_from_http(base_url, mcp_cls=_FakeFastMCP)
        assert "nudge" in mcp.tools
        assert mcp.tools["nudge"]["description"] == "Move hero right"

        result = mcp.tools["nudge"]["fn"]()
        assert result["state"]["globals"]["count"] == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
