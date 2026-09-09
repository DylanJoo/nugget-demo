#!/usr/bin/env python3
"""Generate NeuCLIR 2024 nugget coverage matrix demo page."""

import json
from collections import defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).parent / 'data' / 'neuclir'
OUT_FILE = Path(__file__).parent / 'index.html'
DOCS_FILE = Path(__file__).parent / 'docs.json'
CLAIMS_FILE = Path(__file__).parent / 'claims.json'

# Claim-level comparison: fixed run pair + depth (see README for why these
# were picked and how the claim/attribution data was produced).
CLAIM_RUN_SPECS = [
    ('bm25', DATA_DIR / 'runs.neuclir2024.bm25.test.txt'),
    ('lancer-top100', DATA_DIR / 'runs.neuclir2024.cover.lancer_expr-top100.test.txt'),
]
CLAIM_DEPTH = 20


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
                    'text': d.get('text', '')[:3000],
                }

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


RUN_FILES = [
    DATA_DIR / 'runs.neuclir2024.bm25.test.txt',
    DATA_DIR / 'runs.neuclir2024.lsr-milco.test.txt',
    DATA_DIR / 'runs.neuclir2024.cover.test.txt',
    DATA_DIR / 'runs.neuclir2024.cover.lancer_expr-top100.test.txt',
    DATA_DIR / 'runs.neuclir2024.cover.lancer_expr-top200.test.txt',
]


def load_run_data():
    """Load all run files and per-doc nugget ratings."""
    # all_runs: {run_name: {tid: [(docid, rank, score)]}}
    all_runs = {}
    for run_file in RUN_FILES:
        run_entries = defaultdict(list)
        with open(run_file) as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 6:
                    run_entries[parts[0]].append((parts[2], int(parts[3]), float(parts[4]), parts[5]))
        all_runs[run_file.stem] = run_entries

    ratings = defaultdict(dict)  # {tid: {docid: rating_array}}
    with open(DATA_DIR / 'neuclir24.ratings.human.jsonl') as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                ratings[str(d['id'])][d['docid']] = d['rating']

    return all_runs, ratings


def load_claim_data():
    """Load decomposed-claim text and the claim<->nugget attribution produced
    for the docs that appear in CLAIM_RUN_SPECS' top-CLAIM_DEPTH lists.

    claims_by_doc: {docid: {'title':..., 'claims': [claim_text, ...]}}
    attribution:   {topic_id: {docid: {nugget_id: [claim_idx, ...]}}}
    """
    claims_file = DATA_DIR / 'neuclir24.claims.byid.json'
    attribution_file = DATA_DIR / 'neuclir24.claim_attribution.json'
    claims_by_doc = json.loads(claims_file.read_text()) if claims_file.exists() else {}
    attribution = json.loads(attribution_file.read_text()) if attribution_file.exists() else {}
    return claims_by_doc, attribution


def build_claim_runs(tid, sorted_nuggets, nidx, ratings_for_tid, claims_by_doc, attribution, claim_run_topk):
    """Build the claim-granularity comparison data for one topic.

    Each run's ranked doc list is flattened into one ordered sequence of
    claim columns (doc rank order, then claim order within a doc). A cell
    [nugget_idx, col] marks that column's claim as stating that nugget,
    using the doc-level human rating to know WHICH nuggets a doc covers and
    the claim attribution to know WHICH claim(s) state each one.
    """
    topic_attr = attribution.get(tid, {})
    topic_runs = {}
    for run_name, _ in CLAIM_RUN_SPECS:
        doc_blocks = []
        cells = []
        col = 0
        for rank, docid, score in claim_run_topk[run_name].get(tid, []):
            doc_info = claims_by_doc.get(docid)
            claims = doc_info['claims'] if doc_info else []
            title = doc_info['title'] if doc_info else ''
            rated = docid in ratings_for_tid
            doc_attr = topic_attr.get(docid, {})
            # invert {nugget_id: [claim_idx,...]} -> {claim_idx: [nugget_idx,...]}
            claim_to_nuggets = defaultdict(list)
            for nid, claim_idxs in doc_attr.items():
                if nid not in nidx:
                    continue
                for ci in claim_idxs:
                    claim_to_nuggets[ci].append(nidx[nid])

            start_col = col
            for ci in range(len(claims)):
                for nix in claim_to_nuggets.get(ci, []):
                    cells.append([nix, col])
                col += 1

            doc_blocks.append({
                'docid': docid,
                'title': title,
                'rank': rank,
                'score': round(score, 6),
                'rated': rated,
                'start': start_col,
                'end': col,
                'n_claims': len(claims),
            })
        topic_runs[run_name] = {'doc_blocks': doc_blocks, 'cells': cells, 'n_cols': col}
    return topic_runs


def _load_claim_run_topk():
    claim_run_topk = {}
    for run_name, path in CLAIM_RUN_SPECS:
        by_topic = defaultdict(list)
        with open(path) as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 6:
                    by_topic[parts[0]].append((int(parts[3]), parts[2], float(parts[4])))
        topk = {}
        for tid, lst in by_topic.items():
            lst.sort(key=lambda x: x[0])
            topk[tid] = lst[:CLAIM_DEPTH]
        claim_run_topk[run_name] = topk
    return claim_run_topk


def _build_run_entries(run_entries_for_tid, sorted_nuggets, ratings_for_tid):
    run_list = sorted(run_entries_for_tid, key=lambda x: x[1])
    run_docs_list = [docid for docid, _, _, _ in run_list]
    run_scores_list = [round(score, 6) for _, _, score, _ in run_list]
    run_rated_list = [docid in ratings_for_tid for docid in run_docs_list]
    run_cov_list = []
    run_cells_list = []
    for i, docid in enumerate(run_docs_list):
        if docid in ratings_for_tid:
            rating_arr = ratings_for_tid[docid]
            cov = 0
            for j, nid in enumerate(sorted_nuggets):
                nidx_0 = int(nid) - 1
                if nidx_0 < len(rating_arr) and rating_arr[nidx_0] == 3:
                    run_cells_list.append([j, i, 3])
                    cov += 1
            run_cov_list.append(cov)
        else:
            run_cov_list.append(-1)
    return {
        'docs': run_docs_list,
        'scores': run_scores_list,
        'rated': run_rated_list,
        'cov': run_cov_list,
        'cells': run_cells_list,
    }


