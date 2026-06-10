#!/usr/bin/env python3
"""Generate NeuCLIR 2024 nugget coverage matrix demo page."""

import json
from collections import defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).parent / 'data' / 'neuclir'
OUT_FILE = Path(__file__).parent / 'index.html'


def load_data():
    qrel = defaultdict(lambda: defaultdict(dict))
    with open(DATA_DIR / 'neuclir24-test-request.qrel') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) == 4:
                topic, nugget, doc, label = parts
                qrel[topic][nugget][doc] = int(label)

    topics = {}
    with open(DATA_DIR / 'neuclir24-test-request.jsonl') as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                topics[d['request_id']] = d

    docs = {}
    with open(DATA_DIR / 'neuclir24-relevant-docs.jsonl') as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                docs[d['id']] = {
                    'title': d.get('title', 'Untitled'),
                    'text': d.get('text', '')[:1500],
                }

    # nugget_info[tid][nugget_id_str] = {question, answers, cond}
    # cond "OR" = list of acceptable answers; "AND" = single specific answer
    nugget_info = {}
    with open(DATA_DIR / 'neuclir24.nuggets.human.jsonl') as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            tid = str(d['id'])
            info = {}
            for idx, item in enumerate(d['nuggets'], start=1):
                question, answers = item[0], item[1]
                if isinstance(answers, list):
                    info[str(idx)] = {'question': question, 'answers': answers, 'cond': 'OR'}
                else:
                    info[str(idx)] = {'question': question, 'answers': [answers], 'cond': 'AND'}
            nugget_info[tid] = info

    return qrel, topics, docs, nugget_info


def process_data(qrel, topics, docs, nugget_info):
    vis_data = {}
    for tid in sorted(topics.keys()):
        if tid not in qrel:
            continue

        nugget_cov = {n: len(ddocs) for n, ddocs in qrel[tid].items()}
        sorted_nuggets = sorted(nugget_cov, key=lambda n: (-nugget_cov[n], int(n)))

        doc_cov = defaultdict(int)
        for n, ddocs in qrel[tid].items():
            for d in ddocs:
                doc_cov[d] += 1
        sorted_docs = sorted(doc_cov, key=lambda d: (-doc_cov[d], d))

        nidx = {n: i for i, n in enumerate(sorted_nuggets)}
        didx = {d: i for i, d in enumerate(sorted_docs)}

        cells = [
            [nidx[n], didx[d], label]
            for n, ddocs in qrel[tid].items()
            for d, label in ddocs.items()
        ]

        tinfo = nugget_info.get(tid, {})

        vis_data[tid] = {
            'title': topics[tid]['title'],
            'background': topics[tid].get('background', ''),
            'problem_statement': topics[tid].get('problem_statement', ''),
            'nuggets': sorted_nuggets,
            'nugget_cov': nugget_cov,
            'nugget_info': tinfo,
            'docs': sorted_docs,
            'doc_cov': dict(doc_cov),
            'doc_info': {d: docs.get(d, {'title': '?', 'text': ''}) for d in sorted_docs},
            'cells': cells,
        }

    return vis_data


def generate_html(vis_data):
    data_json = json.dumps(vis_data, ensure_ascii=False)

    return '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NeuCLIR 2024 — Nugget Coverage Matrix</title>
<script src="https://cdn.jsdelivr.net/npm/d3@7"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',system-ui,sans-serif;background:#f0f2f5;color:#1e293b;min-height:100vh}

