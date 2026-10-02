"""Existing-schema, offline adapter for ICMA's DatabaseClient result contract.

Reuses rag_query_chroma's path/device resolution and rag_failure10_probe's
full-problem and duplicate guards. Does not create collections or embeddings.
"""
from __future__ import annotations

from difflib import SequenceMatcher
import json
import math
import os
from pathlib import Path
import re
import threading
import unicodedata

from .assets import ensure_runtime_assets

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / 'runtime_assets/reference_rag_v1/chroma'
DEFAULT_MODEL = 'Qwen/Qwen3-Embedding-0.6B'
_LOCK = threading.Lock()
_MODEL = None
_MODEL_KEY = None
_COLLECTIONS = {}
_QUERY_LOCK = threading.Lock()

# Prior manual cross-language review. These IDs are denied globally, including
# when another local comparison batch happens to retrieve them.
MANDATORY_DENY = {
    'aimo_olympiads::a7ee26ea27::4': 'LG-HARD120-001: cross-language same knight problem',
    'aimo_olympiads_ref_base::a07dc2775e::6419': 'BOUNDARY-V1-076: cross-language same rooms problem',
}


def normalize(text):
    text = unicodedata.normalize('NFKC', str(text or '')).casefold()
    text = re.sub(r'\\(?:left|right|displaystyle|textstyle)\b', '', text)
    text = re.sub(r'\\[dt]frac\b', r'\\frac', text)
    text = re.sub(r'\\(?:[,;! ]|quad\b|qquad\b|\(|\)|\[|\])', '', text)
    return re.sub(r'[\s${}]', '', text.replace(r'\{', '{').replace(r'\}', '}'))


def candidate(doc_id, document, meta):
    meta = meta or {}
    document = document or ''
    match = re.match(r'\A题目：(.*?)\n学科：', document, flags=re.S)
    problem = match.group(1) if match else str(meta.get('problem', ''))
    return {'id': str(doc_id), 'problem': problem, 'document': document,
            'metadata': meta, 'answer': str(meta.get('answer', '')),
            'solution': str(meta.get('solution', '')), 'subject': str(meta.get('subject', '')),
            'source': str(meta.get('source', ''))}


def exclusion(row, tests):
    """Conservative duplicate guard used by the frozen local comparison batch."""
    reasons = []
    target_variants = {normalize(row['problem']), normalize(row['metadata'].get('problem', ''))} - {''}
    if not target_variants:
        reasons.append({'reason': 'full_problem_unavailable'})
    for test in tests:
        target = normalize(test['problem'])
        for text in target_variants:
            matcher = SequenceMatcher(None, target, text, autojunk=False)
            if matcher.real_quick_ratio() >= .8 and matcher.quick_ratio() >= .8:
                score = max(matcher.ratio(), SequenceMatcher(None, text, target, autojunk=False).ratio())
                if score >= .8:
                    reasons.append({'reason': 'exact_text' if target == text else 'near_text',
                                    'test_idx': str(test['idx']), 'ratio': score})
    return reasons


def resolve_device(requested='auto'):
    import torch
    if requested == 'cpu':
        return 'cpu'
    if requested != 'auto' and not requested.startswith('cuda'):
        raise ValueError('device must be auto, cpu, cuda or cuda:N')
    target = torch.device('cuda:0' if requested == 'auto' else requested)
    try:
        if not torch.cuda.is_available():
            raise RuntimeError('CUDA unavailable')
        index = target.index if target.index is not None else torch.cuda.current_device()
        if index >= torch.cuda.device_count():
            raise RuntimeError('CUDA device unavailable')
        torch.cuda.get_device_properties(index)
        return f'cuda:{index}'
    except (RuntimeError, AssertionError):
        return 'cpu'


def resolve_model_path(model_name):
    path = Path(str(model_name))
    if path.is_dir():
        return str(path)
    if model_name == DEFAULT_MODEL:
        packaged = ROOT / 'runtime_assets/reference_rag_v1/model'
        if packaged.is_dir() and (packaged / 'model.safetensors').is_file():
            return str(packaged)
        cache = Path.home() / '.cache/huggingface/hub/models--Qwen--Qwen3-Embedding-0.6B/snapshots'
        if cache.is_dir():
            for item in sorted(cache.iterdir(), reverse=True):
                if (item / 'model.safetensors').is_file() and (item / 'config.json').is_file():
                    return str(item)
    return str(model_name)


