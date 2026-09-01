"""Base class: har agent ka timing, status, confidence aur evidence yahin se aata hai."""

import time
from abc import ABC, abstractmethod


class Agent(ABC):
    name = "agent"
    role = ""
    uses_llm = False

    @abstractmethod
    def run(self, state) -> dict:
        ...

    def __call__(self, state):
        t0 = time.perf_counter()
        state.trace.log(self.name, "start", f"{self.role} shuru")
        try:
            out = self.run(state)
            out.setdefault("status", "OK")
        except Exception as e:
            out = {"status": "ERROR", "error": f"{type(e).__name__}: {e}",
                   "confidence": 0.0, "findings": {}, "evidence": [],
                   "text": f"{self.name} fail ho gaya: {e}"}
            state.trace.log(self.name, "error", str(e))
        ms = (time.perf_counter() - t0) * 1000
        out["latency_ms"] = round(ms, 1)
        out["agent"] = self.name
        out["uses_llm"] = self.uses_llm
        state.trace.step(self.name, ms, out["status"], out.get("confidence"))
        state.trace.log(self.name, "end",
                        out.get("text", "")[:180] or f"{self.name} done",
                        ms=round(ms, 1), confidence=out.get("confidence"))
        state.set(self.name, out)
        return out

    # helper: evidence chip
    @staticmethod
    def ev(kind, label, value, source=""):
        return {"kind": kind, "label": label, "value": value, "source": source}
