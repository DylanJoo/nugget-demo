"""Shared rendering/data-assembly logic for the per-document claim/nugget
coverage comparison pages (used by generate_demo.py for NeuCLIR and
generate_demo_ragtime.py for RAGTIME).

Dataset-specific loaders build a `doc_coverage` structure:
    {topic_id: {docid: set(covered_nugget_id), ...}}
A docid's presence as a key means "this doc was judged" (rated), regardless
of whether its covered set is empty. Everything downstream (redundancy
walk, HTML/JS) is dataset-agnostic.
"""

import json
from collections import defaultdict


def load_claim_run_topk(run_specs, depth):
    """run_name -> {topic_id: [(rank, docid, score), ...]} truncated to depth."""
    claim_run_topk = {}
    for run_name, path in run_specs:
        by_topic = defaultdict(list)
        with open(path) as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 6:
                    by_topic[parts[0]].append((int(parts[3]), parts[2], float(parts[4])))
        topk = {}
        for tid, lst in by_topic.items():
            lst.sort(key=lambda x: x[0])
            topk[tid] = lst[:depth]
        claim_run_topk[run_name] = topk
    return claim_run_topk


def build_doc_runs(tid, nugget_ids, doc_coverage_for_tid, claims_by_doc, attribution, claim_run_topk, run_names):
    """For each fixed run, the ranked doc list with per-doc claim/nugget stats.

    Redundancy is computed by walking the run's own ranking: a covered
    nugget is "new" the first time any document in this run states it, and
    "redundant" on every later document that also covers it.
    """
    topic_attr = attribution.get(tid, {})
    out = {}
    for run_name in run_names:
        seen = set()
        first_new_rank = {}  # nugget_id -> rank of the doc that first surfaced it
        docs_out = []
        for rank, docid, score in claim_run_topk[run_name].get(tid, []):
            info = claims_by_doc.get(docid) or {'title': '', 'claims': []}
            claims = info['claims']
            rated = docid in doc_coverage_for_tid

            doc_attr = topic_attr.get(docid, {})
            claim_tags = defaultdict(list)
            for nid, claim_idxs in doc_attr.items():
                for ci in claim_idxs:
                    claim_tags[ci].append(nid)

            if rated:
                covered_set = doc_coverage_for_tid[docid]
                covered_ids = [nid for nid in nugget_ids if nid in covered_set]
                new_ids = sorted(covered_set - seen, key=int)
                redundant_ids = sorted(covered_set & seen, key=int)
                for nid in new_ids:
                    first_new_rank[nid] = rank
                seen |= covered_set
                cum_covered = len(seen)
                new_efficiency = round(len(new_ids) / len(claims), 4) if claims else 0.0
            else:
                covered_ids = new_ids = redundant_ids = None
                cum_covered = None
                new_efficiency = None

            docs_out.append({
                'docid': docid,
                'title': info['title'],
                'rank': rank,
                'score': round(score, 6),
                'rated': rated,
                'n_claims': len(claims),
                'claims': claims,
                'claim_tags': {str(k): v for k, v in claim_tags.items()},
                'covered_ids': covered_ids,
                'new_ids': new_ids,
                'redundant_ids': redundant_ids,
                'cum_covered': cum_covered,
                'new_efficiency': new_efficiency,
            })

        rated_docs = [d for d in docs_out if d['rated']]
        fully_redundant = [d for d in rated_docs if len(d['covered_ids']) > 0 and len(d['new_ids']) == 0]
        total_claims_rated = sum(d['n_claims'] for d in rated_docs)
        new_per_100_claims = round(100 * len(seen) / total_claims_rated, 2) if total_claims_rated else 0.0
        avg_first_new_rank = round(sum(first_new_rank.values()) / len(first_new_rank), 2) if first_new_rank else None
        out[run_name] = {
            'docs': docs_out,
            'summary': {
                'n_nuggets': len(nugget_ids),
                'total_unique_covered': len(seen),
                'n_docs': len(docs_out),
                'n_rated': len(rated_docs),
                'avg_claims': round(sum(d['n_claims'] for d in docs_out) / len(docs_out), 1) if docs_out else 0,
                'n_fully_redundant': len(fully_redundant),
                'first_fully_redundant_rank': fully_redundant[0]['rank'] if fully_redundant else None,
                'new_per_100_claims': new_per_100_claims,
                'avg_first_new_rank': avg_first_new_rank,
            },
        }
    return out


