"""
TACTICAL REPORT — command-center UI.
Canvas radar map + agent swarm mesh + thought stream + latency waterfall + query console.
"""

import base64
import json
from datetime import datetime
from pathlib import Path

import numpy as np

from . import config as C, geo_tools as G


def _enc(a, cap=360):
    if a is None:
        return "null"
    st = max(1, int(max(a.shape) / cap) + 1)
    b = a[::st, ::st]
    return json.dumps([[None if not np.isfinite(v) else round(float(v), 3) for v in r]
                       for r in b], separators=(",", ":"))


def build_tactical(state, maps, prov, cfg, out_html, spots=None):
    b64 = lambda p: base64.b64encode(Path(p).read_bytes()).decode() if p and Path(p).exists() else ""
    sst_png, wind_png, pfz_png = maps
    g = state.grids
    spots = spots or state.meta.get("spots", [])

    rows = "".join(
        f"<tr><td>{i+1}</td>"
        f"<td><a class='gm' target='_blank' href='https://www.google.com/maps?q={s['lat']},{s['lon']}'>"
        f"{s['lat']:.3f}°N {s['lon']:.3f}°E</a></td>"
        f"<td><b class='s' style='color:{('#22c55e' if s['score']>=70 else '#84cc16' if s['score']>=55 else '#eab308' if s['score']>=40 else '#ef4444')}'>{s['score']:.0f}</b></td>"
        f"<td>{s['sst'] if s['sst'] is not None else '—'}</td>"
        f"<td>{s['wind'] if s['wind'] is not None else '—'}</td>"
        f"<td>{s['front'] if s['front'] is not None else '—'}</td>"
        f"<td>{int(s['coast_km']) if s['coast_km'] is not None else '—'}</td>"
        f"<td>{'EEZ' if s['in_eez'] else '—'}</td>"
        f"<td><button class='mini' onclick='fly({s['lat']},{s['lon']})'>ask</button></td></tr>"
        for i, s in enumerate(spots))

    prov_rows = "".join(
        f"<tr><td>{p['layer']}</td><td>{p['source']}</td><td>{p['dataset']}</td>"
        f"<td>{p['file']}</td><td>{p['time']}</td>"
        f"<td class='{'ok' if p['status']=='REAL' else 'warn'}'>{p['status']}</td></tr>"
        for p in prov)

    tr = state.trace
    steps_json = json.dumps(tr.steps, separators=(",", ":"))
    eez_json = json.dumps(G.eez_rings(), separators=(",", ":"))
    fin = state.final or {}

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>MATSYA — Tactical Command</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:#060b16;color:#cbd5e1;font-family:'Segoe UI',Consolas,monospace;
font-size:13px;overflow-x:hidden}}
header{{background:linear-gradient(90deg,#0b1220,#12203a);border-bottom:1px solid #1e3a5f;
padding:10px 18px;display:flex;align-items:center;gap:14px;flex-wrap:wrap}}
h1{{margin:0;font-size:17px;color:#38bdf8;letter-spacing:1px}}
h1 span{{color:#e2e8f0;font-weight:400;font-size:11px}}
.chip{{background:#0f2035;border:1px solid #1e3a5f;border-radius:20px;padding:3px 11px;
font-size:11px;color:#7dd3fc}}
.led{{width:9px;height:9px;border-radius:50%;background:#22c55e;box-shadow:0 0 8px #22c55e;
animation:pulse 1.6s infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.35}}}}
.grid{{display:grid;grid-template-columns:1.55fr 1fr;gap:12px;padding:12px}}
.panel{{background:#0b1424;border:1px solid #1c2f4a;border-radius:9px;padding:11px;
margin-bottom:12px}}
.panel h3{{margin:0 0 9px;font-size:11px;color:#38bdf8;letter-spacing:1.5px;text-transform:uppercase;
border-bottom:1px solid #1c2f4a;padding-bottom:6px;display:flex;justify-content:space-between}}
.mapwrap{{position:relative;width:100%;background:#08101f;border-radius:7px;overflow:hidden}}
#mapImg{{width:100%;display:block;cursor:crosshair}}
#radar{{position:absolute;inset:0;pointer-events:none}}
.btns button{{background:#123049;border:1px solid #1e4b6e;color:#7dd3fc;padding:5px 11px;
border-radius:5px;cursor:pointer;margin:0 5px 7px 0;font-size:11px}}
.btns button.on{{background:#0ea5e9;color:#04202e;font-weight:700;border-color:#0ea5e9}}
.hud{{position:absolute;left:10px;top:10px;background:#040d1ae0;border:1px solid #1e3a5f;
border-radius:6px;padding:7px 10px;font-size:11px;line-height:1.7;min-width:172px;pointer-events:none}}
.hud b{{color:#38bdf8}}
.panel-scroll{{max-height:230px;overflow-y:auto}}
.msg{{border-left:2px solid #1e3a5f;padding:3px 0 3px 8px;margin-bottom:5px;font-size:11.5px;
line-height:1.5}}
.msg .a{{color:#38bdf8;font-weight:700;margin-right:5px}}
.msg .t{{color:#475569;font-size:10px}}
.msg.error{{border-left-color:#ef4444}}
.msg.end{{border-left-color:#22c55e}}
.bars div{{margin-bottom:4px;font-size:11px}}
.bar{{height:9px;background:linear-gradient(90deg,#0ea5e9,#22d3ee);border-radius:3px}}
.wf{{display:grid;grid-template-columns:112px 1fr 46px;gap:5px;align-items:center;font-size:11px}}
.wf .bg{{background:#111e33;border-radius:3px;height:9px;overflow:hidden}}
.wf .fl{{height:100%;background:linear-gradient(90deg,#22d3ee,#0ea5e9);border-radius:3px}}
.card-action{{background:linear-gradient(135deg,#0d1f33,#0a1729);border:1px solid #1e3a5f;
border-radius:9px;padding:13px}}
.verdict{{font-size:23px;font-weight:800;letter-spacing:1.5px}}
.score-ring{{float:right;width:74px;height:74px;border-radius:50%;display:grid;
place-items:center;font-size:19px;font-weight:800;border:3px solid #22c55e}}
table{{width:100%;border-collapse:collapse;font-size:11.5px}}
th{{text-align:left;color:#5b7a99;padding:4px 5px;border-bottom:1px solid #1c2f4a}}
td{{padding:4px 5px;border-bottom:1px solid #12203a}}
a.gm{{color:#38bdf8;text-decoration:none}}
.ok{{color:#22c55e}} .warn{{color:#eab308}}
input,select{{background:#08111f;border:1px solid #1e3a5f;color:#e2e8f0;border-radius:5px;
padding:7px 9px;font-family:inherit;font-size:12px}}
input[type=text]{{flex:1;min-width:200px}}
button.go{{background:#0ea5e9;border:0;color:#04202e;font-weight:700;padding:7px 15px;
border-radius:5px;cursor:pointer}}
.mini{{background:#123049;border:1px solid #1e4b6e;color:#7dd3fc;border-radius:4px;
padding:2px 7px;cursor:pointer;font-size:10.5px}}
.row{{display:flex;gap:7px;flex-wrap:wrap;align-items:center}}
.note{{color:#64748b;font-size:10.5px;margin-top:6px;line-height:1.6}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
@media(max-width:1100px){{.grid{{grid-template-columns:1fr}}.grid2{{grid-template-columns:1fr}}}}
</style></head><body>

<header>
  <div class="led"></div>
  <h1>MATSYA <span>// Marine EcOsystem Reasoning with Collaborative Agents</span></h1>
  <div class="chip">INSAT-3DR SST</div>
  <div class="chip">INSAT-3DR WIND</div>
  <div class="chip">EEZ v12 (MarineRegions)</div>
  <div class="chip">Natural Earth coast</div>
  <div class="chip" id="clock">—</div>
</header>

<div class="grid">
<div>
  <div class="panel">
    <h3>Tactical map <span id="layerName" style="color:#7dd3fc">SST °C</span></h3>
    <div class="btns">
      <button id="l0" class="on" onclick="layer(0)">🌡️ SST</button>
      <button id="l1" onclick="layer(1)">💨 Wind</button>
      <button id="l2" onclick="layer(2)">🎣 PFZ</button>
      <button onclick="toggleRoute()">🧭 Route</button>
    </div>
    <div class="mapwrap">
      <img id="mapImg" src="data:image/png;base64,{b64(sst_png)}">
      <canvas id="radar"></canvas>
      <div class="hud" id="hud">
        <div>📍 <b id="hLat">—</b> , <b id="hLon">—</b></div>
        <div>🌡️ SST <b id="hSst">—</b> °C</div>
        <div>〰️ Front <b id="hFront">—</b> °C/km</div>
        <div>💨 Wind <b id="hWind">—</b> m/s</div>
        <div id="chlRow" style="display:none">🌿 CHL <b id="hChl">—</b> mg/m³</div>
        <div>🎯 PFZ <b id="hPfz">—</b></div>
        <div>🗺️ <b id="hZone">—</b></div>
      </div>
    </div>
    <div class="note">Map pe click karo → HUD update. Radar sweep sirf dikhane ke liye hai
      (real-time nahi) — asli data file ke acquisition time ka hai.</div>
  </div>

  <div class="panel">
    <h3>Top fishing spots <span style="color:#64748b">click "ask" → poora agent analysis</span></h3>
    <div class="panel-scroll"><table>
      <tr><th>#</th><th>Location</th><th>Score</th><th>SST</th><th>Wind</th>
      <th>Front</th><th>Coast km</th><th>Zone</th><th></th></tr>
      {rows}
    </table></div>
  </div>
</div>

<div>
  <div class="card-action">
    <div class="score-ring" id="ring">{fin.get('score', '—')}</div>
    <div class="verdict" id="verdict" style="color:{fin.get('color','#38bdf8')}">{fin.get('headline','ANALYSIS READY')}</div>
    <div style="color:#7dd3fc;font-size:11.5px;margin-top:4px" id="where">{fin.get('where','')}</div>
    <div style="margin-top:9px;color:#cbd5e1;line-height:1.65" id="bullets">
      {"".join(f"<div style='margin-bottom:3px'>{b}</div>" for b in fin.get('bullets', [])) or
       "<i style='color:#64748b'>Query karo ya map pe click karo…</i>"}
    </div>
  </div>

  <div class="panel">
    <h3>Query console <span style="color:#64748b">agent swarm</span></h3>
    <div class="row">
      <input type="text" id="q" placeholder="e.g. Veraval se 40 km SW tuna ke liye jaaun?"
             onkeydown="if(event.key==='Enter')ask()">
      <select id="persona">
        <option value="fisher">Machhuara</option>
        <option value="researcher">Researcher</option>
        <option value="coast_guard">Coast Guard</option>
        <option value="authority">Authority</option>
      </select>
      <button class="go" onclick="ask()">ASK ▶</button>
    </div>
    <div class="note">Server mode (<code>python matsya.py serve</code>) me ye poora agent DAG
      chalaata hai. Static file me sirf map click kaam karega.</div>
  </div>

  <div class="panel">
    <h3>Agent swarm mesh <span style="color:#64748b" id="tot">—</span></h3>
    <svg id="mesh" width="100%" height="200" viewBox="0 0 460 200"></svg>
  </div>

  <div class="panel">
    <h3>Latency waterfall</h3>
    <div id="wf"></div>
  </div>

  <div class="panel">
    <h3>Thought stream</h3>
    <div class="panel-scroll" id="stream"></div>
  </div>
</div>
</div>

<div class="grid"><div class="grid2">
  <div class="panel"><h3>Data provenance</h3><table>
    <tr><th>Layer</th><th>Source</th><th>Dataset</th><th>File</th><th>Time</th><th>Status</th></tr>
    {prov_rows}</table></div>
  <div class="panel"><h3>Regulatory rules (real, verify karein)</h3>
    <div class="panel-scroll" id="rules">
      {"".join(f"<div class='msg'><span class='a'>{r['title']}</span><br>{r['text']}<br>"
               f"<span class='t'>source: {r.get('source','')}</span></div>"
               for r in (fin.get('rules') or [])) or
       "<i style='color:#64748b'>Query karne par yahan relevant niyam aayenge</i>"}</div></div>
</div></div>

<div style="padding:0 12px 20px;color:#475569;font-size:10.5px;line-height:1.7">
MATSYA v1.0 • ISRO/MOSDAC (INSAT-3DR SST + VSW) · MarineRegions/EEZ v12 (VLIZ, CC BY 4.0) ·
Natural Earth (public domain). Deterministic agents = numeric/spatial kaam; LLM sirf optional
language polish ke liye (OPENAI_API_KEY set hone par). Satellite advisory hai — hamesha local
weather, Coast Guard notices aur monsoon ban check karein.
</div>

<script>
const LAT={_enc(g.get('lat'))},LON={_enc(g.get('lon'))},SST={_enc(g.get('sst'))},
 WIND={_enc(g.get('wind'))},GRAD={_enc(g.get('grad'))},PFZ={_enc(g.get('score'))},
 DIST={_enc(g.get('dist'))},EEZ={_enc(g.get('eez'),600)},CHL={_enc(g.get('chl'))};
const RINGS={eez_json};
const IMGS=["data:image/png;base64,{b64(sst_png)}","data:image/png;base64,{b64(wind_png)}",
 "data:image/png;base64,{b64(pfz_png)}"];
const NAMES=["SST °C","Wind m/s","PFZ score"],KEYS=["sst","wind","pfz"];
let cur=0, route=null, showRoute=true;

const img=document.getElementById('mapImg'),cv=document.getElementById('radar'),
 ctx=cv.getContext('2d');
function sizeCanvas(){{cv.width=img.clientWidth;cv.height=img.clientHeight;}}
window.addEventListener('resize',sizeCanvas); img.onload=sizeCanvas;

function layer(k){{cur=k;img.src=IMGS[k];
 for(let i=0;i<3;i++)document.getElementById('l'+i).className=(i===k?'on':'');
 document.getElementById('layerName').textContent=NAMES[k];}}

/* ---------- radar sweep + route ---------- */
let ang=0;
function draw(){{
  if(cv.width!==img.clientWidth||cv.height!==img.clientHeight)sizeCanvas();
  const w=cv.width,h=cv.height;ctx.clearRect(0,0,w,h);
  const cx=w/2,cy=h/2,R=Math.min(w,h)/2;ang+=0.012;
  const grd=ctx.createConicGradient?ctx.createConicGradient(ang,cx,cy):null;
  ctx.save();ctx.beginPath();ctx.moveTo(cx,cy);
  ctx.arc(cx,cy,R,ang-0.30,ang);ctx.closePath();
  ctx.fillStyle='rgba(34,211,238,0.045)';ctx.fill();ctx.restore();
  ctx.strokeStyle='rgba(34,211,238,0.10)';ctx.lineWidth=1;
  for(let r=40;r<R;r+=40){{ctx.beginPath();ctx.arc(cx,cy,r,0,6.28);ctx.stroke();}}
  ctx.beginPath();ctx.moveTo(cx-R,cy);ctx.lineTo(cx+R,cy);
  ctx.moveTo(cx,cy-R);ctx.lineTo(cx,cy+R);ctx.stroke();
  if(route&&showRoute){{
    ctx.beginPath();let first=true;
    for(const c of route.coordinates){{
      const p=toPix(c[1],c[0]);if(!p)continue;
      first?(ctx.moveTo(p[0],p[1]),first=false):ctx.lineTo(p[0],p[1]);}}
    ctx.strokeStyle='#f43f5e';ctx.lineWidth=2;
    ctx.setLineDash([7,5]);ctx.lineDashOffset=-performance.now()/60;ctx.stroke();
    ctx.setLineDash([]);}}
  requestAnimationFrame(draw);}}
requestAnimationFrame(draw);

function bboxPix(){{
  let lo=1e9,la=1e9,LO=-1e9,LA=-1e9;
  for(let i=0;i<LAT.length;i++)for(let j=0;j<LAT[0].length;j++){{
    if(LAT[i][j]===null)continue;
    lo=Math.min(lo,LON[i][j]);LO=Math.max(LO,LON[i][j]);
    la=Math.min(la,LAT[i][j]);LA=Math.max(LA,LAT[i][j]);}}
  return {{lo,la,LO,LA}};}}
const BB=bboxPix();
function toPix(lat,lon){{
  const x=(lon-BB.lo)/(BB.LO-BB.lo),y=(BB.LA-lat)/(BB.LA-BB.la);
  if(x<0||x>1||y<0||y>1)return null;
  return [x*img.clientWidth,y*img.clientHeight];}}

function pip(pt,ring){{let c=false;
 for(let i=0,j=ring.length-1;i<ring.length;j=i++){{const xi=ring[i][0],yi=ring[i][1],
  xj=ring[j][0],yj=ring[j][1];
  if(((yi>pt[1])!=(yj>pt[1]))&&(pt[0]<(xj-xi)*(pt[1]-yi)/(yj-yi)+xi))c=!c;}}return c;}}
function eezOf(lo,la){{for(const k in RINGS){{for(const poly of RINGS[k]){{
 if(pip([lo,la],poly[0]))return k;}}}}return null;}}

function cell(e){{
  const r=img.getBoundingClientRect();
  let j=Math.round((e.clientX-r.left)/r.width*(LAT[0].length-1));
  let i=Math.round((e.clientY-r.top)/r.height*(LAT.length-1));
  return [Math.max(0,Math.min(LAT.length-1,i)),Math.max(0,Math.min(LAT[0].length-1,j))];}}
function showHud(i,j){{
  const gv=(a)=>(a&&a[i][j]!==null&&a[i][j]!==undefined)?a[i][j]:null;
  document.getElementById('hLat').textContent=LAT[i][j]?LAT[i][j].toFixed(3):'—';
  document.getElementById('hLon').textContent=LON[i][j]?LON[i][j].toFixed(3):'—';
  document.getElementById('hSst').textContent=gv(SST)?.toFixed(2)??'—';
  document.getElementById('hFront').textContent=gv(GRAD)?.toFixed(3)??'—';
  document.getElementById('hWind').textContent=gv(WIND)?.toFixed(1)??'—';
  if(CHL&&CHL[i][j]!==null){{document.getElementById('chlRow').style.display='block';
   document.getElementById('hChl').textContent=CHL[i][j].toFixed(3);}}
  document.getElementById('hPfz').textContent=gv(PFZ)?.toFixed(0)??'—';
  document.getElementById('hZone').textContent=eezOf(LON[i][j],LAT[i][j])||'High Seas';}}
img.addEventListener('click',e=>{{const[i,j]=cell(e);showHud(i,j);}});
img.addEventListener('mousemove',e=>{{const[i,j]=cell(e);showHud(i,j);}});
function toggleRoute(){{showRoute=!showRoute;}}
function fly(la,lo){{document.getElementById('q').value=la.toFixed(3)+' '+lo.toFixed(3)+' pe fishing kaisi rahegi?';ask();}}

/* ---------- agent swarm mesh (SVG) ---------- */
const AG=[["supervisor",210,24],["ocean_analytics",58,80],["risk_geofencing",210,80],
 ["navigation",362,80],["policy_rag",80,140],["species_forecaster",215,140],
 ["synthesizer",360,140]];
const EDGES=[["supervisor","ocean_analytics"],["supervisor","risk_geofencing"],
 ["supervisor","navigation"],["ocean_analytics","synthesizer"],
 ["risk_geofencing","synthesizer"],["navigation","synthesizer"],
 ["policy_rag","synthesizer"],["species_forecaster","synthesizer"]];
function mesh(activeSet){{
  const s=document.getElementById('mesh');s.innerHTML='';
  const NS='http://www.w3.org/2000/svg';
  const defs=document.createElementNS(NS,'defs');
  EDGES.forEach((e,i)=>{{
    const a=AG.find(x=>x[0]===e[0]),b=AG.find(x=>x[0]===e[1]);
    const l=document.createElementNS(NS,'line');
    l.setAttribute('x1',a[1]);l.setAttribute('y1',a[2]);
    l.setAttribute('x2',b[1]);l.setAttribute('y2',b[2]);
    l.setAttribute('stroke',activeSet.has(e[0])&&activeSet.has(e[1])?'#22d3ee':'#1e3a5f');
    l.setAttribute('stroke-width',activeSet.has(e[0])?'1.8':'1');
    s.appendChild(l);
    const c=document.createElementNS(NS,'circle');c.setAttribute('r','2.6');
    c.setAttribute('fill','#22d3ee');
    const an=document.createElementNS(NS,'animateMotion');
    an.setAttribute('dur','2.4s');an.setAttribute('repeatCount','indefinite');
    an.setAttribute('path',`M${{a[1]}},${{a[2]}} L${{b[1]}},${{b[2]}}`);
    an.setAttribute('begin',(i*0.28)+'s');c.appendChild(an);s.appendChild(c);}});
  AG.forEach(a=>{{
    const g=document.createElementNS(NS,'g');
    const r=document.createElementNS(NS,'rect');
    r.setAttribute('x',a[1]-52);r.setAttribute('y',a[2]-12);
    r.setAttribute('width',104);r.setAttribute('height',24);r.setAttribute('rx',6);
    r.setAttribute('fill',activeSet.has(a[0])?'#0b3a52':'#0d1a2b');
    r.setAttribute('stroke',activeSet.has(a[0])?'#22d3ee':'#243b57');
    g.appendChild(r);
    const t=document.createElementNS(NS,'text');
    t.setAttribute('x',a[1]);t.setAttribute('y',a[2]+4);
    t.setAttribute('text-anchor','middle');t.setAttribute('font-size','8.6');
    t.setAttribute('fill',activeSet.has(a[0])?'#7dd3fc':'#5b7a99');
    t.textContent=a[0];g.appendChild(t);s.appendChild(g);}});
}}

/* ---------- waterfall + stream ---------- */
function waterfall(steps){{
  const el=document.getElementById('wf');
  const mx=Math.max(1,...steps.map(s=>s.ms));
  el.innerHTML='<div class="wf"></div>';
  const w=el.firstChild;
  steps.forEach(s=>{{
    const a=document.createElement('div');a.textContent=s.agent;
    const b=document.createElement('div');b.className='bg';
    const f=document.createElement('div');f.className='fl';
    f.style.width=(s.ms/mx*100).toFixed(1)+'%';
    b.appendChild(f);
    const c=document.createElement('div');c.textContent=s.ms.toFixed(0)+'ms';
    c.style.color=s.status==='ERROR'?'#ef4444':'#94a3b8';
    w.appendChild(a);w.appendChild(b);w.appendChild(c);}});
  document.getElementById('tot').textContent='total '+steps.reduce((x,y)=>x+y.ms,0).toFixed(0)+'ms';
}}
function stream(msgs){{
  const el=document.getElementById('stream');el.innerHTML='';
  msgs.forEach(m=>{{
    const d=document.createElement('div');
    d.className='msg '+(m.level==='error'?'error':(m.level==='end'?'end':''));
    d.innerHTML=`<span class="a">${{m.agent}}</span>
      <span class="t">${{m.t.toFixed(2)}}s</span><br>${{m.text}}`;
    el.appendChild(d);}});
  el.scrollTop=el.scrollHeight;}}
function paint(res){{
  if(!res)return;
  document.getElementById('verdict').textContent=res.headline||'—';
  document.getElementById('verdict').style.color=res.color||'#38bdf8';
  document.getElementById('ring').textContent=res.score??'—';
  document.getElementById('ring').style.borderColor=res.color||'#22c55e';
  document.getElementById('where').textContent=res.where||'';
  document.getElementById('bullets').innerHTML=(res.bullets||[]).map(b=>
    `<div style="margin-bottom:3px">${{b}}</div>`).join('')||'—';
  if(res.rules)document.getElementById('rules').innerHTML=res.rules.map(r=>
    `<div class="msg"><span class="a">${{r.title}}</span><br>${{r.text}}<br>
     <span class="t">source: ${{r.source||''}}</span></div>`).join('');
  route=res.route||route;
  const names=new Set(Object.keys(res.results||{{}}));
  mesh(names);waterfall(res.trace?.steps||[]);stream(res.trace?.messages||[]);
}}
function ask(){{
  const q=document.getElementById('q').value.trim();
  if(!q)return;
  document.getElementById('bullets').innerHTML='<i style="color:#38bdf8">agents chal rahe hain…</i>';
  fetch('/api/ask',{{method:'POST',headers:{{'Content-Type':'application/json'}},
   body:JSON.stringify({{query:q,persona:document.getElementById('persona').value}})}})
   .then(r=>r.json()).then(paint)
   .catch(e=>{{document.getElementById('bullets').innerHTML=
     '<i style="color:#eab308">Server mode chalu nahi? <code>python matsya.py serve</code> chalao. '
     +e+'</i>';}});}}
setInterval(()=>{{document.getElementById('clock').textContent=
  new Date().toLocaleTimeString('en-IN');}},1000);
mesh(new Set({json.dumps(sorted(state.results.keys()))}));
waterfall({steps_json});
stream({json.dumps(tr.messages, ensure_ascii=False)});
</script></body></html>"""
    Path(out_html).write_text(html, encoding="utf-8")
    return str(out_html)
