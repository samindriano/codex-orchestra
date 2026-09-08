#!/usr/bin/env python3
"""Highlight-first read-only UI for Orchestra telemetry.

Presentation-only layer over scripts/orchestra_dashboard.py. It reuses the
canonical read/fold/cache semantics and never writes telemetry.
"""

from __future__ import annotations

import argparse
import html
import http.server
import json
from pathlib import Path
import sys
from typing import Any
import webbrowser

try:
    import orchestra_dashboard as core
except ModuleNotFoundError:
    from scripts import orchestra_dashboard as core  # type: ignore


UI_VERSION = "3.0"


def _json_for_html(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).replace("</", "<\\/")


def build_html(snapshot: dict[str, Any], *, live: bool) -> str:
    payload = _json_for_html(snapshot)
    template = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Orchestra</title>
<style>
:root{
  color-scheme:dark;
  --bg:#0a0b0d;
  --sidebar:#0d0f12;
  --panel:#12151a;
  --panel2:#171b21;
  --line:#242a32;
  --line2:#303844;
  --text:#f4f6f8;
  --muted:#9ba4af;
  --faint:#65707d;
  --accent:#8aa8ff;
  --accent2:#b3c5ff;
  --good:#67d99a;
  --warn:#f0c36d;
  --bad:#f07f8f;
  --radius:12px;
}
*{box-sizing:border-box}
html,body{margin:0;min-height:100%;background:var(--bg);color:var(--text);font:14px/1.45 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
button,input,select{font:inherit}
.sidebar{position:fixed;inset:0 auto 0 0;width:210px;background:var(--sidebar);border-right:1px solid #1b2027;padding:20px 14px;z-index:20}
.brand{padding:2px 10px 22px;font-size:17px;font-weight:760;letter-spacing:-.03em}
.brand b{color:var(--accent)}
.nav{display:grid;gap:4px}
.nav button{height:39px;padding:0 11px;border:0;border-radius:8px;background:transparent;color:#929ba6;text-align:left;cursor:pointer;font-weight:620}
.nav button:hover{background:#151920;color:#d9dee4}
.nav button.active{background:#1a2029;color:#fff}
.side-bottom{position:absolute;left:14px;right:14px;bottom:18px;padding:12px 10px;border-top:1px solid #1b2027;color:var(--faint);font-size:11px}
.live{display:flex;align-items:center;gap:7px;color:#aab2bb}
.live-dot{width:7px;height:7px;border-radius:99px;background:var(--good)}
.shell{margin-left:210px;min-height:100vh}
.top{position:sticky;top:0;z-index:15;height:64px;display:flex;align-items:center;justify-content:space-between;padding:0 30px;border-bottom:1px solid #1b2027;background:rgba(10,11,13,.94);backdrop-filter:blur(14px)}
.page-title{font-size:16px;font-weight:680}
.top-right{display:flex;align-items:center;gap:12px}
.updated{color:var(--faint);font-size:11px}
.refresh{height:34px;padding:0 12px;border:1px solid var(--line2);border-radius:8px;background:#171b21;color:#e4e8ed;cursor:pointer}
.content{max-width:1560px;margin:0 auto;padding:26px 30px 52px}
.view{display:none}.view.active{display:block}
.filters{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:18px}
.periods{display:flex;padding:3px;border:1px solid var(--line);border-radius:9px;background:#101318}
.periods button{height:30px;padding:0 11px;border:0;border-radius:6px;background:transparent;color:#818b97;cursor:pointer;font-size:12px}
.periods button.active{background:#242b35;color:#fff}
.filters select,.filters input[type=search]{height:36px;border:1px solid var(--line);border-radius:8px;background:#11151a;color:#e5e9ed;padding:0 10px}
.filters select{min-width:132px}.filters input[type=search]{min-width:210px}
.filters label{display:flex;align-items:center;gap:6px;color:var(--muted);font-size:12px}
.filters input[type=checkbox]{accent-color:var(--accent)}
.hero{display:grid;grid-template-columns:minmax(360px,1.4fr) repeat(3,minmax(150px,.7fr));overflow:hidden;border:1px solid var(--line2);border-radius:14px;background:var(--panel)}
.hero-main{padding:24px 26px;border-right:1px solid var(--line)}
.hero-label{color:var(--faint);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.08em}
.hero-title{margin-top:8px;font-size:25px;font-weight:760;letter-spacing:-.04em}
.hero-meta{margin-top:5px;color:var(--muted);font-size:13px}
.badges{display:flex;gap:6px;margin-top:14px;flex-wrap:wrap}
.badge{display:inline-flex;align-items:center;height:24px;padding:0 8px;border:1px solid var(--line2);border-radius:999px;background:#171c23;color:#a8b1bb;font-size:10px;font-weight:700}
.badge.good{color:var(--good);border-color:rgba(103,217,154,.28);background:rgba(103,217,154,.08)}
.badge.warn{color:var(--warn);border-color:rgba(240,195,109,.28);background:rgba(240,195,109,.08)}
.badge.bad{color:var(--bad);border-color:rgba(240,127,143,.28);background:rgba(240,127,143,.08)}
.badge.fast{color:var(--accent2);border-color:rgba(138,168,255,.34);background:rgba(138,168,255,.09)}
.hero-stat{display:flex;flex-direction:column;justify-content:center;padding:20px;border-right:1px solid var(--line)}
.hero-stat:last-child{border-right:0}
.hero-stat span{color:var(--faint);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.07em}
.hero-stat strong{margin-top:8px;font-size:27px;letter-spacing:-.045em;font-variant-numeric:tabular-nums}
.hero-stat small{margin-top:3px;color:var(--faint);font-size:10px}
.kpis{display:grid;grid-template-columns:repeat(5,minmax(150px,1fr));gap:10px;margin-top:10px}
.kpi{padding:15px 16px;border:1px solid var(--line);border-radius:10px;background:var(--panel)}
.kpi span{display:block;color:var(--faint);font-size:10px;font-weight:720;text-transform:uppercase;letter-spacing:.08em}
.kpi strong{display:block;margin-top:6px;font-size:22px;letter-spacing:-.035em}
.section{margin-top:24px}
.section-head{display:flex;align-items:end;justify-content:space-between;margin-bottom:10px}
.section-head h2{margin:0;font-size:15px;letter-spacing:-.02em}
.section-head span{color:var(--faint);font-size:11px}
.chart-grid{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(360px,.85fr);gap:10px}
.panel{min-width:0;border:1px solid var(--line);border-radius:12px;background:var(--panel)}
.panel-head{display:flex;align-items:center;justify-content:space-between;padding:16px 18px 0}
.panel-head h3{margin:0;font-size:14px}.panel-head span{color:var(--faint);font-size:11px}
.chart{height:300px;padding:8px 14px 14px}
.chart svg{width:100%;height:100%;display:block}
.gridline{stroke:#222831;stroke-width:1}.axis{stroke:#38414d;stroke-width:1}
.line{fill:none;stroke:var(--accent);stroke-width:2.6;stroke-linejoin:round;stroke-linecap:round}
.bar{fill:var(--accent)}.bar:hover{fill:var(--accent2)}
.point{fill:var(--accent);stroke:#e7edff;stroke-width:1.2}
.label{fill:#87919c;font-size:12px}
.empty{height:280px;display:grid;place-items:center;text-align:center;color:var(--faint);font-size:13px}
.recent{overflow:hidden}
.recent-head,.recent-row{display:grid;grid-template-columns:92px minmax(220px,1.5fr) 130px 110px 110px 110px 100px;gap:12px;align-items:center}
.recent-head{padding:10px 14px;border-bottom:1px solid var(--line);color:var(--faint);font-size:10px;font-weight:720;text-transform:uppercase}
.recent-row{padding:13px 14px;border-bottom:1px solid #1e242c;cursor:pointer}
.recent-row:last-child{border-bottom:0}.recent-row:hover{background:var(--panel2)}
.main{font-weight:630;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sub{margin-top:2px;color:var(--faint);font-size:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.num{text-align:right;font-variant-numeric:tabular-nums}
.table-wrap{overflow:auto}.turn-table{width:100%;min-width:980px;border-collapse:collapse}
.turn-table th,.turn-table td{padding:12px 13px;border-bottom:1px solid #1e242c;text-align:left;white-space:nowrap}
.turn-table th{position:sticky;top:0;background:#141820;color:var(--faint);font-size:10px;text-transform:uppercase}
.turn-table tbody tr{cursor:pointer}.turn-table tbody tr:hover{background:var(--panel2)}
.pagination{display:flex;justify-content:space-between;align-items:center;padding:11px 13px;color:var(--faint);font-size:11px}
.pagination button{height:30px;border:1px solid var(--line);border-radius:7px;background:#171b21;color:#c9d0d8;padding:0 10px}
.orch-layout{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(300px,.55fr);gap:10px}
.orch-main{padding:18px}.turn-picker{width:100%;height:38px;border:1px solid var(--line);border-radius:8px;background:#11151a;color:#e5e9ed;padding:0 10px}
.orch-big{display:grid;grid-template-columns:repeat(4,1fr);gap:9px;margin:14px 0}
.orch-big div{padding:14px;border:1px solid var(--line);border-radius:9px;background:#101318}
.orch-big span{display:block;color:var(--faint);font-size:10px;text-transform:uppercase}
.orch-big strong{display:block;margin-top:5px;font-size:20px}
.worker-table{overflow:hidden;border:1px solid var(--line);border-radius:9px}
.worker-row{display:grid;grid-template-columns:minmax(160px,1.5fr) 120px 110px 90px;gap:10px;padding:11px 12px;border-bottom:1px solid var(--line)}
.worker-row:last-child{border-bottom:0}.worker-row.head{background:#141820;color:var(--faint);font-size:10px;text-transform:uppercase}
.compare{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.cohort{padding:18px}.cohort h3{margin:0;font-size:16px}.cohort .n{margin-top:4px;color:var(--faint);font-size:11px}
.cohort-metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:16px}
.cohort-metrics div{padding:12px;border:1px solid var(--line);border-radius:8px;background:#101318}
.cohort-metrics span{display:block;color:var(--faint);font-size:10px}.cohort-metrics strong{display:block;margin-top:5px;font-size:18px}
.drawer-bg{display:none;position:fixed;inset:0;z-index:49;background:rgba(0,0,0,.55)}.drawer-bg.open{display:block}
.drawer{position:fixed;z-index:50;top:0;right:0;bottom:0;width:min(520px,94vw);padding:22px;overflow:auto;background:#0f1216;border-left:1px solid var(--line2);transform:translateX(103%);transition:.18s}.drawer.open{transform:translateX(0)}
.drawer-top{display:flex;justify-content:space-between;gap:12px}.drawer-top h2{margin:0;font-size:20px}.drawer-close{width:32px;height:32px;border:1px solid var(--line);border-radius:7px;background:#171b21;color:#d8dde3}
.drawer-section{margin-top:20px}.drawer-section h3{margin:0 0 9px;color:var(--faint);font-size:10px;text-transform:uppercase}
.detail-grid{display:grid;grid-template-columns:1fr 1fr;border:1px solid var(--line);border-radius:9px;overflow:hidden}
.detail{padding:11px 12px;border-right:1px solid var(--line);border-bottom:1px solid var(--line)}.detail:nth-child(even){border-right:0}
.detail span{display:block;color:var(--faint);font-size:10px}.detail strong{display:block;margin-top:4px;font-size:13px;overflow-wrap:anywhere}
@media(max-width:1100px){.sidebar{width:176px}.shell{margin-left:176px}.hero{grid-template-columns:1fr 1fr}.hero-main{grid-column:1/-1;border-right:0;border-bottom:1px solid var(--line)}.kpis{grid-template-columns:repeat(2,1fr)}.chart-grid,.orch-layout{grid-template-columns:1fr}.recent-head,.recent-row{grid-template-columns:82px minmax(180px,1.5fr) 110px 90px 90px}.recent-head>:nth-child(6),.recent-row>:nth-child(6),.recent-head>:nth-child(7),.recent-row>:nth-child(7){display:none}}
</style>
</head>
<body>
<aside class="sidebar">
  <div class="brand">Orchestra <b>Telemetry</b></div>
  <div class="nav">
    <button class="active" data-view="overview">Overview</button>
    <button data-view="turns">Turns</button>
    <button data-view="orchestra">Orchestra</button>
    <button data-view="compare">Compare</button>
  </div>
  <div class="side-bottom">
    <div class="live"><span class="live-dot"></span><span id="liveState">Live ledger</span></div>
    <div id="coverageMini" style="margin-top:6px"></div>
  </div>
</aside>
<div class="shell">
  <header class="top">
    <div class="page-title" id="pageTitle">Overview</div>
    <div class="top-right"><span id="updated" class="updated"></span><button id="refresh" class="refresh">Refresh</button></div>
  </header>
  <main class="content">
    <div class="filters">
      <div class="periods">
        <button data-period="today">Today</button><button data-period="7d">7D</button><button data-period="30d">30D</button><button class="active" data-period="all">All</button>
      </div>
      <select id="project"><option value="">All projects</option></select>
      <select id="model"><option value="">All models</option></select>
      <select id="speed"><option value="">All speeds</option></select>
      <input id="search" type="search" placeholder="Search project">
      <label><input id="exact" type="checkbox"> Exact only</label>
      <label><input id="auto" type="checkbox" checked> Auto</label>
    </div>

    <section id="overviewView" class="view active"></section>
    <section id="turnsView" class="view"></section>
    <section id="orchestraView" class="view"></section>
    <section id="compareView" class="view"></section>
  </main>
</div>
<div id="drawerBg" class="drawer-bg"></div>
<aside id="drawer" class="drawer"></aside>
<script>
let DATA=__PAYLOAD__;
const LIVE=__LIVE__;
const U='UNKNOWN';
const $=id=>document.getElementById(id);
const state={view:'overview',period:'all',project:'',model:'',speed:'',query:'',exact:false,page:1,drawer:null};
const esc=v=>String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const known=v=>v!==null&&v!==undefined&&v!==''&&v!==U;
const compact=v=>{if(!known(v))return U;const n=Number(v);if(Math.abs(n)>=1e9)return(n/1e9).toFixed(n>=1e10?1:2)+'B';if(Math.abs(n)>=1e6)return(n/1e6).toFixed(n>=1e7?1:2)+'M';if(Math.abs(n)>=1e3)return(n/1e3).toFixed(n>=1e4?1:2)+'K';return Math.round(n).toLocaleString()};
const duration=v=>{if(!known(v))return U;let s=Math.round(Number(v));const h=Math.floor(s/3600);s%=3600;const m=Math.floor(s/60);s%=60;if(h)return h+'h '+m+'m';if(m)return m+'m '+s+'s';return s+'s'};
const pct=v=>known(v)?(Number(v)*100).toFixed(1)+'%':U;
const ts=v=>known(v)?new Date(v).getTime():0;
const time=v=>known(v)?new Date(v).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}):U;
const day=v=>known(v)?new Date(v).toLocaleDateString([], {month:'short',day:'numeric'}):U;
function statusBadge(s){const c=s==='COMPLETED'?'good':(s==='OPEN'?'warn':(s==='INTERRUPTED'||s==='FAILED'?'bad':''));return '<span class="badge '+c+'">'+esc(s||U)+'</span>'}
function speedBadge(r){if(r.speed_certified)return '<span class="badge fast">'+esc(r.speed_mode)+'</span>';return '<span class="badge">'+esc(r.speed_mode||U)+'</span>'}
function setOptions(id,values,label){const el=$(id),old=el.value;el.innerHTML='<option value="">'+label+'</option>'+values.map(v=>'<option>'+esc(v)+'</option>').join('');if(values.includes(old))el.value=old}
function initOptions(){setOptions('project',DATA.filters?.projects||[],'All projects');setOptions('model',DATA.filters?.models||[],'All models');setOptions('speed',DATA.filters?.speed_modes||[],'All speeds')}
function filtered(){
  const now=Date.now(),q=state.query.toLowerCase();
  return (DATA.turns||[]).filter(r=>{
    const t=ts(r.timestamp);
    if(state.period==='today'&&day(r.timestamp)!==day(new Date().toISOString()))return false;
    if(state.period==='7d'&&t<now-7*864e5)return false;
    if(state.period==='30d'&&t<now-30*864e5)return false;
    if(state.project&&r.project!==state.project)return false;
    if(state.model&&r.model!==state.model)return false;
    if(state.speed&&r.speed_mode!==state.speed)return false;
    if(state.exact&&r.usage_quality!=='EXACT')return false;
    if(q&&!String(r.project+' '+r.worktree+' '+r.model).toLowerCase().includes(q))return false;
    return true;
  }).sort((a,b)=>ts(b.timestamp)-ts(a.timestamp));
}
function latestMeasured(rows){return rows.find(r=>r.usage_quality==='EXACT')||rows[0]||null}
function sum(rows,key){return rows.reduce((a,r)=>a+(known(r[key])?Number(r[key]):0),0)}
function renderOverview(){
  const rows=filtered(),r=latestMeasured(rows),todayRows=rows.filter(x=>day(x.timestamp)===day(new Date().toISOString()));
  const exact=todayRows.filter(x=>x.usage_quality==='EXACT'),wall=sum(todayRows,'duration_seconds'),workers=todayRows.filter(x=>Number(x.worker_count)>0).length;
  const hero=r?`<div class="hero">
    <div class="hero-main"><div class="hero-label">${r.usage_quality==='EXACT'?'Latest measured turn':'Latest turn'}</div><div class="hero-title">${esc(r.project||U)}</div><div class="hero-meta">${esc(r.worktree||r.model||U)} · ${esc(r.model||U)}</div><div class="badges">${speedBadge(r)} ${statusBadge(r.status)}</div></div>
    <div class="hero-stat"><span>Duration</span><strong>${duration(r.duration_seconds)}</strong><small>${day(r.timestamp)} ${time(r.timestamp)}</small></div>
    <div class="hero-stat"><span>Total tokens</span><strong>${compact(r.orchestra_exact_total_tokens??r.root_exact_total_tokens??r.exact_total_tokens)}</strong><small>${esc(r.usage_quality||U)}</small></div>
    <div class="hero-stat"><span>Cache</span><strong>${pct(r.cache_ratio)}</strong><small>${known(r.worker_count)?r.worker_count+' workers':'workers '+U}</small></div>
  </div>`:`<div class="hero"><div class="hero-main"><div class="hero-title">No turns match this view</div></div></div>`;
  const exactTokens=sum(exact,'exact_total_tokens');
  $('overviewView').innerHTML=hero+
    `<div class="kpis">
      <div class="kpi"><span>Turns today</span><strong>${todayRows.length}</strong></div>
      <div class="kpi"><span>Exact tokens today</span><strong>${compact(exactTokens)}</strong></div>
      <div class="kpi"><span>Wall time today</span><strong>${duration(wall)}</strong></div>
      <div class="kpi"><span>Exact coverage</span><strong>${rows.length?((rows.filter(x=>x.usage_quality==='EXACT').length/rows.length)*100).toFixed(0)+'%':U}</strong></div>
      <div class="kpi"><span>Turns with workers</span><strong>${workers}</strong></div>
    </div>
    <div class="section"><div class="section-head"><h2>Usage</h2><span>${rows.length} turns</span></div>
      <div class="chart-grid">
        <div class="panel"><div class="panel-head"><h3>Exact tokens per measured turn</h3><span id="tokenN"></span></div><div id="tokenChart" class="chart"></div></div>
        <div class="panel"><div class="panel-head"><h3>Duration</h3><span id="durationN"></span></div><div id="durationChart" class="chart"></div></div>
      </div>
    </div>
    <div class="section"><div class="section-head"><h2>Recent turns</h2><span>Click for details</span></div><div class="panel recent" id="recent"></div></div>`;
  barChart('tokenChart',rows.filter(x=>known(x.exact_total_tokens)).slice(0,18).reverse(),'exact_total_tokens',compact);$('tokenN').textContent='N='+rows.filter(x=>known(x.exact_total_tokens)).length;
  lineChart('durationChart',rows.filter(x=>known(x.duration_seconds)).slice(0,30).reverse(),'duration_seconds',duration);$('durationN').textContent='N='+rows.filter(x=>known(x.duration_seconds)).length;
  renderRecent(rows.slice(0,9));
}
function renderRecent(rows){
  const head='<div class="recent-head"><div>Time</div><div>Work</div><div>Model</div><div>Duration</div><div>Tokens</div><div>Workers</div><div>Status</div></div>';
  const body=rows.map(r=>`<div class="recent-row" data-run="${esc(r.run_id)}"><div>${time(r.timestamp)}</div><div><div class="main">${esc(r.project)}</div><div class="sub">${esc(r.worktree)}</div></div><div>${esc(r.model)}</div><div class="num">${duration(r.duration_seconds)}</div><div class="num">${compact(r.orchestra_exact_total_tokens??r.root_exact_total_tokens??r.exact_total_tokens)}</div><div class="num">${known(r.worker_count)?r.worker_count:U}</div><div>${statusBadge(r.status)}</div></div>`).join('');
  $('recent').innerHTML=head+(body||'<div class="empty">No turns</div>');
}
function lineChart(id,rows,key,fmt){
  if(!rows.length){$(id).innerHTML='<div class="empty">No data yet</div>';return}
  const W=760,H=260,L=68,R=18,T=18,B=42,CW=W-L-R,CH=H-T-B,vals=rows.map(r=>Number(r[key])),max=Math.max(...vals,1);
  const x=i=>L+CW*i/Math.max(rows.length-1,1),y=v=>T+CH-(v/max)*CH;
  const grid=[0,.5,1].map(f=>{const yy=T+CH*(1-f);return `<line class="gridline" x1="${L}" y1="${yy}" x2="${W-R}" y2="${yy}"/><text class="label" x="${L-10}" y="${yy+4}" text-anchor="end">${esc(fmt(max*f))}</text>`}).join('');
  const pts=vals.map((v,i)=>x(i)+','+y(v)).join(' ');
  const dots=vals.map((v,i)=>`<circle class="point" cx="${x(i)}" cy="${y(v)}" r="4"><title>${esc(day(rows[i].timestamp)+' '+time(rows[i].timestamp)+' · '+fmt(v))}</title></circle>`).join('');
  $(id).innerHTML=`<svg viewBox="0 0 ${W} ${H}">${grid}<line class="axis" x1="${L}" y1="${T+CH}" x2="${W-R}" y2="${T+CH}"/><polyline class="line" points="${pts}"/>${dots}<text class="label" x="${L}" y="${H-12}">${esc(day(rows[0].timestamp))}</text><text class="label" x="${W-R}" y="${H-12}" text-anchor="end">${esc(day(rows.at(-1).timestamp))}</text></svg>`;
}
function barChart(id,rows,key,fmt){
  if(!rows.length){$(id).innerHTML='<div class="empty">Exact token data will appear here.</div>';return}
  const W=900,H=260,L=70,R=18,T=16,B=42,CW=W-L-R,CH=H-T-B,vals=rows.map(r=>Number(r[key])),max=Math.max(...vals,1),gap=7,bw=Math.max(8,(CW-gap*(rows.length-1))/rows.length);
  const grid=[0,.5,1].map(f=>{const yy=T+CH*(1-f);return `<line class="gridline" x1="${L}" y1="${yy}" x2="${W-R}" y2="${yy}"/><text class="label" x="${L-10}" y="${yy+4}" text-anchor="end">${esc(fmt(max*f))}</text>`}).join('');
  const bars=vals.map((v,i)=>{const h=(v/max)*CH,x=L+i*(bw+gap),y=T+CH-h;return `<rect class="bar" x="${x}" y="${y}" width="${bw}" height="${h}" rx="3"><title>${esc(day(rows[i].timestamp)+' '+time(rows[i].timestamp)+' · '+fmt(v))}</title></rect>`}).join('');
  $(id).innerHTML=`<svg viewBox="0 0 ${W} ${H}">${grid}<line class="axis" x1="${L}" y1="${T+CH}" x2="${W-R}" y2="${T+CH}"/>${bars}<text class="label" x="${L}" y="${H-12}">${esc(day(rows[0].timestamp))}</text><text class="label" x="${W-R}" y="${H-12}" text-anchor="end">${esc(day(rows.at(-1).timestamp))}</text></svg>`;
}
function renderTurns(){
  const all=filtered(),pageSize=18,pages=Math.max(1,Math.ceil(all.length/pageSize));state.page=Math.min(state.page,pages);const start=(state.page-1)*pageSize,rows=all.slice(start,start+pageSize);
  const body=rows.map(r=>`<tr data-run="${esc(r.run_id)}"><td>${day(r.timestamp)} ${time(r.timestamp)}</td><td><div class="main">${esc(r.project)}</div><div class="sub">${esc(r.worktree)}</div></td><td>${esc(r.model)}</td><td>${duration(r.duration_seconds)}</td><td class="num">${compact(r.orchestra_exact_total_tokens??r.root_exact_total_tokens??r.exact_total_tokens)}</td><td class="num">${known(r.worker_count)?r.worker_count:U}</td><td>${statusBadge(r.status)}</td></tr>`).join('');
  $('turnsView').innerHTML=`<div class="section-head"><h2>Turns</h2><span>${all.length} total</span></div><div class="panel table-wrap"><table class="turn-table"><thead><tr><th>Time</th><th>Work</th><th>Model</th><th>Duration</th><th class="num">Tokens</th><th class="num">Workers</th><th>Status</th></tr></thead><tbody>${body||'<tr><td colspan="7">No turns</td></tr>'}</tbody></table><div class="pagination"><span>${all.length?start+1:0}–${Math.min(start+pageSize,all.length)} of ${all.length}</span><div><button data-page="prev" ${state.page<=1?'disabled':''}>Prev</button> <button data-page="next" ${state.page>=pages?'disabled':''}>Next</button></div></div></div>`;
}
function renderOrchestra(){
  const rows=filtered().filter(r=>Number(r.worker_count)>0||r.worker_usage_quality==='EXACT'),r=rows[0]||filtered()[0]||null;
  if(!r){$('orchestraView').innerHTML='<div class="empty">No turns</div>';return}
  const workers=Array.isArray(r.workers)?r.workers:[];
  const rowsHtml=workers.map(w=>`<div class="worker-row"><div>${esc(w.worker_id||U)}</div><div>${esc(w.model||U)}</div><div class="num">${compact(w.total_tokens)}</div><div>${esc(w.usage_quality||U)}</div></div>`).join('');
  $('orchestraView').innerHTML=`<div class="section-head"><h2>Orchestra</h2><span>${rows.length} turns with worker evidence</span></div><div class="orch-layout">
    <div class="panel orch-main"><select id="orchPick" class="turn-picker">${filtered().slice(0,60).map(x=>`<option value="${esc(x.run_id)}" ${x.run_id===r.run_id?'selected':''}>${esc(day(x.timestamp)+' '+time(x.timestamp)+' · '+x.project)}</option>`).join('')}</select>
      <div class="orch-big"><div><span>Duration</span><strong>${duration(r.duration_seconds)}</strong></div><div><span>Root</span><strong>${compact(r.root_exact_total_tokens)}</strong></div><div><span>Workers</span><strong>${compact(r.worker_exact_total_tokens)}</strong></div><div><span>Total</span><strong>${compact(r.orchestra_exact_total_tokens)}</strong></div></div>
      <div class="worker-table"><div class="worker-row head"><div>Worker</div><div>Model</div><div class="num">Tokens</div><div>Quality</div></div>${rowsHtml||'<div class="worker-row"><div>No worker detail recorded</div><div></div><div></div><div></div></div>'}</div>
    </div>
    <div class="panel" style="padding:18px"><div class="hero-label">Selected turn</div><div class="hero-title" style="font-size:20px">${esc(r.project)}</div><div class="hero-meta">${esc(r.model)} · ${duration(r.duration_seconds)}</div><div class="badges">${speedBadge(r)} ${statusBadge(r.status)}</div><div style="margin-top:22px;color:var(--faint);font-size:12px">Worker share</div><div style="font-size:28px;font-weight:760;margin-top:4px">${known(r.worker_exact_total_tokens)&&known(r.orchestra_exact_total_tokens)&&Number(r.orchestra_exact_total_tokens)>0?((100*Number(r.worker_exact_total_tokens)/Number(r.orchestra_exact_total_tokens)).toFixed(0)+'%'):U}</div></div>
  </div>`;
  $('orchPick').onchange=e=>{const found=filtered().find(x=>x.run_id===e.target.value);if(found){state.drawer=found.run_id;openDrawer(found)}};
}
function renderCompare(){
  const rows=filtered().filter(r=>r.speed_certified);
  function cohort(mode){const a=rows.filter(r=>r.speed_mode===mode),dur=a.map(r=>r.duration_seconds).filter(known).map(Number).sort((x,y)=>x-y),tok=a.map(r=>r.exact_total_tokens).filter(known).map(Number).sort((x,y)=>x-y);const med=x=>x.length?x[Math.floor((x.length-1)/2)]:null;return `<div class="panel cohort"><h3>${mode}</h3><div class="n">N=${a.length} certified turns</div><div class="cohort-metrics"><div><span>Median duration</span><strong>${duration(med(dur))}</strong></div><div><span>Median tokens</span><strong>${compact(med(tok))}</strong></div><div><span>Exact N</span><strong>${tok.length}</strong></div></div></div>`}
  $('compareView').innerHTML=`<div class="section-head"><h2>FAST vs STANDARD</h2><span>launcher-certified only</span></div><div class="compare">${cohort('FAST')}${cohort('STANDARD')}</div>`;
}
function openDrawer(r){
  state.drawer=r.run_id;$('drawerBg').classList.add('open');$('drawer').classList.add('open');
  $('drawer').innerHTML=`<div class="drawer-top"><div><h2>${esc(r.project)}</h2><div class="hero-meta">${esc(day(r.timestamp)+' '+time(r.timestamp)+' · '+r.model)}</div></div><button class="drawer-close" data-close>×</button></div>
  <div class="drawer-section"><h3>Summary</h3><div class="detail-grid">
    <div class="detail"><span>Duration</span><strong>${duration(r.duration_seconds)}</strong></div><div class="detail"><span>Status</span><strong>${esc(r.status)}</strong></div>
    <div class="detail"><span>Total tokens</span><strong>${compact(r.orchestra_exact_total_tokens??r.root_exact_total_tokens??r.exact_total_tokens)}</strong></div><div class="detail"><span>Cache</span><strong>${pct(r.cache_ratio)}</strong></div>
    <div class="detail"><span>Workers</span><strong>${known(r.worker_count)?r.worker_count:U}</strong></div><div class="detail"><span>Speed</span><strong>${esc(r.speed_mode||U)}</strong></div>
  </div></div>
  <div class="drawer-section"><h3>Token breakdown</h3><div class="detail-grid">
    <div class="detail"><span>Input</span><strong>${compact(r.input_tokens)}</strong></div><div class="detail"><span>Cached</span><strong>${compact(r.cached_input_tokens)}</strong></div>
    <div class="detail"><span>Fresh input</span><strong>${compact(r.non_cached_input_tokens)}</strong></div><div class="detail"><span>Output</span><strong>${compact(r.output_tokens)}</strong></div>
    <div class="detail"><span>Reasoning</span><strong>${compact(r.reasoning_tokens)}</strong></div><div class="detail"><span>Usage quality</span><strong>${esc(r.usage_quality||U)}</strong></div>
  </div></div>
  <div class="drawer-section"><h3>IDs</h3><div class="detail-grid"><div class="detail"><span>Turn</span><strong>${esc(r.turn_id||U)}</strong></div><div class="detail"><span>Thread</span><strong>${esc(r.thread_id||r.session_id||U)}</strong></div></div></div>`;
}
function closeDrawer(){state.drawer=null;$('drawerBg').classList.remove('open');$('drawer').classList.remove('open')}
function render(){
  document.querySelectorAll('.view').forEach(v=>v.classList.remove('active'));$(state.view+'View').classList.add('active');
  document.querySelectorAll('.nav button').forEach(b=>b.classList.toggle('active',b.dataset.view===state.view));$('pageTitle').textContent=state.view[0].toUpperCase()+state.view.slice(1);
  const rows=filtered(),exact=rows.filter(r=>r.usage_quality==='EXACT').length;$('coverageMini').textContent=rows.length?(exact+'/'+rows.length+' exact turns'):'No turns';
  if(state.view==='overview')renderOverview();else if(state.view==='turns')renderTurns();else if(state.view==='orchestra')renderOrchestra();else renderCompare();
}
let timer=null,busy=false;
async function refresh(){
  if(!LIVE||busy)return;busy=true;$('updated').textContent='Refreshing…';
  try{const r=await fetch('/api/snapshot?ts='+Date.now(),{cache:'no-store'});if(!r.ok)throw new Error('HTTP '+r.status);DATA=await r.json();initOptions();render();$('updated').textContent='Updated '+new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'})}
  catch(e){$('updated').textContent='Refresh failed'}finally{busy=false}
}
function auto(){if(timer)clearInterval(timer);timer=null;if(LIVE&&$('auto').checked)timer=setInterval(refresh,5000)}
document.addEventListener('click',e=>{
  const nav=e.target.closest('[data-view]');if(nav){state.view=nav.dataset.view;render();return}
  const p=e.target.closest('[data-period]');if(p){state.period=p.dataset.period;document.querySelectorAll('[data-period]').forEach(x=>x.classList.toggle('active',x.dataset.period===state.period));state.page=1;render();return}
  const row=e.target.closest('[data-run]');if(row){const r=filtered().find(x=>x.run_id===row.dataset.run);if(r)openDrawer(r);return}
  const pg=e.target.closest('[data-page]');if(pg){state.page+=pg.dataset.page==='next'?1:-1;renderTurns();return}
  if(e.target.closest('[data-close]')||e.target.id==='drawerBg')closeDrawer();
});
$('project').onchange=e=>{state.project=e.target.value;state.page=1;render()};$('model').onchange=e=>{state.model=e.target.value;state.page=1;render()};$('speed').onchange=e=>{state.speed=e.target.value;state.page=1;render()};
$('search').oninput=e=>{state.query=e.target.value;state.page=1;render()};$('exact').onchange=e=>{state.exact=e.target.checked;state.page=1;render()};$('refresh').onclick=refresh;$('auto').onchange=auto;
initOptions();render();auto();if(LIVE)refresh();else{$('auto').checked=false;$('auto').disabled=true;$('refresh').disabled=true;$('liveState').textContent='Static report'}
</script>
</body>
</html>'''
    return template.replace("__PAYLOAD__", payload).replace("__LIVE__", "true" if live else "false")


class _Handler(http.server.BaseHTTPRequestHandler):
    store_root: str | None = None
    cache_path: str | None = None

    def _snapshot(self) -> dict[str, Any]:
        store = core.TelemetryStore(self.store_root)
        cache = Path(self.cache_path) if self.cache_path else None
        return core.load_snapshot(store, cache=cache)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            self._send(200, b"ok\n", "text/plain; charset=utf-8")
            return
        if path == "/api/snapshot":
            try:
                body = json.dumps(self._snapshot(), sort_keys=True, separators=(",", ":")).encode("utf-8")
            except core.DashboardError as exc:
                self._send(503, json.dumps({"error": str(exc)}).encode("utf-8"), "application/json; charset=utf-8")
                return
            self._send(200, body, "application/json; charset=utf-8")
            return
        if path in {"/", "/index.html"}:
            try:
                body = build_html(self._snapshot(), live=True).encode("utf-8")
            except core.DashboardError as exc:
                self._send(503, html.escape(str(exc)).encode("utf-8"), "text/plain; charset=utf-8")
                return
            self._send(200, body, "text/html; charset=utf-8")
            return
        self._send(404, b"not found\n", "text/plain; charset=utf-8")

    def log_message(self, format: str, *args: Any) -> None:
        return


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--store", default=None)
    p.add_argument("--cache", default=None)
    p.add_argument("--no-cache", action="store_true")
    sub = p.add_subparsers(dest="command")
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8766)
    serve.add_argument("--no-browser", action="store_true")
    report = sub.add_parser("report")
    report.add_argument("--output", default="orchestra-dashboard-highlight.html")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command is None:
        args.command = "serve"
        args.host = "127.0.0.1"
        args.port = 8766
        args.no_browser = False
    try:
        store = core.TelemetryStore(args.store)
        cache = None if args.no_cache else core._cache_path(store, args.cache)
        snapshot = core.load_snapshot(store, cache=cache)
        if args.command == "report":
            target = Path(args.output).expanduser()
            if target.resolve() == store.ledger_path.resolve():
                raise core.DashboardError("report must not overwrite ledger.jsonl")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(build_html(snapshot, live=False), encoding="utf-8", newline="\n")
            print(str(target.resolve()))
            return 0
        if args.host != "127.0.0.1":
            raise core.DashboardError("dashboard binds to 127.0.0.1 only")
        handler = type("HighlightDashboardHandler", (_Handler,), {})
        handler.store_root = str(store.root)
        handler.cache_path = str(cache) if cache is not None else None
        with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
            url = f"http://127.0.0.1:{server.server_port}/"
            print(f"Orchestra dashboard: {url}", flush=True)
            if not args.no_browser:
                webbrowser.open(url)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
        return 0
    except (core.DashboardError, OSError) as exc:
        print(f"orchestra-dashboard: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