def process_data(topics, nugget_info, doc_coverage, claims_by_doc, attribution, claim_run_topk, run_names):
    """topics: {tid: {title, background, problem_statement}}
    nugget_info: {tid: {nugget_id: {question, answers, cond}}}
    doc_coverage: {tid: {docid: set(covered_nugget_id)}}
    """
    vis_data = {}
    for tid in sorted(topics.keys(), key=int):
        tinfo = nugget_info.get(tid)
        if not tinfo:
            continue
        nugget_ids = sorted(tinfo.keys(), key=int)
        doc_runs = build_doc_runs(
            tid, nugget_ids, doc_coverage.get(tid, {}), claims_by_doc, attribution, claim_run_topk, run_names
        )
        vis_data[tid] = {
            'title': topics[tid].get('title', tid),
            'background': topics[tid].get('background', ''),
            'problem_statement': topics[tid].get('problem_statement', ''),
            'nuggets': tinfo,
            'nugget_order': nugget_ids,
            'doc_runs': doc_runs,
        }
    return vis_data


def generate_html(vis_data, run_names, page_title, logo_html, subtitle):
    data_json = json.dumps(vis_data, ensure_ascii=False)
    run_names_json = json.dumps(run_names)

    return '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>''' + page_title + '''</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',system-ui,sans-serif;background:#f0f2f5;color:#1e293b;min-height:100vh}

header{background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 100%);color:#fff;padding:18px 28px;display:flex;align-items:center;gap:16px;box-shadow:0 2px 8px rgba(0,0,0,.3)}
header .logo{font-size:1.5rem;font-weight:800;letter-spacing:-0.5px}
header .logo span{color:#60a5fa}
header .subtitle{font-size:.82rem;opacity:.6;margin-top:3px}

.main{max-width:1500px;margin:0 auto;padding:20px 24px;display:flex;flex-direction:column;gap:16px}

.card{background:#fff;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,.08),0 1px 2px rgba(0,0,0,.06);padding:18px 22px}

.controls{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.controls label{font-weight:600;font-size:.85rem;color:#475569}
select{padding:7px 12px;border:1.5px solid #e2e8f0;border-radius:6px;font-size:.88rem;background:#fff;cursor:pointer;color:#1e293b;outline:none}
select:focus{border-color:#3b82f6}
#topic-sel{min-width:320px}

.topic-title{font-size:1.1rem;font-weight:700;color:#0f172a;margin-bottom:10px}
.info-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.info-block strong{display:block;font-size:.68rem;text-transform:uppercase;letter-spacing:.6px;color:#94a3b8;margin-bottom:4px}
.info-block p{font-size:.8rem;color:#475569;line-height:1.5}

.run-columns{display:flex;gap:18px;flex-wrap:wrap;align-items:flex-start}
.run-col{flex:1;min-width:340px;display:flex;flex-direction:column;gap:10px}

.run-summary{border-radius:8px;padding:12px 16px;border:1px solid #e2e8f0}
.run-summary.winner{border-color:#3b82f6;background:linear-gradient(135deg,#eff6ff,#dbeafe)}
.run-name{font-weight:700;font-size:.92rem;color:#0f172a;margin-bottom:6px;display:flex;align-items:center;gap:6px}
.crown{font-size:.68rem;background:#1d4ed8;color:#fff;padding:1px 7px;border-radius:9px;font-weight:700}
.run-summary .row{display:flex;justify-content:space-between;font-size:.78rem;color:#475569;padding:1px 0}
.run-summary .row b{color:#0f172a}

.doc-card{border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;background:#fff}
.doc-card.unrated{background:#f8fafc}
.doc-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.doc-rank{font-weight:800;color:#1d4ed8;font-size:.8rem;min-width:28px}
.doc-title{font-size:.85rem;font-weight:600;color:#0f172a;flex:1;min-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.doc-score{font-size:.72rem;color:#94a3b8;font-family:monospace}
.badge{display:inline-block;padding:1px 7px;border-radius:9px;font-size:.66rem;font-weight:700}
.badge-rated{background:#dcfce7;color:#166534}
.badge-unrated{background:#e2e8f0;color:#64748b}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin-top:7px}
.chip{font-size:.72rem;padding:2px 8px;border-radius:6px;background:#f1f5f9;color:#475569}
.chip b{color:#0f172a}
.chip.new{background:#dbeafe;color:#1e3a8a}
.chip.redundant{background:#fef3c7;color:#92400e}
.chip.claims{background:#f3e8ff;color:#6b21a8}
.chip.efficiency{background:#dcfce7;color:#166534}
.cum{font-size:.7rem;color:#94a3b8;margin-top:5px}

details.drill{margin-top:7px}
details.drill summary{cursor:pointer;font-size:.72rem;color:#3b82f6;font-weight:600;list-style:none;user-select:none}
details.drill summary::-webkit-details-marker{display:none}
details.drill summary::before{content:'▸ ';display:inline-block;transition:transform .1s}
details.drill[open] summary::before{content:'▾ '}
.claim-list{margin-top:8px;padding-left:0;list-style:none;display:flex;flex-direction:column;gap:4px}
.claim-list li{font-size:.76rem;color:#334155;line-height:1.4;padding:4px 8px;border-radius:5px;background:#fafafa;border-left:2px solid transparent}
.claim-list li.tag-new{border-left-color:#3b82f6;background:#eff6ff}
.claim-list li.tag-redundant{border-left-color:#f59e0b;background:#fffbeb}
.claim-tag{display:inline-block;margin-left:6px;font-size:.65rem;font-weight:700;padding:0 5px;border-radius:5px}
.claim-tag.new{background:#3b82f6;color:#fff}
.claim-tag.redundant{background:#f59e0b;color:#fff}
.nugget-list{margin:6px 0 0;padding-left:0;list-style:none;font-size:.74rem}
.nugget-list li{padding:2px 0;color:#475569}
.nugget-list b{color:#0f172a}

.empty-note{font-size:.78rem;color:#94a3b8;font-style:italic;padding:8px 0}
</style>
</head>
<body>
<header>
  <div>
    <div class="logo">''' + logo_html + '''</div>
    <div class="subtitle">''' + subtitle + '''</div>
  </div>
</header>

<div class="main">

  <div class="card controls">
    <label for="topic-sel">Topic</label>
    <select id="topic-sel"></select>
  </div>

  <div class="card" id="topic-info"></div>

  <div class="run-columns" id="run-columns"></div>

</div>

<script>
const DATA = ''' + data_json + ''';
const RUN_NAMES = ''' + run_names_json + ''';
const topicIds = Object.keys(DATA).sort((a,b)=>+a-+b);

function esc(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') }

const sel = document.getElementById('topic-sel');
topicIds.forEach(tid => {
  const o = document.createElement('option');
  o.value = tid;
  o.textContent = `${tid} — ${DATA[tid].title}`;
  sel.appendChild(o);
});
sel.addEventListener('change', () => render(sel.value));

function nuggetQuestion(d, nid) {
  const n = d.nuggets[nid];
  return n ? n.question : `Nugget #${nid}`;
}

function idList(d, ids) {
  return `<ul class="nugget-list">${ids.map(nid => `<li><b>#${esc(nid)}</b> ${esc(nuggetQuestion(d, nid))}</li>`).join('')}</ul>`;
}

function renderDocCard(d, doc) {
  const ratedBadge = doc.rated
    ? '<span class="badge badge-rated">RATED</span>'
    : '<span class="badge badge-unrated">UNRATED</span>';

  let chips, drillNuggets = '';
  if (doc.rated) {
    const nCovered = doc.covered_ids.length, nNew = doc.new_ids.length, nRedundant = doc.redundant_ids.length;
    const effPct = (doc.new_efficiency * 100).toFixed(1);
    chips = `
      <div class="chip claims"><b>${doc.n_claims}</b> claims</div>
      <div class="chip"><b>${nCovered}</b> covered</div>
      <div class="chip new"><b>${nNew}</b> new</div>
      <div class="chip redundant"><b>${nRedundant}</b> redundant</div>
      <div class="chip efficiency" title="New nuggets per claim in this document"><b>${effPct}%</b> new/claim</div>`;
    const parts = [];
    if (nNew) parts.push(`<div><strong style="font-size:.7rem;color:#1e3a8a">New nuggets</strong>${idList(d, doc.new_ids)}</div>`);
    if (nRedundant) parts.push(`<div><strong style="font-size:.7rem;color:#92400e">Redundant nuggets (already seen)</strong>${idList(d, doc.redundant_ids)}</div>`);
    drillNuggets = parts.join('');
  } else {
    chips = `<div class="chip claims"><b>${doc.n_claims}</b> claims</div><div class="chip">coverage unknown (no human rating)</div>`;
  }

  const claimItems = doc.claims.map((text, ci) => {
    const tags = doc.claim_tags[String(ci)] || [];
    let cls = '', tagHtml = '';
    if (doc.rated && tags.length) {
      const newSet = new Set(doc.new_ids), redSet = new Set(doc.redundant_ids);
      const isNew = tags.some(nid => newSet.has(nid));
      const isRed = tags.some(nid => redSet.has(nid));
      cls = isNew ? 'tag-new' : (isRed ? 'tag-redundant' : '');
      tagHtml = tags.map(nid => {
        const kind = newSet.has(nid) ? 'new' : (redSet.has(nid) ? 'redundant' : '');
        return kind ? `<span class="claim-tag ${kind}">#${esc(nid)}</span>` : '';
      }).join('');
    }
    return `<li class="${cls}">${esc(text)}${tagHtml}</li>`;
  }).join('');

  const cumLine = doc.rated
    ? `<div class="cum">Running total after this doc: ${doc.cum_covered} / ${d.nugget_order.length} nuggets seen</div>`
    : '';

  return `
    <div class="doc-card ${doc.rated ? '' : 'unrated'}">
      <div class="doc-head">
        <div class="doc-rank">#${doc.rank}</div>
        <div class="doc-title" title="${esc(doc.title || doc.docid)}">${esc(doc.title || doc.docid)}</div>
        <div class="doc-score">${doc.score.toFixed(4)}</div>
        ${ratedBadge}
      </div>
      <div class="chips">${chips}</div>
      ${cumLine}
      <details class="drill">
        <summary>Details (claims &amp; nugget attribution)</summary>
        ${drillNuggets}
        <ul class="claim-list">${claimItems || '<li>No claims available.</li>'}</ul>
      </details>
    </div>`;
}

function renderRunColumn(d, runName, winner) {
  const rd = d.doc_runs[runName];
  const s = rd.summary;
  const isWinner = runName === winner;
  const summaryHtml = `
    <div class="run-summary ${isWinner ? 'winner' : ''}">
      <div class="run-name">${esc(runName)} ${isWinner ? '<span class="crown">More coverage</span>' : ''}</div>
      <div class="row"><span>Nuggets covered</span><b>${s.total_unique_covered} / ${s.n_nuggets}</b></div>
      <div class="row"><span>Docs shown (rated)</span><b>${s.n_docs} (${s.n_rated})</b></div>
      <div class="row"><span>Avg claims / doc</span><b>${s.avg_claims}</b></div>
      <div class="row"><span>Fully-redundant docs</span><b>${s.n_fully_redundant}${s.first_fully_redundant_rank ? ' · first @ rank ' + s.first_fully_redundant_rank : ''}</b></div>
      <div class="row" title="New (unique) nuggets found per 100 claims read across this run's rated docs"><span>New-nugget efficiency</span><b>${s.new_per_100_claims} / 100 claims</b></div>
      <div class="row" title="Mean retrieval rank at which each new nugget was first surfaced — lower means the run front-loads novel information"><span>Avg rank of new-nugget discovery</span><b>${s.avg_first_new_rank !== null ? s.avg_first_new_rank : '—'}</b></div>
    </div>`;
  const cardsHtml = rd.docs.map(doc => renderDocCard(d, doc)).join('');
  return `<div class="run-col">${summaryHtml}${cardsHtml}</div>`;
}

function render(tid) {
  const d = DATA[tid];

  document.getElementById('topic-info').innerHTML = `
    <div class="topic-title">Topic ${esc(tid)}: ${esc(d.title)}</div>
    <div class="info-grid">
      <div class="info-block"><strong>Background</strong><p>${esc(d.background)}</p></div>
      <div class="info-block"><strong>Problem Statement</strong><p>${esc(d.problem_statement)}</p></div>
    </div>`;

  let winner = RUN_NAMES[0];
  RUN_NAMES.forEach(rn => {
    const a = d.doc_runs[winner].summary, b = d.doc_runs[rn].summary;
    if (b.total_unique_covered > a.total_unique_covered) winner = rn;
  });

  document.getElementById('run-columns').innerHTML =
    RUN_NAMES.map(rn => renderRunColumn(d, rn, winner)).join('');
}

render(topicIds[0]);
</script>
</body>
</html>
'''
