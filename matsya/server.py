"""
Live server — stdlib http.server par (koi FastAPI/Docker/Node nahi).

  python matsya.py serve --port 8000
  browser: http://localhost:8000

Endpoint:
  GET  /                tactical dashboard
  POST /api/ask         {query, persona} -> agent DAG chalta hai, JSON trace ke saath
  GET  /api/state       current grids ka summary
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import config as C
from .agents.state import AgentState

_ctx = {"state": None, "html": "", "cfg": None, "lock": threading.Lock()}


def set_context(state, html, cfg):
    _ctx["state"], _ctx["html"], _ctx["cfg"] = state, html, cfg


def _ask(payload, cfg, state):
    """Naya query -> nayi (copy) state par agent DAG chalao."""
    from .orchestrator import Orchestrator

    st = AgentState(user_query=payload.get("query", ""),
                    persona=payload.get("persona", "fisher"))
    st.grids = state.grids
    st.meta = dict(state.meta)
    st.meta["use_llm"] = payload.get("llm", False)
    st.origin = payload.get("origin") or state.origin
    st.target = payload.get("target") or state.target
    st.trace.log("user", "query", payload.get("query", ""))
    Orchestrator(cfg, audit_dir=C.OUT / "audit").run(st)

    fin = st.final or {}
    return {
        "run_id": st.trace.run_id,
        "query": st.user_query,
        "intent": st.intent,
        "origin": st.origin, "target": st.target,
        "verdict": fin.get("verdict"), "headline": fin.get("headline"),
        "color": fin.get("color"), "score": fin.get("score"),
        "risk": fin.get("risk"), "bullets": fin.get("bullets", []),
        "text": fin.get("text", ""), "confidence": fin.get("confidence"),
        "route": st.meta.get("route"),
        "rules": fin.get("rules", []),
        "results": {k: {"status": v.get("status"), "confidence": v.get("confidence"),
                        "latency_ms": v.get("latency_ms"), "text": v.get("text"),
                        "evidence": v.get("evidence", [])}
                    for k, v in st.results.items()},
        "trace": {"steps": st.trace.steps, "messages": st.trace.messages,
                  "total_ms": st.trace.total_ms},
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = urlparse(self.path).path
        if p in ("/", "/index.html", "/tactical.html"):
            self._send(200, _ctx["html"].encode("utf-8"))
        elif p == "/api/state":
            st = _ctx["state"]
            body = json.dumps({
                "meta": {k: v for k, v in (st.meta or {}).items() if k != "cfg"},
                "spots": (st.meta or {}).get("spots", [])[:12],
                "final": st.final,
                "trace": {"steps": st.trace.steps, "total_ms": st.trace.total_ms},
            }, ensure_ascii=False).encode()
            self._send(200, body, "application/json")
        elif p == "/api/health":
            self._send(200, b'{"ok":true}', "application/json")
        else:
            self._send(404, b"not found")

    def do_POST(self):
        if urlparse(self.path).path != "/api/ask":
            self._send(404, b"not found")
            return
        n = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            payload = {}
        try:
            out = _ask(payload, _ctx["cfg"], _ctx["state"])
            self._send(200, json.dumps(out, ensure_ascii=False).encode(), "application/json")
        except Exception as e:
            self._send(500, json.dumps({"error": f"{type(e).__name__}: {e}"}).encode(),
                       "application/json")


def serve(port=8000, state=None, html="", cfg=None):
    set_context(state, html, cfg)
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"\n  MATSYA live server: http://localhost:{port}")
    print("  Band karne ke liye Ctrl+C\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