def adapt(doc_id, document, metadata):
    row = candidate(str(doc_id), document, metadata)
    # Full document fields outrank truncated metadata (6000/1200/9000 chars).
    doc = row['document']
    if '\n答案：' in doc and '\n解答：' in doc:
        _, rest = doc.split('\n答案：', 1)
        row['answer'], row['solution'] = rest.split('\n解答：', 1)
    else:
        try:
            value = json.loads(row['answer'])
            row['answer'] = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        except (ValueError, TypeError):
            pass
    source = row['source']
    try:
        source_meta = json.loads(source)
    except (ValueError, TypeError):
        source_meta = {}
    if not isinstance(source_meta, dict):
        source_meta = {}
    row.update(contest=str(source_meta.get('exam', row['metadata'].get('contest', ''))),
               year=str(source_meta.get('year', row['metadata'].get('year', ''))),
               field_origin='document' if '\n解答：' in doc else 'metadata')
    return row


def exclusion_reasons(row, tests, manual_deny=None):
    reasons = exclusion(row, tests)
    deny = {**MANDATORY_DENY, **(manual_deny or {})}
    ids = {str(row.get('id', ''))}
    ids.update(str(row.get('metadata', {}).get(key)) for key in
               ('id', 'idx', 'test_id', 'original_id', 'source_id')
               if row.get('metadata', {}).get(key) is not None)
    for test in tests:
        if str(test['idx']) in ids:
            reasons.append({'reason': 'exact_test_id', 'test_idx': str(test['idx'])})
    if row['id'] in deny:
        reasons.append({'reason': 'manual_deny_id', 'evidence': deny[row['id']]})
    return reasons


class DatabaseClient:
    """One embedding model per process, collections keyed by their own DB path.

    A conflicting model/device request fails explicitly rather than loading a
    second model or silently reusing another device. Use separate smoke processes
    to compare CPU and auto. No reference-project imports or remote code loading.
    """
    def __init__(self, db_dir=None, collection_name='math_rag_v1',
                 model_id=DEFAULT_MODEL, device='auto'):
        self._use_bundle = db_dir is None and model_id == DEFAULT_MODEL
        self.db_dir = Path(db_dir).resolve() if db_dir else None
        self.collection_name = collection_name
        self.model_id = model_id
        self.requested_device = device

    def _ensure_shared(self):
        global _MODEL, _MODEL_KEY
        if self._use_bundle:
            bundled_model, bundled_db, manifest = ensure_runtime_assets()
            db_dir = bundled_db
            model_path = bundled_model
        else:
            db_dir = self.db_dir
            model_path = Path(resolve_model_path(self.model_id)).resolve()
            manifest = {}
        if not (db_dir / 'chroma.sqlite3').is_file():
            raise FileNotFoundError('Existing local Chroma database required')
        if not (model_path / 'config.json').is_file() or not (model_path / 'model.safetensors').is_file():
            raise FileNotFoundError('Complete committed Qwen model required; downloads forbidden')
        os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                          ANONYMIZED_TELEMETRY='False', TOKENIZERS_PARALLELISM='false')
        device = resolve_device(self.requested_device)
        key = (str(model_path), device)
        collection_key = (str(db_dir), self.collection_name)
        with _LOCK:
            if _MODEL is not None and _MODEL_KEY != key:
                raise ValueError('One model/device per process; use a separate process')
            if collection_key not in _COLLECTIONS:
                import chromadb
                from chromadb.config import Settings
                client = chromadb.PersistentClient(path=str(db_dir),
                    settings=Settings(anonymized_telemetry=False))
                collection = client.get_collection(self.collection_name, embedding_function=None)
                if (collection.metadata or {}).get('hnsw:space') != 'cosine':
                    raise ValueError('Cosine collection required for 1-distance threshold')
                _COLLECTIONS[collection_key] = collection
            if _MODEL is None:
                from sentence_transformers import SentenceTransformer
                _MODEL = SentenceTransformer(str(model_path), device=device,
                    local_files_only=True, trust_remote_code=False)
                _MODEL_KEY = key
            self._model = _MODEL
            self._collection = _COLLECTIONS[collection_key]
            count_method = getattr(self._collection, 'count', None)
            self.info = {'model': DEFAULT_MODEL, 'device': device,
                         'max_seq_length': self._model.max_seq_length,
                         'document_format': 'rag_build_chroma Chinese field labels',
                         'corpus_count': count_method() if callable(count_method) else None,
                         'bundle_sha256': manifest.get('bundle_sha256', ''),
                         'threshold_calibrated': False}

    def scan(self):
        self._ensure_shared()
        count = self._collection.count()
        rows = {}
        for offset in range(0, count, 500):
            batch = self._collection.get(limit=500, offset=offset, include=['documents', 'metadatas'])
            for doc_id, doc, meta in zip(batch['ids'], batch['documents'], batch['metadatas']):
                rows[doc_id] = adapt(doc_id, doc, meta)
        if len(rows) != count or self._collection.count() != count:
            raise ValueError('Incomplete or changing collection scan')
        return rows

    def query(self, problem, top_k=2):
        if not isinstance(problem, str) or not problem.strip() or not 1 <= top_k <= 100:
            raise ValueError('Nonempty problem and top_k in 1..100 required')
        self._ensure_shared()
        # Reject oversized query rather than silently truncating the original.
        if len(self._model.tokenizer.encode(problem)) > self._model.max_seq_length:
            raise ValueError('Problem exceeds cached embedding sequence limit')
        count = self._collection.count()
        if not count:
            return []
        with _QUERY_LOCK:
            vector = self._model.encode([problem], normalize_embeddings=True,
                                        convert_to_numpy=True)[0].tolist()
            response = self._collection.query(query_embeddings=[vector], n_results=min(top_k, count),
                                             include=['documents', 'metadatas', 'distances'])
        rows = []
        for doc_id, doc, meta, distance in zip(response['ids'][0], response['documents'][0],
                response['metadatas'][0], response['distances'][0]):
            similarity = 1 - float(distance)
            if not math.isfinite(similarity):
                raise ValueError('Nonfinite vector distance')
            rows.append({**adapt(doc_id, doc, meta), 'similarity': similarity})
        return rows


