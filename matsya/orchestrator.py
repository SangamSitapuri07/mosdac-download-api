"""
ORCHESTRATOR — agent DAG. LangGraph ki tarah, par zero dependency.

Wave 1 (parallel): ocean_analytics + risk_geofencing
Wave 2 (parallel): navigation + policy_rag
Wave 3          : synthesizer

Har wave ka latency record hota hai -> UI me "latency waterfall" dikhta hai.
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .agents.base import Agent
from .agents.navigation import Navigation
from .agents.ocean_analytics import OceanAnalytics
from .agents.policy import PolicyRAG
from .agents.risk_geofencing import RiskGeofencing
from .agents.state import AgentState
from .agents.supervisor import Supervisor
from .agents.synthesizer import Synthesizer

AGENTS = {
    "supervisor": Supervisor,
    "ocean_analytics": OceanAnalytics,
    "risk_geofencing": RiskGeofencing,
    "navigation": Navigation,
    "policy_rag": PolicyRAG,
    "synthesizer": Synthesizer,
}

WAVES = [
    ["ocean_analytics", "risk_geofencing"],
    ["navigation", "policy_rag"],
    ["synthesizer"],
]


class Orchestrator:
    def __init__(self, cfg, audit_dir=None):
        self.cfg = cfg
        self.agents = {k: v() for k, v in AGENTS.items()}
        self.audit_dir = Path(audit_dir) if audit_dir else None

    def run(self, state: AgentState) -> AgentState:
        self.agents["supervisor"](state)
        state.trace.log("orchestrator", "plan",
                        f"tasks: {', '.join(state.tasks)}")

        for wave in WAVES:
            todo = [t for t in wave if t in state.tasks or t == "synthesizer"]
            if not todo:
                continue
            t0 = time.perf_counter()
            with ThreadPoolExecutor(max_workers=len(todo)) as ex:
                list(ex.map(lambda n: self.agents[n](state), todo))
            state.trace.log("orchestrator", "wave",
                            f"{', '.join(todo)} ek saath chale",
                            ms=round((time.perf_counter() - t0) * 1000, 1))

        state.trace.log("orchestrator", "done",
                        f"total {state.trace.total_ms} ms, "
                        f"{len(state.trace.steps)} agent steps")
        self._audit(state)
        return state

    def _audit(self, state):
        if not self.audit_dir:
            return
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        rec = {
            "run_id": state.trace.run_id,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "query": state.user_query,
            "persona": state.persona,
            "intent": state.intent,
            "origin": state.origin,
            "target": state.target,
            "total_ms": state.trace.total_ms,
            "steps": state.trace.steps,
            "messages": state.trace.messages,
            "verdict": (state.final or {}).get("verdict"),
            "score": (state.final or {}).get("score"),
            "risk": (state.final or {}).get("risk"),
        }
        with open(self.audit_dir / "execution_audit.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
