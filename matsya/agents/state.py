"""
AgentState — sab agents ke beech shared state (LangGraph jaisa, par zero dependency).

Har agent apna result `state.results[agent_name]` me daalta hai:
  {status, confidence, latency_ms, findings:{}, evidence:[], text:""}
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

PERSONAS = {
    "fisher":       "Machhuara - simple Hinglish, seedha faisla",
    "researcher":   "Scientist - numbers, uncertainty, method",
    "coast_guard":  "Operator - risk, jurisdiction, legal status",
    "authority":    "Fisheries officer - policy, compliance, zones",
}


@dataclass
class Trace:
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    started: float = field(default_factory=time.time)
    steps: list = field(default_factory=list)
    messages: list = field(default_factory=list)

    def log(self, agent, level, text, **kw):
        self.messages.append({
            "t": round(time.time() - self.started, 3),
            "agent": agent, "level": level, "text": text, **kw})

    def step(self, agent, ms, status, confidence=None):
        self.steps.append({"agent": agent, "ms": round(ms, 1),
                           "status": status, "confidence": confidence})

    @property
    def total_ms(self):
        return round(sum(s["ms"] for s in self.steps), 1)


@dataclass
class AgentState:
    user_query: str = ""
    persona: str = "fisher"
    origin: dict | None = None          # {"name":..,"lat":..,"lon":..}
    target: dict | None = None          # {"lat":..,"lon":..,"label":..}
    bbox: list | None = None
    tasks: list = field(default_factory=list)
    intent: str = "FIND_FISHING_ZONE"
    results: dict = field(default_factory=dict)
    grids: dict = field(default_factory=dict)   # real numpy grids
    meta: dict = field(default_factory=dict)
    final: dict | None = None
    trace: Trace = field(default_factory=Trace)

    def set(self, agent, payload):
        self.results[agent] = payload
        return payload
