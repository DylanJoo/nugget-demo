#!/usr/bin/env python3
"""Generate the RAGTIME1 (2025) per-document claim/nugget coverage page.

Same design as generate_demo.py (NeuCLIR), comparing two dense-retrieval
runs (Qwen3-Embedding-0.6B vs modernbert-base.cover-5k) over their top-DEPTH
ranked documents per topic. See demo_common.py for the shared data assembly
and page rendering.

Unlike NeuCLIR, RAGTIME has no full per-nugget rating array -- only a qrel
of positive (doc, nugget) coverage pairs, so "rated" here means "appears in
the qrel for this topic" rather than "was shown to an annotator." A doc
judged irrelevant to every nugget is indistinguishable from a doc that was
never judged at all; this is a known limitation of the available data, not
a bug in this script.
"""

import json
from collections import defaultdict
from pathlib import Path

import demo_common

DATA_DIR = Path(__file__).parent / 'data' / 'ragtime'
OUT_FILE = Path(__file__).parent / 'index_ragtime.html'

RUN_SPECS = [
    ('qwen3-embed', DATA_DIR / 'run.ragtime1.documents.Qwen3-Embedding-0.6B.txt'),
    ('modernbert-cover', DATA_DIR / 'run.ragtime1.documents.modernbert-base.cover-5k.txt'),
]
DEPTH = 20


def load_topics():
    """topic_id -> {title, background, problem_statement}"""
    topics = {}
    with open(DATA_DIR / 'ragtime25_main_all.jsonl') as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                topics[str(d['topic_id'])] = d
    return topics


def load_nugget_info():
    """topic_id -> {nugget_id: {question, answers, cond}}, in nugget-id order.

    RAGTIME's nugget file (converted from ragtime_nuggets.tsv) has no gold
    answer text, only the question -- answers is always [].
    """
    nugget_info = {}
    with open(DATA_DIR / 'ragtime25.nuggets.human.jsonl') as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            tid = str(d['id'])
            info = {}
            for idx, item in enumerate(d['nuggets'], start=1):
                question, answers = item[0], item[1]
                info[str(idx)] = {'question': question, 'answers': answers, 'cond': 'OR'}
            nugget_info[tid] = info
    return nugget_info


def load_doc_coverage():
    """topic_id -> {docid: set(covered_nugget_id)}, from the positive-only qrel."""
    doc_coverage = defaultdict(dict)
    with open(DATA_DIR / 'ragtime25-test-request.qrel') as f:
        for line in f:
            tid, nid, docid, label = line.split()
            doc_coverage[tid].setdefault(docid, set()).add(nid)
    return doc_coverage


def load_claim_data():
    """docid -> {'title':..., 'claims':[...]}, topic_id -> {docid: {nugget_id: [claim_idx,...]}}"""
    claims_file = DATA_DIR / 'ragtime25.claims.byid.json'
    attribution_file = DATA_DIR / 'ragtime25.claim_attribution.json'
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
        page_title='RAGTIME 2025 — Claim &amp; Nugget Coverage by Document',
        logo_html='RAGTIME<span> 2025</span>',
        subtitle='Per-document Claim &amp; Nugget Coverage — Qwen3-Embedding vs ModernBERT-cover',
    )
    OUT_FILE.write_text(html, encoding='utf-8')
    size_kb = len(html.encode()) / 1024
    print(f'\nWrote {OUT_FILE}  ({size_kb:.0f} KB)')