def process_data(qrel, topics, docs, nugget_info, all_runs, ratings, claims_by_doc=None, attribution=None):
    claims_by_doc = claims_by_doc or {}
    attribution = attribution or {}
    claim_run_topk = _load_claim_run_topk()

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

        runs_data = {}
        for run_name, run_by_tid in all_runs.items():
            entries = run_by_tid.get(tid, [])
            runs_data[run_name] = _build_run_entries(entries, sorted_nuggets, ratings.get(tid, {}))

        claim_runs = build_claim_runs(
            tid, sorted_nuggets, nidx, ratings.get(tid, {}), claims_by_doc, attribution, claim_run_topk
        )

        vis_data[tid] = {
            'title': topics[tid]['title'],
            'background': topics[tid].get('background', ''),
            'problem_statement': topics[tid].get('problem_statement', ''),
            'nuggets': sorted_nuggets,
            'nugget_cov': nugget_cov,
            'nugget_info': tinfo,
            'docs': sorted_docs,
            'doc_cov': dict(doc_cov),
            'cells': cells,
            'runs': runs_data,
            'claim_runs': claim_runs,
        }

    return vis_data


def generate_html(vis_data, run_names=None):
    data_json = json.dumps(vis_data, ensure_ascii=False)
    run_names = run_names or []
    run_names_json = json.dumps(run_names)
    claim_run_names_json = json.dumps([name for name, _ in CLAIM_RUN_SPECS])

    return '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NeuCLIR 2024 — Nugget Coverage Matrix</title>
