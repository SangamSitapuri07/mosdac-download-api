"""
Agent 6 — SYNTHESIZER / LOCALIZATION
Sab agents ke findings ko ek saaf Hinglish (ya English) advisory me badalta hai.

Offline by default (templated). Agar OPENAI_API_KEY set ho to optional LLM rewrite.
"""

import os

from .base import Agent

PERSONA_TONE = {
    "fisher": "Seedhi Hinglish baat, bina bhaasha-bhaari shabdon ke.",
    "researcher": "Numbers, uncertainty aur method ke saath likho.",
    "coast_guard": "Risk, jurisdiction aur legal status pe focus.",
    "authority": "Compliance, zones aur notification references ke saath.",
}


class Synthesizer(Agent):
    name = "synthesizer"
    role = "Final advisory banana (Hinglish)"
    uses_llm = False

    def run(self, state):
        cfg = state.meta["cfg"]
        oa = (state.results.get("ocean_analytics") or {}).get("findings", {})
        rk = (state.results.get("risk_geofencing") or {}).get("findings", {})
        nv = (state.results.get("navigation") or {}).get("findings", {})
        pl = (state.results.get("policy_rag") or {}).get("findings", {})
        sp = (state.results.get("species_forecaster") or {}).get("findings", {})
        pt_o = oa.get("point") or {}
        pt_r = rk.get("point") or {}

        # ---- verdict ----
        pfz = pt_o.get("pfz")
        risk = pt_r.get("risk_level", "LOW")
        if pfz is None:
            pfz = oa.get("pfz_max")
            score_src = "grid max"
        else:
            score_src = "query point"

        if risk == "CRITICAL":
            head, col, verdict = "MAT JAO", "#ef4444", "NO-GO"
        elif pfz is not None and pfz >= cfg["advisory"]["go"] and risk != "HIGH":
            head, col, verdict = "JAO — BEST ZONE", "#22c55e", "GO"
        elif pfz is not None and pfz >= cfg["advisory"]["ok"]:
            head, col, verdict = "THEEK HAI", "#84cc16", "OK"
        elif pfz is not None and pfz >= cfg["advisory"]["maybe"]:
            head, col, verdict = "SHAYAD", "#eab308", "MAYBE"
        else:
            head, col, verdict = "MAT JAO", "#ef4444", "NO-GO"

        # ---- bullet points ----
        bullets = []
        if pt_o.get("sst_c") is not None:
            bullets.append(f"🌡️ **SST {pt_o['sst_c']} °C** — "
                           f"{'optimum range (26–30 °C) me' if 26 <= pt_o['sst_c'] <= 30 else 'optimum se bahar'}")
        if pt_o.get("sst_c") is None:
            bullets.append("🛰️ **Is point par satellite SST data nahi hai** (zameen / cloud / "
                           "swath ke bahar) — nazdiki valid zone ke liye top-spots table dekho")
        if pt_o.get("front_c_per_km") is not None:
            strong = pt_o["front_c_per_km"] >= cfg["physics"]["front_ref_c_per_km"]
            bullets.append(f"〰️ **Thermal front {pt_o['front_c_per_km']} °C/km** — "
                           f"{'strong front, machhliyon ke jamav ke liye achha' if strong else 'kamzor front'}")
        if pt_o.get("wind_ms") is not None:
            bullets.append(f"💨 **Hawa {pt_o['wind_ms']} m/s** — {pt_r.get('sea_state','')}")
        if pt_r.get("in_india_eez") is not None:
            bullets.append(f"🗺️ **{'India EEZ ke andar' if pt_r['in_india_eez'] else 'India EEZ ke BAHAR'}**")
        if pt_r.get("coast_km") is not None:
            bullets.append(f"📏 **Coast se {pt_r['coast_km']:.0f} km**")
        if nv.get("route_nm"):
            bullets.append(f"🧭 **{nv['from']} se {nv['route_nm']} NM** — ETA {nv['eta_text']}, "
                           f"~{nv['fuel_litres']:.0f} L diesel")
        for r in (sp.get("species") or [])[:2]:
            bullets.append(f"🐟 **{r['species']}** ({r['score']:.0f}/100) — "
                           + "; ".join(r["reasons"][:2]))
        for r in (pl.get("rules") or [])[:3]:
            bullets.append(f"⚖️ **{r['title']}** — {r['text'][:150]}")
        for rsn in (pt_r.get("reasons") or [])[:3]:
            bullets.append(f"⚠️ {rsn}")

        # ---- summary text ----
        where = (state.target or {}).get("label") or (
            f"{pt_o.get('lat')}°N, {pt_o.get('lon')}°E" if pt_o else "poora grid")
        text = (f"**{head}** — {where} ke liye advisory.\n"
                f"PFZ score **{pfz}/100** ({score_src}), risk level **{risk}**.\n"
                + "\n".join(f"• {b}" for b in bullets))

        # ---- optional LLM polish ----
        llm_used = False
        if os.getenv("OPENAI_API_KEY") and state.meta.get("use_llm"):
            try:
                text = self._llm(state, text)
                llm_used = True
                self.uses_llm = True
            except Exception:
                pass

        conf = round(sum(a.get("confidence", 0) for a in state.results.values()) /
                     max(len(state.results), 1), 2)

        final = {
            "verdict": verdict, "headline": head, "color": col,
            "score": pfz, "risk": risk, "where": where,
            "bullets": bullets, "text": text,
            "confidence": conf, "llm_used": llm_used,
            "persona": state.persona,
            "tone": PERSONA_TONE.get(state.persona, ""),
            "spots": state.meta.get("spots", [])[:8],
            "rules": pl.get("rules", [])[:5],
        }
        state.final = final
        return {"status": "OK", "confidence": conf,
                "findings": final,
                "evidence": [self.ev("verdict", head, f"PFZ {pfz}/100, risk {risk}", "synthesizer")],
                "text": head + " — " + where}

    def _llm(self, state, draft):
        import requests
        base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        r = requests.post(f"{base}/chat/completions",
                          headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                          json={"model": model, "temperature": 0.3, "messages": [
                              {"role": "system", "content":
                               f"Tum ek Indian marine advisory assistant ho. "
                               f"Persona: {state.persona}. {PERSONA_TONE.get(state.persona,'')} "
                               f"Hinglish me jawab do, 120 shabdon se kam. Numbers mat badlo."},
                              {"role": "user", "content": draft}]}, timeout=60)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