/* Header */
header{background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 100%);color:#fff;padding:18px 28px;display:flex;align-items:center;gap:16px;box-shadow:0 2px 8px rgba(0,0,0,.3)}
header .logo{font-size:1.5rem;font-weight:800;letter-spacing:-0.5px}
header .logo span{color:#60a5fa}
header .subtitle{font-size:.82rem;opacity:.6;margin-top:3px}

/* Main layout */
.main{max-width:1600px;margin:0 auto;padding:20px 24px;display:flex;flex-direction:column;gap:16px}

/* Cards */
.card{background:#fff;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,.08),0 1px 2px rgba(0,0,0,.06);padding:18px 22px}

/* Controls row */
.controls{display:flex;align-items:center;gap:18px;flex-wrap:wrap}
.controls label{font-weight:600;font-size:.85rem;color:#475569}
select{padding:7px 12px;border:1.5px solid #e2e8f0;border-radius:6px;font-size:.88rem;background:#fff;cursor:pointer;color:#1e293b;min-width:280px;outline:none}
select:focus{border-color:#3b82f6}

/* Topic info */
.topic-title{font-size:1.15rem;font-weight:700;color:#0f172a;margin-bottom:12px}
.info-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.info-block strong{display:block;font-size:.7rem;text-transform:uppercase;letter-spacing:.6px;color:#94a3b8;margin-bottom:5px}
.info-block p{font-size:.82rem;color:#475569;line-height:1.55}

/* Stats bar */
.stats{display:flex;gap:12px;flex-wrap:wrap}
.stat{flex:1;min-width:120px;background:linear-gradient(135deg,#eff6ff,#dbeafe);border:1px solid #bfdbfe;border-radius:8px;padding:12px 16px}
.stat-val{font-size:1.5rem;font-weight:800;color:#1d4ed8}
.stat-lbl{font-size:.72rem;color:#3b82f6;text-transform:uppercase;letter-spacing:.5px;margin-top:2px}

/* Matrix section */
.matrix-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;flex-wrap:wrap;gap:10px}
.matrix-header h2{font-size:.95rem;font-weight:700;color:#0f172a}
.matrix-opts{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.matrix-opts .opt-label{font-size:.8rem;color:#64748b;display:flex;align-items:center;gap:6px}
.matrix-opts input[type=range]{width:90px;accent-color:#3b82f6;cursor:pointer}
.matrix-hint{font-size:.78rem;color:#94a3b8;margin-bottom:12px}

.legend{display:flex;align-items:center;gap:8px;font-size:.78rem;color:#64748b}
.legend-sq{width:13px;height:13px;border-radius:2px}

#matrix-wrap{overflow:auto;border:1px solid #e2e8f0;border-radius:6px;background:#fafafa;cursor:crosshair}
#matrix-svg{display:block}

/* Tooltip */
#tooltip{
  position:fixed;pointer-events:none;z-index:9999;
  background:rgba(15,23,42,.96);color:#f1f5f9;
  padding:13px 15px;border-radius:8px;
  font-size:.8rem;line-height:1.55;max-width:480px;
  display:none;box-shadow:0 8px 32px rgba(0,0,0,.4);
  border:1px solid rgba(255,255,255,.08)
}
#tooltip .tt-section{margin-top:10px;padding-top:10px;border-top:1px solid rgba(255,255,255,.12)}
#tooltip .tt-tag{font-size:.68rem;text-transform:uppercase;letter-spacing:.7px;color:#94a3b8;margin-bottom:3px}
#tooltip .tt-title{font-weight:700;font-size:.88rem;color:#e2e8f0;line-height:1.3}
#tooltip .tt-sub{color:#94a3b8;font-size:.77rem;margin-top:3px}
#tooltip .tt-text{color:#cbd5e1;font-size:.76rem;margin-top:6px;line-height:1.45}
#tooltip .tt-id{color:#475569;font-size:.7rem;margin-top:5px;font-family:monospace}
.badge-blue{display:inline-block;background:#1d4ed8;color:#bfdbfe;padding:1px 7px;border-radius:10px;font-size:.72rem;font-weight:600;margin-left:5px}
.badge-or{display:inline-block;background:#065f46;color:#6ee7b7;padding:1px 6px;border-radius:10px;font-size:.68rem;font-weight:700;margin-left:4px}
.badge-and{display:inline-block;background:#7c2d12;color:#fca5a5;padding:1px 6px;border-radius:10px;font-size:.68rem;font-weight:700;margin-left:4px}

/* Axis text */
.y-label{font-size:10px;fill:#475569;cursor:default}
.y-label:hover{fill:#1d4ed8}
.x-label{font-size:9px;fill:#94a3b8}
.axis-title{font-size:10px;fill:#94a3b8;font-weight:600}
</style>
</head>
<body>
<header>
  <div>
    <div class="logo">NeuCLIR<span> 2024</span></div>
    <div class="subtitle">Nugget · Document Coverage Matrix</div>
  </div>
</header>

<div class="main">

  <div class="card controls">
    <label for="topic-sel">Topic</label>
    <select id="topic-sel"></select>
  </div>

  <div class="card" id="topic-info"></div>

  <div class="stats" id="stats"></div>

  <div class="card">
    <div class="matrix-header">
      <h2>Coverage Matrix</h2>
      <div class="matrix-opts">
        <div class="legend">
          <div class="legend-sq" style="background:#3b82f6"></div><span>Covered (label 3)</span>
          <div class="legend-sq" style="background:#f1f5f9;border:1px solid #e2e8f0;margin-left:6px"></div><span>Not covered</span>
        </div>
        <label class="opt-label">
          Cell size&nbsp;
          <input type="range" id="size-slider" min="4" max="28" value="12" step="1">
          <span id="size-val">12</span>px
        </label>
      </div>
    </div>
    <p class="matrix-hint">
      Y-axis: nuggets sorted by coverage (most covered first) &nbsp;·&nbsp;
      X-axis: documents sorted by nuggets covered (most first) &nbsp;·&nbsp;
      Hover any cell for details
    </p>
    <div id="matrix-wrap">
      <svg id="matrix-svg"></svg>
    </div>
  </div>

</div>

<div id="tooltip"></div>

<script>
const DATA = ''' + data_json + ''';

const topicIds = Object.keys(DATA).sort((a,b)=>+a-+b);
let cellSize = 12;

// Populate selector
const sel = document.getElementById('topic-sel');
topicIds.forEach(tid => {
  const o = document.createElement('option');
  o.value = tid;
  o.textContent = `${tid} — ${DATA[tid].title}`;
  sel.appendChild(o);
});

sel.addEventListener('change', () => render(sel.value));

const slider = document.getElementById('size-slider');
const sizeVal = document.getElementById('size-val');
slider.addEventListener('input', () => {
  cellSize = +slider.value;
  sizeVal.textContent = cellSize;
  render(sel.value);
});

function esc(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') }

function render(tid) {
  const d = DATA[tid];

  // Info panel
  document.getElementById('topic-info').innerHTML = `
    <div class="topic-title">Topic ${esc(tid)}: ${esc(d.title)}</div>
    <div class="info-grid">
      <div class="info-block"><strong>Background</strong><p>${esc(d.background)}</p></div>
      <div class="info-block"><strong>Problem Statement</strong><p>${esc(d.problem_statement)}</p></div>
    </div>`;

  // Stats
  const nN = d.nuggets.length, nD = d.docs.length, nC = d.cells.length;
  const density = (nC / (nN * nD) * 100).toFixed(1);
  document.getElementById('stats').innerHTML = `
    <div class="stat"><div class="stat-val">${nN}</div><div class="stat-lbl">Nuggets</div></div>
    <div class="stat"><div class="stat-val">${nD}</div><div class="stat-lbl">Documents</div></div>
    <div class="stat"><div class="stat-val">${nC.toLocaleString()}</div><div class="stat-lbl">Annotated Pairs</div></div>
    <div class="stat"><div class="stat-val">${density}%</div><div class="stat-lbl">Matrix Density</div></div>`;

  renderMatrix(tid);
}

function renderMatrix(tid) {
  const d = DATA[tid];
  const nN = d.nuggets.length, nD = d.docs.length;
  const cs = cellSize;
  const mL = 82, mT = 36, mR = 20, mB = 28;
  const W = nD * cs + mL + mR;
  const H = nN * cs + mT + mB;

  const svg = d3.select('#matrix-svg')
    .attr('width', W).attr('height', H);
  svg.selectAll('*').remove();

  const g = svg.append('g').attr('transform', `translate(${mL},${mT})`);

  // Row/col highlight rects (drawn first, behind cells)
  const rowHL = g.append('rect')
    .attr('fill', 'rgba(59,130,246,.08)').attr('pointer-events','none').attr('display','none')
    .attr('x', 0).attr('width', nD * cs).attr('height', cs);
  const colHL = g.append('rect')
    .attr('fill', 'rgba(59,130,246,.08)').attr('pointer-events','none').attr('display','none')
    .attr('y', 0).attr('height', nN * cs).attr('width', cs);

  // Subtle grid lines every 10
  const gridG = g.append('g').attr('class','grid');
  for (let i = 10; i < nN; i += 10) {
    gridG.append('line').attr('x1',0).attr('x2',nD*cs).attr('y1',i*cs).attr('y2',i*cs)
      .attr('stroke','#e2e8f0').attr('stroke-width',.5);
  }
  for (let i = 10; i < nD; i += 10) {
    gridG.append('line').attr('x1',i*cs).attr('x2',i*cs).attr('y1',0).attr('y2',nN*cs)
      .attr('stroke','#e2e8f0').attr('stroke-width',.5);
  }

  // Cells
  const tt = document.getElementById('tooltip');

  g.selectAll('rect.c')
    .data(d.cells)
    .join('rect').attr('class','c')
    .attr('x', c => c[1]*cs).attr('y', c => c[0]*cs)
    .attr('width', Math.max(1, cs-1)).attr('height', Math.max(1, cs-1))
    .attr('rx', cs >= 8 ? 1.5 : 0)
    .attr('fill', '#3b82f6')
    .on('mousemove', function(event, c) {
      const nugId = d.nuggets[c[0]];
      const docId = d.docs[c[1]];
      const di = d.doc_info[docId] || {title:'?', text:''};
      const nCov = d.nugget_cov[nugId];
      const dCov = d.doc_cov[docId];
      const ni = d.nugget_info && d.nugget_info[nugId];

      rowHL.attr('display',null).attr('y', c[0]*cs);
      colHL.attr('display',null).attr('x', c[1]*cs);
      d3.select(this).attr('fill','#ef4444');

      const condBadge = ni ? `<span class="badge-${ni.cond === 'OR' ? 'or' : 'and'}">${esc(ni.cond)}</span>` : '';
      const answersHtml = ni
        ? `<div class="tt-sub" style="margin-top:4px"><em>Answer${ni.answers.length>1?'s':''}: </em>${esc(ni.answers.slice(0,4).join(' / '))}${ni.answers.length>4?' …':''}</div>`
        : '';
      tt.innerHTML = `
        <div class="tt-tag">Nugget #${esc(nugId)} ${condBadge}<span class="badge-blue" style="margin-left:4px">${nCov} docs</span></div>
        <div class="tt-title">${ni ? esc(ni.question) : 'Nugget #' + esc(nugId)}</div>
        ${answersHtml}
        <div class="tt-sub" style="margin-top:4px">Covered by ${nCov} of ${nD} documents (${(nCov/nD*100).toFixed(0)}%)</div>
        <div class="tt-section">
          <div class="tt-tag">Document</div>
          <div class="tt-title">${esc(di.title)}</div>
          <div class="tt-text">${esc((di.text||'').substring(0,900))}${di.text && di.text.length>900?'…':''}</div>
          <div class="tt-sub" style="margin-top:6px">Covers <strong>${dCov}</strong> nugget${dCov!==1?'s':''} in this topic</div>
          <div class="tt-id">${docId}</div>
        </div>`;
      tt.style.display = 'block';

      const x = event.clientX, y = event.clientY;
      const vw = window.innerWidth, vh = window.innerHeight;
      let left = x + 16, top = y - 12;
      if (left + 340 > vw) left = x - 340 - 8;
      if (top + 320 > vh) top = vh - 324;
      if (top < 4) top = 4;
      tt.style.left = left + 'px';
      tt.style.top = top + 'px';
    })
    .on('mouseleave', function() {
      rowHL.attr('display','none');
      colHL.attr('display','none');
      d3.select(this).attr('fill','#3b82f6');
      tt.style.display = 'none';
    });

  // Y-axis labels
  const yG = svg.append('g').attr('transform', `translate(0,${mT})`);
  const showEvery = cs >= 10 ? 1 : cs >= 6 ? 2 : 5;
  d.nuggets.forEach((nid, i) => {
    if (i % showEvery !== 0) return;
    const y = i * cs + cs / 2;
    const cov = d.nugget_cov[nid];
    const ni = d.nugget_info && d.nugget_info[nid];
    const labelQ = ni ? ni.question.substring(0, 38) + (ni.question.length > 38 ? '…' : '') : nid;
    yG.append('text')
      .attr('class','y-label')
      .attr('x', mL - 5).attr('y', y)
      .attr('text-anchor','end').attr('dominant-baseline','middle')
      .attr('font-size', Math.min(10, cs))
      .text(cs >= 10 ? `#${nid} ${labelQ} (${cov})` : `#${nid} (${cov})`)
      .on('mousemove', (event) => {
        const condBadge = ni ? `<span class="badge-${ni.cond === 'OR' ? 'or' : 'and'}">${esc(ni.cond)}</span>` : '';
        const answersHtml = ni
          ? `<div class="tt-sub" style="margin-top:5px"><em>Answer${ni.answers.length>1?'s':''}: </em>${esc(ni.answers.slice(0,5).join(' / '))}${ni.answers.length>5?' …':''}</div>`
          : '';
        tt.innerHTML = `
          <div class="tt-tag">Nugget #${esc(nid)} ${condBadge}</div>
          <div class="tt-title">${ni ? esc(ni.question) : esc(nid)}</div>
          ${answersHtml}
          <div class="tt-sub" style="margin-top:6px">Position in ranking: #${i+1} of ${nN}</div>
          <div class="tt-sub">Coverage: ${cov} docs (${(cov/nD*100).toFixed(1)}%)</div>`;
        tt.style.display = 'block';
        tt.style.left = (event.clientX + 12) + 'px';
        tt.style.top = (event.clientY - 8) + 'px';
      })
      .on('mouseleave', () => { tt.style.display = 'none'; });
  });

  // Y-axis title
  svg.append('text').attr('class','axis-title')
    .attr('transform', `translate(10,${mT + nN*cs/2}) rotate(-90)`)
    .attr('text-anchor','middle')
    .text('Nugget ID (# docs covered)');

  // X-axis: show index every ~20 cols
  const xG = svg.append('g').attr('transform', `translate(${mL},${mT})`);
  const xStep = Math.max(5, Math.ceil(30 / cs) * 5);
  for (let i = 0; i < nD; i += xStep) {
    xG.append('text').attr('class','x-label')
      .attr('x', i*cs + cs/2).attr('y', -4)
      .attr('text-anchor','middle')
      .text(i + 1);
  }

  // X-axis title
  svg.append('text').attr('class','axis-title')
    .attr('x', mL + nD*cs/2).attr('y', H - 4)
    .attr('text-anchor','middle')
    .text(`Documents (${nD} total, sorted by nugget coverage ↓)`);
}

// Initial render
render(topicIds[0]);
</script>
</body>
</html>
'''


if __name__ == '__main__':
    print('Loading data...')
    qrel, topics, docs, nugget_info = load_data()
    print('Processing...')
    vis_data = process_data(qrel, topics, docs, nugget_info)
    stats = {tid: (len(v['nuggets']), len(v['docs']), len(v['cells'])) for tid, v in vis_data.items()}
    for tid, (nn, nd, nc) in stats.items():
        print(f'  Topic {tid}: {nn} nuggets × {nd} docs = {nc} pairs')
    html = generate_html(vis_data)
    OUT_FILE.write_text(html, encoding='utf-8')
    size_kb = len(html.encode()) / 1024
    print(f'\nWrote {OUT_FILE}  ({size_kb:.0f} KB)')
