#!/usr/bin/env python3
"""Generate the NeuCLIR 2024 per-document claim/nugget coverage page.

Simple, list-based view: for two fixed runs (BM25 vs the coverage-optimized
Lancer reranker), walk each run's top-CLAIM_DEPTH ranked documents in order
and show, per document: how many claims it decomposes into, how many nuggets
it covers, and how many of those nuggets are redundant (already covered by
an earlier-ranked document in the same run). No nugget x document matrix --
just document-by-document counts, meant to be skimmed top to bottom and
compared side by side across the two runs. See demo_common.py for the
dataset-agnostic data assembly and page rendering.
"""

import json
from collections import defaultdict
from pathlib import Path

import demo_common

DATA_DIR = Path(__file__).parent / 'data' / 'neuclir'
OUT_FILE = Path(__file__).parent / 'index.html'

RUN_SPECS = [
    ('bm25', DATA_DIR / 'runs.neuclir2024.bm25.test.txt'),
    ('lancer-top100', DATA_DIR / 'runs.neuclir2024.cover.lancer_expr-top100.test.txt'),
]
DEPTH = 20


def load_topics():
    topics = {}
    with open(DATA_DIR / 'neuclir24-test-request.jsonl') as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                topics[d['request_id']] = d
    return topics


def load_nugget_info():
    """topic_id -> {nugget_id: {question, answers, cond}}, in nugget-id order."""
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
    return nugget_info


def load_doc_coverage():
    """topic_id -> {docid: set(covered_nugget_id)}.

    Built from the full per-nugget rating array (ratings.human.jsonl), so a
    doc's presence as a key means it was judged, whether or not it covers
    anything.
    """
    doc_coverage = defaultdict(dict)
    with open(DATA_DIR / 'neuclir24.ratings.human.jsonl') as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            tid, docid, rating = str(d['id']), d['docid'], d['rating']
            covered = {str(i + 1) for i, v in enumerate(rating) if v == 3}
            doc_coverage[tid][docid] = covered
    return doc_coverage


def load_claim_data():
    """docid -> {'title':..., 'claims':[...]}, topic_id -> {docid: {nugget_id: [claim_idx,...]}}"""
    claims_file = DATA_DIR / 'neuclir24.claims.byid.json'
    attribution_file = DATA_DIR / 'neuclir24.claim_attribution.json'
    claims_by_doc = json.loads(claims_file.read_text()) if claims_file.exists() else {}
    attribution = json.loads(attribution_file.read_text()) if attribution_file.exists() else {}
    return claims_by_doc, attribution


if __name__ == '__main__':
    print('Loading data...')
    topics = load_topics()
    nugget_info = load_nugget_info()
    doc_coverage = load_doc_coverage()
    claims_by_doc, attribution = load_claim_data()
    claim_run_topk = demo_common.load_claim_run_topk(RUN_SPECS, DEPTH)
    run_names = [name for name, _ in RUN_SPECS]

    print('Processing...')
    vis_data = demo_common.process_data(
        topics, nugget_info, doc_coverage, claims_by_doc, attribution, claim_run_topk, run_names
    )

    for tid, v in vis_data.items():
        line = f"  Topic {tid}: {len(v['nugget_order'])} nuggets"
        for rn in run_names:
            s = v['doc_runs'][rn]['summary']
            line += f" | {rn}: {s['n_docs']} docs ({s['n_rated']} rated), {s['total_unique_covered']}/{s['n_nuggets']} covered, {s['n_fully_redundant']} fully-redundant"
        print(line)

    html = demo_common.generate_html(
        vis_data, run_names,
        page_title='NeuCLIR 2024 — Claim &amp; Nugget Coverage by Document',
        logo_html='NeuCLIR<span> 2024</span>',
        subtitle='Per-document Claim &amp; Nugget Coverage — BM25 vs Lancer',
    )
    OUT_FILE.write_text(html, encoding='utf-8')
    size_kb = len(html.encode()) / 1024
    print(f'\nWrote {OUT_FILE}  ({size_kb:.0f} KB)')