def select_references(rows, tests, manual_deny=None):
    selected, audit = [], []
    for row in rows:
        reasons = exclusion_reasons(row, tests, manual_deny)
        if not math.isfinite(row['similarity']) or row['similarity'] < .55:
            reasons.append({'reason': 'below_similarity_threshold_or_nonfinite'})
        placeholders = {'', 'empty', 'not found', 'n/a', 'none', 'null', 'unknown', '暂无', '未找到'}
        if row['answer'].strip().casefold() in placeholders and row['solution'].strip().casefold() in placeholders:
            reasons.append({'reason': 'no_source_answer_or_solution'})
        if len(row['problem']) + len(row['answer']) + len(row['solution']) > 18000:
            reasons.append({'reason': 'reference_character_budget_exceeded'})
        if not reasons and len(selected) < 2:
            selected.append(row)
        audit.append({'id': row['id'], 'similarity': row['similarity'], 'reasons': reasons,
                      'selected': row in selected})
    return selected, audit


def select_runtime_references(rows):
    """Select prompt references without reading any test key or local gold."""
    selected, audit = [], []
    placeholders = {'', 'empty', 'not found', 'n/a', 'none', 'null', 'unknown', '暂无', '未找到'}
    for row in rows:
        reasons = []
        similarity = row.get('similarity')
        if not isinstance(similarity, (int, float)) or not math.isfinite(similarity) or similarity < .55:
            reasons.append({'reason': 'below_similarity_threshold_or_nonfinite'})
        if row.get('answer', '').strip().casefold() in placeholders and row.get('solution', '').strip().casefold() in placeholders:
            reasons.append({'reason': 'no_source_answer_or_solution'})
        if not normalize(row.get('problem', '')):
            reasons.append({'reason': 'full_problem_unavailable'})
        if len(row.get('problem', '')) + len(row.get('answer', '')) + len(row.get('solution', '')) > 18000:
            reasons.append({'reason': 'reference_character_budget_exceeded'})
        if not reasons and len(selected) < 2:
            selected.append(row)
        audit.append({'id': row.get('id', ''), 'similarity': similarity,
                      'reasons': reasons, 'selected': row in selected})
    return selected, audit