<script src="https://cdn.jsdelivr.net/npm/d3@7"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:\'Segoe UI\',system-ui,sans-serif;background:#f0f2f5;color:#1e293b;min-height:100vh}

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
select{padding:7px 12px;border:1.5px solid #e2e8f0;border-radius:6px;font-size:.88rem;background:#fff;cursor:pointer;color:#1e293b;outline:none}
select:focus{border-color:#3b82f6}
#topic-sel{min-width:280px}

/* Mode toggle */
.mode-toggle{display:flex;border:1.5px solid #e2e8f0;border-radius:7px;overflow:hidden}
.mode-btn{padding:6px 14px;font-size:.82rem;font-weight:600;cursor:pointer;border:none;background:#fff;color:#64748b;transition:background .15s,color .15s}
.mode-btn.active{background:#1d4ed8;color:#fff}
.mode-btn:not(.active):hover{background:#eff6ff;color:#1d4ed8}

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

.legend{display:flex;align-items:center;gap:8px;font-size:.78rem;color:#64748b;flex-wrap:wrap}
.legend-sq{width:13px;height:13px;border-radius:2px;flex-shrink:0}

#matrix-wrap{overflow:auto;border:1px solid #e2e8f0;border-radius:6px;background:#fafafa;cursor:crosshair}
#matrix-svg{display:block}

/* Tooltip */
#tooltip{
  position:fixed;pointer-events:none;z-index:9999;
  background:rgba(15,23,42,.96);color:#f1f5f9;
  padding:13px 15px;border-radius:8px;
  font-size:.8rem;line-height:1.55;max-width:480px;max-height:80vh;overflow-y:auto;
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
.badge-grey{display:inline-block;background:#475569;color:#cbd5e1;padding:1px 6px;border-radius:10px;font-size:.68rem;font-weight:700;margin-left:4px}
ul.tt-answers{margin:6px 0 2px 14px;padding:0;list-style:disc}
ul.tt-answers li{color:#a5f3d0;font-size:.75rem;line-height:1.5;margin-bottom:1px}

/* Axis text */
.y-label{font-size:10px;cursor:default}
.y-label:hover{fill:#1d4ed8}
.x-label{font-size:9px;fill:#94a3b8}
.axis-title{font-size:10px;fill:#94a3b8;font-weight:600}

/* Claims comparison view */
#claims-summary{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:16px}
.cmp-card{flex:1;min-width:240px;border-radius:8px;padding:12px 16px;border:1px solid #e2e8f0}
.cmp-card.winner{border-color:#3b82f6;background:linear-gradient(135deg,#eff6ff,#dbeafe)}
.cmp-name{font-weight:700;font-size:.88rem;color:#0f172a;margin-bottom:6px;display:flex;align-items:center;gap:6px}
.cmp-crown{font-size:.7rem;background:#1d4ed8;color:#fff;padding:1px 7px;border-radius:9px;font-weight:700}
.cmp-row{display:flex;justify-content:space-between;font-size:.78rem;color:#475569;padding:2px 0}
.cmp-row b{color:#0f172a}
.claim-run-block{margin-bottom:18px}
.claim-run-title{font-size:.82rem;font-weight:700;color:#0f172a;margin-bottom:6px}
.claim-matrix-wrap{overflow-x:auto;border:1px solid #e2e8f0;border-radius:6px;background:#fafafa;cursor:crosshair}
.doc-hdr-label{font-size:8px;fill:#64748b;cursor:default}
.doc-hdr-label:hover{fill:#1d4ed8;font-weight:700}
.doc-sep{stroke:#94a3b8;stroke-width:1}
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
    <div class="mode-toggle">
      <button id="mode-rel" class="mode-btn active" onclick="setMode(\'rel\')">Relevant Docs</button>
      <button id="mode-run" class="mode-btn" onclick="setMode(\'run\')">Run</button>
      <button id="mode-claims" class="mode-btn" onclick="setMode(\'claims\')">Claims (BM25 vs Lancer)</button>
    </div>
    <label class="opt-label" id="run-ctrl" style="display:none">
      System&nbsp;
      <select id="run-sel" onchange="render(document.getElementById(\'topic-sel\').value)"></select>
    </label>
    <label class="opt-label" id="topk-ctrl" style="display:none">
      Top-K&nbsp;
      <select id="topk-sel" onchange="render(document.getElementById(\'topic-sel\').value)">
        <option value="20">20</option>
        <option value="50">50</option>
        <option value="100" selected>100</option>
        <option value="200">200</option>
        <option value="500">500</option>
        <option value="1000">1000</option>
      </select>
    </label>
  </div>

  <div class="card" id="topic-info"></div>

  <div class="stats" id="stats"></div>

  <div class="card" id="matrix-card">
    <div class="matrix-header">
      <h2>Coverage Matrix</h2>
      <div class="matrix-opts">
        <div class="legend" id="legend">
          <div class="legend-sq" style="background:#3b82f6"></div><span>Covered</span>
          <div class="legend-sq" style="background:#f1f5f9;border:1px solid #e2e8f0;margin-left:6px"></div><span>Not covered</span>
        </div>
        <label class="opt-label">
          Cell size&nbsp;
          <input type="range" id="size-slider" min="4" max="28" value="12" step="1">
          <span id="size-val">12</span>px
        </label>
      </div>
    </div>
    <p class="matrix-hint" id="matrix-hint">
      Y-axis: nuggets sorted by coverage (most covered first) &nbsp;·&nbsp;
      X-axis: documents sorted by nuggets covered (most first) &nbsp;·&nbsp;
      Hover any cell for details
    </p>
    <div id="matrix-wrap">
      <svg id="matrix-svg"></svg>
    </div>
  </div>

  <div class="card" id="claims-card" style="display:none">
    <div class="matrix-header">
      <h2>Claim-level Coverage &amp; Redundancy — top-''' + str(CLAIM_DEPTH) + ''' docs per run</h2>
      <div class="matrix-opts">
        <div class="legend" id="claims-legend">
          <div class="legend-sq" style="background:#3b82f6"></div><span>Nugget-stating claim</span>
          <div class="legend-sq" style="background:#bfdbfe"></div><span>Redundant (nugget already seen)</span>
          <div class="legend-sq" style="background:#f1f5f9;border:1px solid #e2e8f0"></div><span>Other claim</span>
          <div class="legend-sq" style="background:#e8ecf0"></div><span>Unrated doc</span>
        </div>
        <label class="opt-label">
          Claim width&nbsp;
          <input type="range" id="claim-size-slider" min="3" max="16" value="6" step="1">
          <span id="claim-size-val">6</span>px
        </label>
      </div>
    </div>
    <p class="matrix-hint">
      Each thin column is one decomposed claim, grouped by source document (rank order, boundary = doc edge) &nbsp;·&nbsp;
      Row = nugget &nbsp;·&nbsp; A claim cell lightens once that nugget was already stated by an earlier claim in the same run &nbsp;·&nbsp;
      Hover a claim or a doc header for details
    </p>
    <div id="claims-summary"></div>
    <div id="claims-matrices"></div>
  </div>

</div>

<div id="tooltip"></div>

<script>
const DATA = ''' + data_json + ''';
const RUN_NAMES = ''' + run_names_json + ''';
const CLAIM_RUN_NAMES = ''' + claim_run_names_json + ''';

const topicIds = Object.keys(DATA).sort((a,b)=>+a-+b);
let cellSize = 12;
let claimCellSize = 6;
let viewMode = 'rel';
let docsCache = null;
let claimsCache = null;

// Populate run selector
const runSel = document.getElementById('run-sel');
RUN_NAMES.forEach(name => {
  const o = document.createElement('option');
  o.value = name;
  o.textContent = name;
  runSel.appendChild(o);
});
runSel.addEventListener('change', () => render(sel.value));

// Load docs.json in the background for tooltip text
fetch('docs.json').then(r => r.json()).then(d => { docsCache = d; }).catch(() => {});
fetch('claims.json').then(r => r.json()).then(d => { claimsCache = d; }).catch(() => {});

function getDoc(docId) {
  return (docsCache && docsCache[docId]) || {title: docId, text: ''};
}

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

const claimSlider = document.getElementById('claim-size-slider');
const claimSizeVal = document.getElementById('claim-size-val');
claimSlider.addEventListener('input', () => {
  claimCellSize = +claimSlider.value;
  claimSizeVal.textContent = claimCellSize;
  if (viewMode === 'claims') render(sel.value);
});

function setMode(mode) {
  viewMode = mode;
  document.getElementById('mode-rel').classList.toggle('active', mode === 'rel');
  document.getElementById('mode-run').classList.toggle('active', mode === 'run');
  document.getElementById('mode-claims').classList.toggle('active', mode === 'claims');
  const runVisible = mode === 'run' ? '' : 'none';
  document.getElementById('run-ctrl').style.display = runVisible;
  document.getElementById('topk-ctrl').style.display = runVisible;
  document.getElementById('stats').style.display = mode === 'claims' ? 'none' : '';
  document.getElementById('matrix-card').style.display = mode === 'claims' ? 'none' : '';
  document.getElementById('claims-card').style.display = mode === 'claims' ? '' : 'none';
  updateLegend();
  render(sel.value);
}

function updateLegend() {
  const el = document.getElementById('legend');
  const base = `
    <div class="legend-sq" style="background:#3b82f6"></div><span>Covered</span>
    <div class="legend-sq" style="background:#f1f5f9;border:1px solid #e2e8f0;margin-left:6px"></div><span>Not covered</span>`;
  if (viewMode === 'rel') {
    el.innerHTML = base;
  } else {
    el.innerHTML = base + `
      <div class="legend-sq" style="background:#e2e8f0;margin-left:6px"></div><span>Unjudged</span>`;
  }
}

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

  if (viewMode === 'claims') {
    renderClaimsView(tid);
    return;
  }

  // Stats
  const nN = d.nuggets.length;
  if (viewMode === 'rel') {
    const nD = d.docs.length, nC = d.cells.length;
    const density = (nC / (nN * nD) * 100).toFixed(1);
    document.getElementById('stats').innerHTML = `
      <div class="stat"><div class="stat-val">${nN}</div><div class="stat-lbl">Nuggets</div></div>
      <div class="stat"><div class="stat-val">${nD}</div><div class="stat-lbl">Relevant Docs</div></div>
      <div class="stat"><div class="stat-val">${nC.toLocaleString()}</div><div class="stat-lbl">Annotated Pairs</div></div>
      <div class="stat"><div class="stat-val">${density}%</div><div class="stat-lbl">Matrix Density</div></div>`;
  } else {
    const topK = +document.getElementById('topk-sel').value;
    const rn = document.getElementById('run-sel').value;
    const rd = d.runs[rn] || {docs:[], rated:[], cells:[]};
    const totalRun = rd.docs.length;
    const judgedInTopK = rd.rated.slice(0, topK).filter(Boolean).length;
    const topKCells = rd.cells.filter(c => c[1] < topK);
    const coveredCells = topKCells.length;
    const coveredNuggets = new Set(topKCells.map(c => c[0])).size;
    document.getElementById('stats').innerHTML = `
      <div class="stat"><div class="stat-val">${nN}</div><div class="stat-lbl">Nuggets</div></div>
      <div class="stat"><div class="stat-val">${coveredNuggets} <span style="font-size:.95rem;font-weight:600;color:#3b82f6">/ ${nN}</span></div><div class="stat-lbl">Nuggets Covered</div></div>
      <div class="stat"><div class="stat-val">${Math.min(topK, totalRun)}</div><div class="stat-lbl">Run Docs (top-${topK})</div></div>
      <div class="stat"><div class="stat-val">${judgedInTopK}</div><div class="stat-lbl">Judged in Top-${topK}</div></div>
      <div class="stat"><div class="stat-val">${coveredCells.toLocaleString()}</div><div class="stat-lbl">Covered Pairs</div></div>`;
  }

  // Hint
  const hint = document.getElementById('matrix-hint');
  if (viewMode === 'rel') {
    hint.textContent = 'Y-axis: nuggets sorted by coverage (most covered first) · X-axis: documents sorted by nuggets covered (most first) · Hover any cell for details';
  } else {
    const topK = +document.getElementById('topk-sel').value;
    const rn = document.getElementById('run-sel').value;
    hint.textContent = `System: ${rn} · Y-axis: nuggets (sorted by relevant-doc coverage) · X-axis: top-${topK} run documents in retrieval rank order · Grey columns = unjudged`;
  }

  renderMatrix(tid);
}

function renderMatrix(tid) {
  const d = DATA[tid];
  const nN = d.nuggets.length;
  const cs = cellSize;
  const mL = 82, mT = 36, mR = 20, mB = 28;
  const tt = document.getElementById('tooltip');

  const isRun = viewMode === 'run';
  const selectedRun = document.getElementById('run-sel').value;
  const rd = (isRun && d.runs[selectedRun]) ? d.runs[selectedRun] : {docs:[],scores:[],rated:[],cov:[],cells:[]};
  const topK = isRun ? Math.min(+document.getElementById('topk-sel').value, rd.docs.length) : 0;

  const activeDocs = isRun ? rd.docs.slice(0, topK) : d.docs;
  const nD = activeDocs.length;

  const W = nD * cs + mL + mR;
  const H = nN * cs + mT + mB;

  const svg = d3.select('#matrix-svg').attr('width', W).attr('height', H);
  svg.selectAll('*').remove();

  const g = svg.append('g').attr('transform', `translate(${mL},${mT})`);

  // Row/col highlight rects
  const rowHL = g.append('rect')
    .attr('fill', 'rgba(59,130,246,.08)').attr('pointer-events','none').attr('display','none')
    .attr('x', 0).attr('width', nD * cs).attr('height', cs);
  const colHL = g.append('rect')
    .attr('fill', 'rgba(59,130,246,.08)').attr('pointer-events','none').attr('display','none')
    .attr('y', 0).attr('height', nN * cs).attr('width', cs);

  // Grid lines every 10
  const gridG = g.append('g').attr('class','grid');
  for (let i = 10; i < nN; i += 10)
    gridG.append('line').attr('x1',0).attr('x2',nD*cs).attr('y1',i*cs).attr('y2',i*cs)
      .attr('stroke','#e2e8f0').attr('stroke-width',.5);
  for (let i = 10; i < nD; i += 10)
    gridG.append('line').attr('x1',i*cs).attr('x2',i*cs).attr('y1',0).attr('y2',nN*cs)
      .attr('stroke','#e2e8f0').attr('stroke-width',.5);

  // For run mode: grey background for unjudged columns
  if (isRun) {
    for (let i = 0; i < topK; i++) {
      if (!rd.rated[i]) {
        g.append('rect')
          .attr('x', i * cs).attr('y', 0)
          .attr('width', cs).attr('height', nN * cs)
          .attr('fill', '#e8ecf0').attr('pointer-events', 'none');
      }
    }
  }

  // Cells
  const activeCells = isRun
    ? rd.cells.filter(c => c[1] < topK)
    : d.cells;

  // For each nugget, the earliest doc index (column) where it appears
  const firstOccurrence = {};
  activeCells.forEach(c => {
    if (!(c[0] in firstOccurrence) || c[1] < firstOccurrence[c[0]]) {
      firstOccurrence[c[0]] = c[1];
    }
  });

  function showTooltip(event, nugIdx, docIdx, label) {
    const nugId = d.nuggets[nugIdx];
    const docId = activeDocs[docIdx];
    const nCov = d.nugget_cov[nugId];
    const ni = d.nugget_info && d.nugget_info[nugId];

    const condBadge = ni ? `<span class="badge-${ni.cond === 'OR' ? 'or' : 'and'}">${esc(ni.cond)}</span>` : '';
    const answersHtml = ni
      ? `<ul class="tt-answers">${ni.answers.map(a => `<li>${esc(a)}</li>`).join('')}</ul>`
      : '';

    const di = getDoc(docId);

    let docSection = '';
    if (isRun) {
      const rank = docIdx + 1;
      const score = rd.scores[docIdx] !== undefined ? rd.scores[docIdx].toFixed(4) : '—';
      const isJudged = rd.rated[docIdx];
      const cov = rd.cov[docIdx];
      const covText = isJudged ? `Covers <strong>${cov}</strong> nugget${cov!==1?'s':''} (judged)` : '<span class="badge-grey">UNJUDGED</span>';
      docSection = `
        <div class="tt-section">
          <div class="tt-tag">Run Doc — Rank #${rank} &nbsp;·&nbsp; Score: ${score}</div>
          <div class="tt-title">${di.title ? esc(di.title) : esc(docId)}</div>
          ${di.text ? `<div class="tt-text">${esc(di.text.substring(0,1500))}${di.text.length>1500?'…':''}</div>` : '<div class="tt-sub" style="margin-top:4px">No text available</div>'}
          <div class="tt-sub" style="margin-top:6px">${covText}</div>
          <div class="tt-id">${docId}</div>
        </div>`;
    } else {
      const dCov = d.doc_cov[docId];
      docSection = `
        <div class="tt-section">
          <div class="tt-tag">Document</div>
          <div class="tt-title">${di.title ? esc(di.title) : esc(docId)}</div>
          ${di.text ? `<div class="tt-text">${esc(di.text.substring(0,2000))}${di.text.length>2000?'…':''}</div>` : ''}
          <div class="tt-sub" style="margin-top:6px">Covers <strong>${dCov}</strong> nugget${dCov!==1?'s':''} in this topic</div>
          <div class="tt-id">${docId}</div>
        </div>`;
    }

    tt.innerHTML = `
      <div class="tt-tag">Nugget #${esc(nugId)} ${condBadge}<span class="badge-blue" style="margin-left:4px">${nCov} docs</span></div>
      <div class="tt-title">${ni ? esc(ni.question) : 'Nugget #' + esc(nugId)}</div>
      ${answersHtml}
      <div class="tt-sub" style="margin-top:4px">Covered by ${nCov} of ${d.docs.length} relevant docs (${(nCov/d.docs.length*100).toFixed(0)}%)</div>
      ${docSection}`;
    tt.style.display = 'block';

    const x = event.clientX, y = event.clientY;
    const vw = window.innerWidth, vh = window.innerHeight;
    let left = x + 16, top = y - 12;
    if (left + 480 > vw) left = x - 488;
    if (top < 4) top = 4;
    const ttH = tt.scrollHeight;
    if (top + ttH > vh - 8) top = Math.max(4, vh - ttH - 8);
    tt.style.left = left + 'px';
    tt.style.top = top + 'px';
  }

  function cellFill(nugIdx, docIdx, hover) {
    const isRedundant = docIdx > firstOccurrence[nugIdx];
    if (hover) return isRedundant ? '#60a5fa' : '#1d4ed8';
    return isRedundant ? '#bfdbfe' : '#3b82f6';
  }

  g.selectAll('rect.c')
    .data(activeCells)
    .join('rect').attr('class','c')
    .attr('x', c => c[1]*cs).attr('y', c => c[0]*cs)
    .attr('width', Math.max(1, cs-1)).attr('height', Math.max(1, cs-1))
    .attr('rx', cs >= 8 ? 1.5 : 0)
    .attr('fill', c => cellFill(c[0], c[1], false))
    .on('mousemove', function(event, c) {
      rowHL.attr('display',null).attr('y', c[0]*cs);
      colHL.attr('display',null).attr('x', c[1]*cs);
      d3.select(this).attr('fill', cellFill(c[0], c[1], true));
      showTooltip(event, c[0], c[1], c[2]);
    })
    .on('mouseleave', function(event, c) {
      rowHL.attr('display','none');
      colHL.attr('display','none');
      d3.select(this).attr('fill', cellFill(c[0], c[1], false));
      tt.style.display = 'none';
    });

  // One full-height transparent rect per unjudged run column for hover
  if (isRun) {
    const unjudgedCols = [];
    for (let i = 0; i < topK; i++) { if (!rd.rated[i]) unjudgedCols.push(i); }
    g.selectAll('rect.u')
      .data(unjudgedCols)
      .join('rect').attr('class','u')
      .attr('x', i => i*cs).attr('y', 0)
      .attr('width', Math.max(1, cs-1)).attr('height', nN * cs)
      .attr('fill', 'transparent')
      .on('mousemove', function(event, i) {
        colHL.attr('display',null).attr('x', i*cs);
        const docId = rd.docs[i];
        const rank = i + 1;
        const score = rd.scores[i] !== undefined ? rd.scores[i].toFixed(4) : '—';
        const di = getDoc(docId);
        tt.innerHTML = `
          <div class="tt-tag">Run Doc — Rank #${rank} &nbsp;·&nbsp; Score: ${score}</div>
          <div class="tt-title">${di.title ? esc(di.title) : esc(docId)}</div>
          ${di.text ? `<div class="tt-text">${esc(di.text.substring(0,1500))}${di.text.length>1500?'…':''}</div>` : '<div class="tt-sub" style="margin-top:4px">No text available</div>'}
          <div class="tt-sub" style="margin-top:6px"><span class="badge-grey">UNJUDGED</span></div>
          <div class="tt-id">${docId}</div>`;
        tt.style.display = 'block';
        const vw = window.innerWidth, vh = window.innerHeight;
        let left = event.clientX + 16, top = event.clientY - 12;
        if (left + 480 > vw) left = event.clientX - 488;
        if (top < 4) top = 4;
        const ttH = tt.scrollHeight;
        if (top + ttH > vh - 8) top = Math.max(4, vh - ttH - 8);
        tt.style.left = left + 'px'; tt.style.top = top + 'px';
      })
      .on('mouseleave', function() {
        colHL.attr('display','none');
        tt.style.display = 'none';
      });
  }

  // Build set of nugget indices covered by run docs (for y-label coloring)
  const coveredNuggetSet = new Set();
  if (isRun) {
    rd.cells.filter(c => c[1] < topK).forEach(c => coveredNuggetSet.add(c[0]));
  }

  // Y-axis labels
  const yG = svg.append('g').attr('transform', `translate(0,${mT})`);
  const showEvery = cs >= 10 ? 1 : cs >= 6 ? 2 : 5;
  d.nuggets.forEach((nid, i) => {
    if (i % showEvery !== 0) return;
    const y = i * cs + cs / 2;
    const cov = d.nugget_cov[nid];
    const ni = d.nugget_info && d.nugget_info[nid];
    let yFill;
    if (isRun && !coveredNuggetSet.has(i)) {
      yFill = '#d1d5db';
    } else if (ni && ni.cond === 'OR') {
      yFill = '#059669';
    } else if (ni && ni.cond === 'AND') {
      yFill = '#dc2626';
    } else {
      yFill = '#475569';
    }
    yG.append('text')
      .attr('class','y-label')
      .attr('fill', yFill)
      .attr('x', mL - 5).attr('y', y)
      .attr('text-anchor','end').attr('dominant-baseline','middle')
      .attr('font-size', Math.min(10, cs))
      .text(`#${nid} (${cov})`)
      .on('mousemove', (event) => {
        const condBadge = ni ? `<span class="badge-${ni.cond === 'OR' ? 'or' : 'and'}">${esc(ni.cond)}</span>` : '';
        const answersHtml = ni
          ? `<ul class="tt-answers">${ni.answers.map(a => `<li>${esc(a)}</li>`).join('')}</ul>`
          : '';
        tt.innerHTML = `
          <div class="tt-tag">Nugget #${esc(nid)} ${condBadge}</div>
          <div class="tt-title">${ni ? esc(ni.question) : esc(nid)}</div>
          ${answersHtml}
          <div class="tt-sub" style="margin-top:6px">Position in ranking: #${i+1} of ${nN}</div>
          <div class="tt-sub">Coverage: ${cov} docs (${(cov/d.docs.length*100).toFixed(1)}%)</div>`;
        tt.style.display = 'block';
        const vw = window.innerWidth, vh = window.innerHeight;
        let left = event.clientX + 12, top = event.clientY - 8;
        if (left + 480 > vw) left = event.clientX - 488;
        if (top < 4) top = 4;
        const ttH = tt.scrollHeight;
        if (top + ttH > vh - 8) top = Math.max(4, vh - ttH - 8);
        tt.style.left = left + 'px';
        tt.style.top = top + 'px';
      })
      .on('mouseleave', () => { tt.style.display = 'none'; });
  });

  // Y-axis title
  svg.append('text').attr('class','axis-title')
    .attr('transform', `translate(10,${mT + nN*cs/2}) rotate(-90)`)
    .attr('text-anchor','middle')
    .text('Nugget ID (# docs covered)');

  // X-axis labels
  const xG = svg.append('g').attr('transform', `translate(${mL},${mT})`);
  const xStep = Math.max(5, Math.ceil(30 / cs) * 5);
  for (let i = 0; i < nD; i += xStep) {
    xG.append('text').attr('class','x-label')
      .attr('x', i*cs + cs/2).attr('y', -4)
      .attr('text-anchor','middle')
      .text(i + 1);
  }

  // X-axis title
  const xTitle = isRun
    ? `Run docs (top-${topK}, sorted by retrieval rank)`
    : `Documents (${nD} total, sorted by nugget coverage ↓)`;
  svg.append('text').attr('class','axis-title')
    .attr('x', mL + nD*cs/2).attr('y', H - 4)
    .attr('text-anchor','middle')
    .text(xTitle);
}

// ---- Claims comparison view ----

function findDocForCol(rd, col) {
  return rd.doc_blocks.find(db => col >= db.start && col < db.end);
}

function getClaimInfo(docid) {
  return (claimsCache && claimsCache[docid]) || {title: docid, claims: []};
}

function computeRunStats(d, rd) {
  const coveredNuggetSet = new Set(rd.cells.map(c => c[0]));
  const firstOcc = {};
  rd.cells.forEach(c => { if (!(c[0] in firstOcc) || c[1] < firstOcc[c[0]]) firstOcc[c[0]] = c[1]; });
  const redundantCells = rd.cells.filter(c => c[1] > firstOcc[c[0]]).length;

  let firstFullyRedundantRank = null;
  let fullyRedundantCount = 0;
  rd.doc_blocks.forEach(db => {
    const docCells = rd.cells.filter(c => c[1] >= db.start && c[1] < db.end);
    if (docCells.length === 0) return;
    const isFullyRedundant = docCells.every(c => c[1] > firstOcc[c[0]]);
    if (isFullyRedundant) {
      fullyRedundantCount++;
      if (firstFullyRedundantRank === null) firstFullyRedundantRank = db.rank;
    }
  });

  return {
    nuggetsCovered: coveredNuggetSet.size,
    totalClaims: rd.n_cols,
    coveredCells: rd.cells.length,
    redundantCells,
    fullyRedundantCount,
    firstFullyRedundantRank,
    docsShown: rd.doc_blocks.length,
    ratedDocs: rd.doc_blocks.filter(db => db.rated).length,
  };
}

function renderClaimsView(tid) {
  const d = DATA[tid];
  const nN = d.nuggets.length;

  const runStats = {};
  CLAIM_RUN_NAMES.forEach(rn => {
    const rd = d.claim_runs[rn] || {doc_blocks: [], cells: [], n_cols: 0};
    runStats[rn] = computeRunStats(d, rd);
  });

  let winner = CLAIM_RUN_NAMES[0];
  CLAIM_RUN_NAMES.forEach(rn => {
    const a = runStats[winner], b = runStats[rn];
    if (b.nuggetsCovered > a.nuggetsCovered ||
        (b.nuggetsCovered === a.nuggetsCovered && b.redundantCells < a.redundantCells)) {
      winner = rn;
    }
  });

  const summaryEl = document.getElementById('claims-summary');
  summaryEl.innerHTML = CLAIM_RUN_NAMES.map(rn => {
    const s = runStats[rn];
    const isWinner = rn === winner;
    const redundantPct = s.coveredCells ? (100 * s.redundantCells / s.coveredCells).toFixed(0) : '0';
    return `
      <div class="cmp-card ${isWinner ? 'winner' : ''}">
        <div class="cmp-name">${esc(rn)} ${isWinner ? '<span class="cmp-crown">More nugget coverage</span>' : ''}</div>
        <div class="cmp-row"><span>Nuggets covered</span><b>${s.nuggetsCovered} / ${nN}</b></div>
        <div class="cmp-row"><span>Docs shown (human-rated)</span><b>${s.docsShown} (${s.ratedDocs})</b></div>
        <div class="cmp-row"><span>Claims total</span><b>${s.totalClaims}</b></div>
        <div class="cmp-row"><span>Nugget-stating claims</span><b>${s.coveredCells}</b></div>
        <div class="cmp-row"><span>↳ redundant (nugget already seen)</span><b>${s.redundantCells} (${redundantPct}%)</b></div>
        <div class="cmp-row"><span>Fully-redundant docs</span><b>${s.fullyRedundantCount}${s.firstFullyRedundantRank ? ' · first @ rank ' + s.firstFullyRedundantRank : ''}</b></div>
      </div>`;
  }).join('');

  const container = document.getElementById('claims-matrices');
  container.innerHTML = '';
  CLAIM_RUN_NAMES.forEach(rn => {
    const rd = d.claim_runs[rn] || {doc_blocks: [], cells: [], n_cols: 0};
    const block = document.createElement('div');
    block.className = 'claim-run-block';
    block.innerHTML = `
      <div class="claim-run-title">${esc(rn)} — ${rd.doc_blocks.length} docs (top-''' + str(CLAIM_DEPTH) + '''), ${rd.n_cols} claims</div>
      <div class="claim-matrix-wrap"><svg></svg></div>`;
    container.appendChild(block);
    renderClaimMatrix(tid, rn, block.querySelector('svg'));
  });
}

function isRedundantCell(rd, nugIdx, col) {
  let minCol = Infinity;
  rd.cells.forEach(c => { if (c[0] === nugIdx && c[1] < minCol) minCol = c[1]; });
  return col > minCol;
}

function positionTooltip(event, tt) {
  const vw = window.innerWidth, vh = window.innerHeight;
  let left = event.clientX + 16, top = event.clientY - 12;
  if (left + 480 > vw) left = event.clientX - 488;
  if (top < 4) top = 4;
  const ttH = tt.scrollHeight;
  if (top + ttH > vh - 8) top = Math.max(4, vh - ttH - 8);
  tt.style.left = left + 'px';
  tt.style.top = top + 'px';
}

function renderClaimMatrix(tid, runName, svgEl) {
  const d = DATA[tid];
  const nN = d.nuggets.length;
  const rd = d.claim_runs[runName] || {doc_blocks: [], cells: [], n_cols: 0};
  const cs = claimCellSize;
  const mL = 82, mT = 18, mR = 20, mB = 6;
  const nD = rd.n_cols;
  const W = Math.max(1, nD) * cs + mL + mR;
  const H = nN * cs + mT + mB;
  const tt = document.getElementById('tooltip');

  const svg = d3.select(svgEl).attr('width', W).attr('height', H);
  svg.selectAll('*').remove();
  const g = svg.append('g').attr('transform', `translate(${mL},${mT})`);

  rd.doc_blocks.forEach(db => {
    if (!db.rated) {
      g.append('rect').attr('x', db.start * cs).attr('y', 0)
        .attr('width', (db.end - db.start) * cs).attr('height', nN * cs)
        .attr('fill', '#e8ecf0').attr('pointer-events', 'none');
    }
  });

  rd.doc_blocks.forEach(db => {
    g.append('line').attr('class', 'doc-sep')
      .attr('x1', db.start * cs).attr('x2', db.start * cs)
      .attr('y1', 0).attr('y2', nN * cs);
  });

  const rowHL = g.append('rect')
    .attr('fill', 'rgba(59,130,246,.08)').attr('pointer-events', 'none').attr('display', 'none')
    .attr('x', 0).attr('width', nD * cs).attr('height', cs);

  function showClaimTooltip(event, nugIdx, col) {
    const db = findDocForCol(rd, col);
    if (!db) return;
    const ci = col - db.start;
    const info = getClaimInfo(db.docid);
    const claimText = info.claims[ci] || '';
    const nugId = d.nuggets[nugIdx];
    const ni = d.nugget_info && d.nugget_info[nugId];
    const condBadge = ni ? `<span class="badge-${ni.cond === 'OR' ? 'or' : 'and'}">${esc(ni.cond)}</span>` : '';
    const answersHtml = ni ? `<ul class="tt-answers">${ni.answers.map(a => `<li>${esc(a)}</li>`).join('')}</ul>` : '';
    const redundant = isRedundantCell(rd, nugIdx, col);

    tt.innerHTML = `
      <div class="tt-tag">Nugget #${esc(nugId)} ${condBadge}</div>
      <div class="tt-title">${ni ? esc(ni.question) : 'Nugget #' + esc(nugId)}</div>
      ${answersHtml}
      <div class="tt-section">
        <div class="tt-tag">${esc(runName)} — Doc rank #${db.rank}${redundant ? ' &nbsp;·&nbsp; <span class="badge-grey">REDUNDANT (nugget already seen earlier in this run)</span>' : ' &nbsp;·&nbsp; <span class="badge-blue">FIRST TO STATE THIS NUGGET</span>'}</div>
        <div class="tt-title">${esc(info.title || db.docid)}</div>
        <div class="tt-text">${esc(claimText)}</div>
        <div class="tt-id">${db.docid}#${ci}</div>
      </div>`;
    tt.style.display = 'block';
    positionTooltip(event, tt);
  }

  function showClaimColTooltip(event, col) {
    const db = findDocForCol(rd, col);
    if (!db) return;
    const ci = col - db.start;
    const info = getClaimInfo(db.docid);
    const claimText = info.claims[ci] || '';
    tt.innerHTML = `
      <div class="tt-tag">${esc(runName)} — Doc rank #${db.rank}${db.rated ? '' : ' &nbsp;·&nbsp; <span class="badge-grey">UNRATED DOC</span>'}</div>
      <div class="tt-title">${esc(info.title || db.docid)}</div>
      <div class="tt-text">${esc(claimText)}</div>
      <div class="tt-sub" style="margin-top:6px">Not attributed to any covered nugget${db.rated ? '' : ' (doc has no human nugget ratings)'}</div>
      <div class="tt-id">${db.docid}#${ci}</div>`;
    tt.style.display = 'block';
    positionTooltip(event, tt);
  }

  function showDocHeaderTooltip(event, db) {
    const info = getClaimInfo(db.docid);
    tt.innerHTML = `
      <div class="tt-tag">${esc(runName)} — Rank #${db.rank} &nbsp;·&nbsp; Score: ${db.score}</div>
      <div class="tt-title">${esc(info.title || db.docid)}</div>
      <div class="tt-sub" style="margin-top:4px">${db.n_claims} claims${db.rated ? '' : ' &nbsp;·&nbsp; <span class="badge-grey">UNRATED</span>'}</div>
      <div class="tt-id">${db.docid}</div>`;
    tt.style.display = 'block';
    positionTooltip(event, tt);
  }

  // Full-height transparent hit-target per claim column, drawn BEFORE the
  // colored covered-nugget cells so a covered cell's own (smaller) rect
  // still wins the hover for its row.
  g.selectAll('rect.allcol').data(d3.range(nD)).join('rect').attr('class', 'allcol')
    .attr('x', i => i * cs).attr('y', 0)
    .attr('width', Math.max(1, cs - 1)).attr('height', nN * cs)
    .attr('fill', 'transparent')
    .on('mousemove', function(event, i) { showClaimColTooltip(event, i); })
    .on('mouseleave', function() { tt.style.display = 'none'; });

  function cellFill(nugIdx, col, hover) {
    const redundant = isRedundantCell(rd, nugIdx, col);
    if (hover) return redundant ? '#60a5fa' : '#1d4ed8';
    return redundant ? '#bfdbfe' : '#3b82f6';
  }

  g.selectAll('rect.c').data(rd.cells).join('rect').attr('class', 'c')
    .attr('x', c => c[1] * cs).attr('y', c => c[0] * cs)
    .attr('width', Math.max(1, cs - 1)).attr('height', Math.max(1, cs - 1))
    .attr('rx', cs >= 8 ? 1.5 : 0)
    .attr('fill', c => cellFill(c[0], c[1], false))
    .on('mousemove', function(event, c) {
      rowHL.attr('display', null).attr('y', c[0] * cs);
      d3.select(this).attr('fill', cellFill(c[0], c[1], true));
      showClaimTooltip(event, c[0], c[1]);
    })
    .on('mouseleave', function(event, c) {
      rowHL.attr('display', 'none');
      d3.select(this).attr('fill', cellFill(c[0], c[1], false));
      tt.style.display = 'none';
    });

  const coveredNuggetIdx = new Set(rd.cells.map(c => c[0]));
  const yG = svg.append('g').attr('transform', `translate(0,${mT})`);
  const yShowEvery = cs >= 10 ? 1 : cs >= 6 ? 2 : 5;
  d.nuggets.forEach((nid, i) => {
    if (i % yShowEvery !== 0) return;
    const y = i * cs + cs / 2;
    yG.append('text').attr('class', 'y-label')
      .attr('fill', coveredNuggetIdx.has(i) ? '#475569' : '#d1d5db')
      .attr('x', mL - 5).attr('y', y).attr('text-anchor', 'end').attr('dominant-baseline', 'middle')
      .attr('font-size', Math.min(10, Math.max(cs, 6)))
      .text(`#${nid}`);
  });

  const hdrG = svg.append('g').attr('transform', `translate(${mL},${mT - 5})`);
  rd.doc_blocks.forEach(db => {
    const w = (db.end - db.start) * cs;
    if (w < 10) return;
    hdrG.append('text').attr('class', 'doc-hdr-label')
      .attr('x', db.start * cs + w / 2).attr('y', 0).attr('text-anchor', 'middle')
      .text(`D${db.rank}`)
      .on('mousemove', (event) => showDocHeaderTooltip(event, db));
  });
}

// Initial render
render(topicIds[0]);
</script>
</body>
</html>
'''


def generate_docs_json(docs):
    """Write all document texts to a separate docs.json file."""
    return json.dumps(docs, ensure_ascii=False)


if __name__ == '__main__':
    print('Loading data...')
    qrel, topics, docs, nugget_info = load_data()
    all_runs, ratings = load_run_data()
    claims_by_doc, attribution = load_claim_data()
    print('Processing...')
    vis_data = process_data(qrel, topics, docs, nugget_info, all_runs, ratings, claims_by_doc, attribution)
    run_names = list(all_runs.keys())
    for tid, v in vis_data.items():
        nn, nd, nc = len(v['nuggets']), len(v['docs']), len(v['cells'])
        run_summary = ' | '.join(
            f"{rn}: {len(rd['docs'])} docs, {sum(rd['rated'])} judged, {len(rd['cells'])} covered"
            for rn, rd in v['runs'].items()
        )
        claim_summary = ' | '.join(
            f"{rn}: {len(cd['doc_blocks'])} docs, {cd['n_cols']} claims, {len(cd['cells'])} covered"
            for rn, cd in v['claim_runs'].items()
        )
        print(f'  Topic {tid}: {nn} nuggets × {nd} rel-docs ({nc} pairs) | {run_summary}')
        print(f'    claims: {claim_summary}')
    html = generate_html(vis_data, run_names=run_names)
    OUT_FILE.write_text(html, encoding='utf-8')
    size_kb = len(html.encode()) / 1024
    print(f'\nWrote {OUT_FILE}  ({size_kb:.0f} KB)')
    docs_json = generate_docs_json(docs)
    DOCS_FILE.write_text(docs_json, encoding='utf-8')
    docs_kb = len(docs_json.encode()) / 1024
    print(f'Wrote {DOCS_FILE}  ({docs_kb:.0f} KB)')
    claims_json = json.dumps(claims_by_doc, ensure_ascii=False)
    CLAIMS_FILE.write_text(claims_json, encoding='utf-8')
    claims_kb = len(claims_json.encode()) / 1024
    print(f'Wrote {CLAIMS_FILE}  ({claims_kb:.0f} KB)')
