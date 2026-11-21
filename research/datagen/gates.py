"""Deterministic gates for the AcneLLM ROLE dataset.

Usage:
    python datagen/gates.py datagen/output/v4_role/v4_role.smoke.jsonl

The module reuses the repository grounding scorer and the existing persistent
8-gram/duplicate implementation instead of maintaining a second definition.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import re
import sys
import unicodedata
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datagen.contamination import (  # noqa: E402
    ContaminationHit,
    DuplicateGuard,
    iter_ngrams,
    normalized_text,
    normalized_tokens,
)
from evaluation.metrics.grounding import (  # noqa: E402
    GroundingScorer,
    normalize_grounding_text,
    split_vietnamese_sentences,
)


REQUIRED_FIELDS = {
    "id",
    "sample_kind",
    "input_style",
    "synthetic_context",
    "knowledge_leak_check",
    "grounded_sentence_rate",
    "gen_model",
    "messages",
}
VALID_INPUT_STYLES = {"standard", "teencode", "no_accent", "typo", "mixed"}
NUMERIC_REGIMEN_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:mg|mcg|%|lan\s*(?:/|moi)\s*ngay|tuan)\b",
    re.IGNORECASE,
)
_MISSING_PATTERNS = (
    "tai lieu chua de cap",
    "tai lieu khong de cap",
    "khong co thong tin trong tai lieu",
    "khong du thong tin trong tai lieu",
)
_CONFLICT_PATTERNS = ("mau thuan", "khac nhau", "khong thong nhat")
_ESCALATION_PATTERNS = ("bac si", "chuyen gia")
_BOILERPLATE_PATTERNS = (
    "minh hieu ban",
    "minh hieu dieu nay",
    "tai lieu chua de cap",
    "tai lieu khong de cap",
    "khong co thong tin trong tai lieu",
    "khong du thong tin trong tai lieu",
    "nen hoi bac si",
    "ban co the hoi bac si",
    "khuyen ban hoi",
    "khuyen ban trao doi",
    "hoi truc tiep bac si",
    "trao doi truc tiep voi bac si",
    "hai nguon khong thong nhat",
    "hai nguon co thong tin khac nhau",
)

_GROUNDING_SCORER: GroundingScorer | None = None


def configure_grounding_embedder(embedder: Any) -> GroundingScorer:
    """Install the real repository embedder for all grounding gates."""
    global _GROUNDING_SCORER
    _GROUNDING_SCORER = GroundingScorer(embedder=embedder)
    return _GROUNDING_SCORER


def grounding_scorer() -> GroundingScorer:
    """Return the configured scorer; lexical-only is kept for isolated unit tests."""
    return _GROUNDING_SCORER or GroundingScorer()


def semantic_sanity_check(embedder: Any) -> dict[str, Any]:
    """Assert that a Vietnamese paraphrase pair has a meaningful cosine score."""
    scorer = GroundingScorer(embedder=embedder)
    result = scorer.score(
        "Nên rửa mặt nhẹ nhàng hai lần mỗi ngày.",
        ["Làm sạch da dịu nhẹ vào buổi sáng và buổi tối."],
    )
    scores = result.get("sentence_scores") or []
    semantic_score = float(scores[0].get("semantic_score") or 0.0) if scores else 0.0
    return {
        "passed": semantic_score > 0.5,
        "pass": semantic_score > 0.5,
        "reasons": [] if semantic_score > 0.5 else ["semantic_sanity_below_0.5"],
        "semantic_score": round(semantic_score, 4),
        "model_check": "AITeamVN/Vietnamese_Embedding",
    }


def _accentless(text: str) -> str:
    value = unicodedata.normalize("NFD", str(text or "").casefold())
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return value.replace("đ", "d")


def vocative_consistency_check(user: str, answer: str) -> dict[str, Any]:
    """Catch mixed register such as addressing a parent as ``cô`` then ``mình``."""
    user_norm = _accentless(user)
    answer_norm = _accentless(answer)
    reasons: list[str] = []
    parent_user = bool(
        re.search(r"\b(?:con|chau)(?:\s+(?:trai|gai))?\s+(?:co|chu|bac)\b", user_norm)
        or re.search(
            r"\b(?:co|chu|bac)\s+(?!si\b)(?:khong|dang|muon|can|lo|hoi|thay|co)\b",
            user_norm,
        )
    )
    parent_answer = bool(re.search(r"\b(?:co|chu|bac)\s+oi\b", answer_norm))
    self_minh = bool(re.search(r"\b(?:cho|minh|voi)\s+minh\b|\bminh\s+(?:hieu|co the|muon)\b", answer_norm))
    if (parent_user or parent_answer) and self_minh:
        reasons.append("parent_vocative_mixed_with_minh")
    answer_uses_honorific = bool(
        re.search(r"\b(?:co|chu|bac)\s+(?:dang|co|nen|cho|minh|bi|can|cu)\b", answer_norm)
    )
    if answer_uses_honorific and not parent_user:
        reasons.append("unprompted_parent_vocative")
    if re.search(r"^(?:co|chu|bac)\s+(?:hieu|thay|co the|se)\b", answer_norm):
        reasons.append("assistant_self_as_honorific")
    addresses_ban = bool(re.search(r"\bban\b", answer_norm))
    addresses_em = bool(re.search(r"\bem\b", answer_norm))
    if addresses_ban and addresses_em:
        reasons.append("mixed_user_address_ban_em")
    user_em = bool(re.search(r"(?:^|\s)(?:em|e)(?:\s|$)", user_norm))
    if user_em and addresses_ban and not addresses_em:
        reasons.append("user_em_answer_ban")
    passed = not reasons
    return {"passed": passed, "pass": passed, "reasons": reasons}


_UNEXPECTED_ENGLISH = {
    "mostly", "basically", "actually", "literally", "anyway", "whatever",
    "maybe", "probably", "random", "seriously", "totally", "obviously",
    "glad", "inflammatory", "comedone",
}


def standard_code_switch_check(text: str, *, input_style: str) -> dict[str, Any]:
    """Reject stray conversational English in records labelled ``standard``."""
    reasons: list[str] = []
    if input_style == "standard":
        tokens = set(re.findall(r"[a-z]+", str(text or "").casefold()))
        hits = sorted(tokens & _UNEXPECTED_ENGLISH)
        reasons.extend(f"unexpected_english:{token}" for token in hits)
        if re.search(r"[\u3400-\u9fff]", str(text or "")):
            reasons.append("unexpected_cjk")
        if re.search(r"[\u0400-\u04ff]", str(text or "")):
            reasons.append("unexpected_cyrillic")
    passed = not reasons
    return {"passed": passed, "pass": passed, "reasons": reasons}


_NATURAL_VERBS = {
    "bi", "biet", "boi", "can", "cham", "co", "dung", "giai thich", "giup",
    "gap", "hoi", "kham", "la", "lam", "noi", "ran", "rua", "thoa", "thu",
    "tron", "tu van", "xai", "xu ly",
}
_TEENCODE_MARKERS = {"k", "ko", "kh", "dc", "j", "z", "bt", "mk", "mik", "r", "mn", "hong"}
_TEENCODE_CANDIDATES = {
    "k", "ko", "kh", "dc", "j", "z", "bt", "mk", "mik", "r", "mn",
    "hok", "hem", "hong", "cx", "vk", "ck", "ib", "rep", "ad",
}


def input_naturalness_check(text: str, input_style: str) -> dict[str, Any]:
    """Cheap readability gate for teencode/no-accent augmentation."""
    normalized = re.sub(r"[^a-z0-9\s]", " ", _accentless(text))
    tokens = [token for token in normalized.split() if token]
    reasons: list[str] = []
    joined = " ".join(tokens)
    if re.search(r"[\u3400-\u9fff]", str(text or "")):
        reasons.append("input_contains_cjk")
    if re.search(r"[\u0400-\u04ff]", str(text or "")):
        reasons.append("input_contains_cyrillic")
    if any(phrase in joined for phrase in ("mun o mong", "mun o cai mong", "hau mon", "sinh duc")):
        reasons.append("input_out_of_scope_body_area")
    if "gau mun" in joined:
        reasons.append("input_awkward_phrase:gau_mun")
    if input_style not in {"teencode", "no_accent", "typo", "mixed"}:
        passed = not reasons
        return {"passed": passed, "pass": passed, "reasons": reasons}
    if len(tokens) < 6:
        reasons.append("augmented_input_too_short")
    has_verb = any(
        (" " in verb and verb in joined) or (" " not in verb and verb in tokens)
        for verb in _NATURAL_VERBS
    )
    if not has_verb:
        reasons.append("augmented_input_missing_verb")
    if input_style == "typo" and not re.search(
        r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡ"
        r"ùúụủũưừứựửữỳýỵỷỹđ]",
        str(text or ""),
        re.IGNORECASE,
    ):
        reasons.append("typo_style_is_actually_no_accent")
    awkward = ("co can dc ko", "em da kem tron", "o cang thang no")
    if any(phrase in joined for phrase in awkward):
        reasons.append("augmented_input_awkward_phrase")
    repeated = re.search(r"\b([a-z0-9]+)\s+\1\b", joined)
    if repeated:
        reasons.append(f"augmented_input_repeated_word:{repeated.group(1)}")
    if input_style in {"teencode", "mixed"}:
        shorthand = {token for token in tokens if token in _TEENCODE_CANDIDATES}
        unknown = sorted(
            token for token in shorthand
            if token not in _TEENCODE_MARKERS
        )
        unknown.extend(
            token for token in tokens
            if len(token) == 1 and token not in {"a", "e", "o", "k", "j", "z", "r"}
        )
        unknown = sorted(set(unknown))
        if unknown:
            reasons.append("teencode_not_in_whitelist:" + ",".join(unknown))
    passed = not reasons
    return {"passed": passed, "pass": passed, "reasons": reasons}


def output_language_quality_check(text: str) -> dict[str, Any]:
    """Reject cheap but high-signal malformed phrasing in generated answers."""
    normalized = " ".join(_accentless(text).split())
    reasons: list[str] = []
    for phrase in ("minh glad", "cuc nong", "ban vui long qua roi", "vi khu khuan"):
        if phrase in normalized:
            reasons.append(f"awkward_answer_phrase:{phrase}")
    if normalized.startswith(("chao ban", "chao em", "xin chao")):
        reasons.append("answer_starts_with_greeting")
    if any(re.search(r" {2,}", line) for line in str(text or "").splitlines()):
        reasons.append("repeated_internal_whitespace")
    letters = re.findall(r"[A-Za-zÀ-ỹĐđ]", str(text or ""))
    accented = re.findall(
        r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡ"
        r"ùúụủũưừứựửữỳýỵỷỹđ]",
        str(text or ""),
        re.IGNORECASE,
    )
    if len(letters) >= 50 and len(accented) / max(len(letters), 1) < 0.015:
        reasons.append("answer_not_standard_vietnamese")
    passed = not reasons
    return {"passed": passed, "pass": passed, "reasons": reasons}


def case_behavior_check(case_id: str, answer: str) -> dict[str, Any]:
    """Small deterministic contracts for cases whose behavior is structural."""
    reasons: list[str] = []
    normalized = normalize_grounding_text(answer)
    if case_id == "R2":
        treatment_terms = (
            "rua mat", "duong am", "giu da sach", "nan mun", "kem duong",
            "san pham cham soc", "thoa kem", "boi thuoc",
        )
        hits = [term for term in treatment_terms if term in normalized]
        if hits:
            reasons.append("r2_must_adapt_register_without_treatment:" + ",".join(hits))
    if case_id == "R5":
        question_count = str(answer or "").count("?")
        if not 1 <= question_count <= 2:
            reasons.append(f"r5_question_count:{question_count}")
        if any(phrase in normalized for phrase in ("co the la", "co kha nang la", "thuong la")):
            reasons.append("r5_must_clarify_without_differential")
    passed = not reasons
    return {"passed": passed, "pass": passed, "reasons": reasons}


class PhraseFrequencyGuard:
    """Dataset-wide generated-text n-gram frequency guard."""

    def __init__(self, ngram_size: int = 8, max_occurrences: int = 5):
        self.ngram_size = ngram_size
        self.max_occurrences = max_occurrences
        self._counts: Counter[str] = Counter()
        self._examples: dict[str, str] = {}

    def _grams(self, text: str) -> set[str]:
        tokens = normalized_tokens(text, accentless=True)
        return set(iter_ngrams(tokens, self.ngram_size))

    def check(self, text: str) -> dict[str, Any]:
        hits = [
            {"phrase": gram, "existing_count": self._counts[gram]}
            for gram in sorted(self._grams(text))
            if self._counts[gram] >= self.max_occurrences
        ]
        passed = not hits
        return {
            "passed": passed,
            "pass": passed,
            "reasons": [] if passed else ["phrase_frequency_exceeded"],
            "hits": hits[:10],
            "ngram_size": self.ngram_size,
            "max_occurrences": self.max_occurrences,
        }

    def add(self, sample_id: str, text: str) -> None:
        for gram in self._grams(text):
            self._counts[gram] += 1
            self._examples.setdefault(gram, sample_id)

    def violations(self) -> list[dict[str, Any]]:
        return [
            {"phrase": gram, "count": count, "first_sample_id": self._examples.get(gram)}
            for gram, count in self._counts.items()
            if count > self.max_occurrences
        ]


def generated_text(record: dict[str, Any]) -> str:
    """Text subject to diversity checks (never the repeated SYSTEM prompt)."""
    raw_users = [str(value) for value in record.get("raw_user_messages") or []]
    assistants = [
        str(message.get("content") or "")
        for message in record.get("messages") or []
        if isinstance(message, dict) and message.get("role") == "assistant"
    ]
    return "\n".join([*raw_users, *assistants])


def validate_b5_pairs(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Validate complete two-record B5 anchors with same docs and depth contrast."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    reasons: list[str] = []
    for record in records:
        if str(record.get("sample_kind") or "").startswith("B5_"):
            anchor = str(record.get("anchor_group") or "").strip()
            if not anchor:
                reasons.append(f"b5_missing_anchor_group:{record.get('id')}")
            else:
                grouped[anchor].append(record)
    for anchor, rows in sorted(grouped.items()):
        if len(rows) != 2:
            reasons.append(f"b5_anchor_pair_size:{anchor}:{len(rows)}")
            continue
        sources = [json.dumps(row.get("synthetic_context_sources") or [], ensure_ascii=False) for row in rows]
        if sources[0] != sources[1]:
            reasons.append(f"b5_anchor_sources_mismatch:{anchor}")
        depths = {str(row.get("anchor_depth") or "") for row in rows}
        if depths != {"beginner", "advanced"}:
            reasons.append(f"b5_anchor_depth_mismatch:{anchor}")
        users = {"\n".join(str(x) for x in row.get("raw_user_messages") or []) for row in rows}
        if len(users) != 2:
            reasons.append(f"b5_anchor_users_not_distinct:{anchor}")
    passed = not reasons
    return {
        "passed": passed,
        "pass": passed,
        "reasons": reasons,
        "anchor_count": len(grouped),
        "pair_count": sum(len(rows) == 2 for rows in grouped.values()),
    }


class EvaluationNgramIndex:
    """Exact/8-gram index adapted to evaluation-v1's `user_query` schema."""

    def __init__(self, db_path: Path, ngram_size: int = 8):
        self.db_path = Path(db_path)
        self.ngram_size = ngram_size
        self._exact: dict[tuple[str, str], tuple[str, int, str]] = {}
        self._ngrams: dict[tuple[str, str], tuple[str, int, str]] = {}
        self._stats: dict[str, Any] = {"ready": False}

    def __enter__(self) -> "EvaluationNgramIndex":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    @staticmethod
    def _texts_from_row(row: dict[str, Any]) -> list[str]:
        texts: list[str] = []
        query = str(row.get("user_query") or "").strip()
        if query:
            texts.append(query)
        for field in ("conversation_history", "messages"):
            messages = row.get(field) or []
            if not isinstance(messages, list):
                continue
            for message in messages:
                if not isinstance(message, dict) or message.get("role") != "user":
                    continue
                content = str(message.get("content") or "").strip()
                if content:
                    texts.append(content)
        return texts

    def build(self, paths: Sequence[Path], **_: Any) -> dict[str, Any]:
        self._exact.clear()
        self._ngrams.clear()
        rows_seen = 0
        user_texts = 0
        invalid_json = 0
        file_hashes: dict[str, str] = {}
        resolved_paths: list[dict[str, Any]] = []
        for source in paths:
            path = Path(source)
            if not path.is_file():
                raise FileNotFoundError(path)
            hasher = hashlib.sha256()
            resolved_paths.append({
                "path": str(path.resolve()),
                "size": path.stat().st_size,
                "mtime_ns": path.stat().st_mtime_ns,
            })
            with path.open("rb") as handle:
                for line_no, raw_line in enumerate(handle, 1):
                    hasher.update(raw_line)
                    if not raw_line.strip():
                        continue
                    rows_seen += 1
                    try:
                        row = json.loads(raw_line.decode("utf-8-sig"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        invalid_json += 1
                        continue
                    if not isinstance(row, dict):
                        invalid_json += 1
                        continue
                    for text in self._texts_from_row(row):
                        user_texts += 1
                        excerpt = " ".join(text.split())[:320]
                        provenance = (str(path.resolve()), line_no, excerpt)
                        for mode, accentless in (("surface", False), ("accentless", True)):
                            tokens = normalized_tokens(text, accentless=accentless)
                            if not tokens:
                                continue
                            normalized = " ".join(tokens)
                            self._exact.setdefault((mode, normalized), provenance)
                            for gram in set(iter_ngrams(tokens, self.ngram_size)):
                                self._ngrams.setdefault((mode, gram), provenance)
            file_hashes[str(path.resolve())] = hasher.hexdigest()
        self._stats = {
            "ready": True,
            "backend": "evaluation_v1_in_memory",
            "input_signature": {
                "schema_version": 1,
                "ngram_size": self.ngram_size,
                "paths": resolved_paths,
            },
            "train_sha256": file_hashes,
            "rows_seen": rows_seen,
            "user_texts": user_texts,
            "invalid_json_rows": invalid_json,
            "unique_exact_texts": len(self._exact),
            "unique_ngrams": len(self._ngrams),
            "source_texts": user_texts,
            "cache_db": None,
        }
        return dict(self._stats)

    def stats(self) -> dict[str, Any]:
        return dict(self._stats)

    def check(self, text: str, *, max_examples: int = 5) -> list[ContaminationHit]:
        hits: list[ContaminationHit] = []
        for mode, accentless in (("surface", False), ("accentless", True)):
            tokens = normalized_tokens(text, accentless=accentless)
            if not tokens:
                continue
            normalized = " ".join(tokens)
            exact_source = self._exact.get((mode, normalized))
            if exact_source:
                hits.append(ContaminationHit(
                    kind="exact",
                    mode=mode,
                    overlap_count=1,
                    query_ngram_count=max(0, len(tokens) - self.ngram_size + 1),
                    overlap_ratio=1.0,
                    matched_ngrams=[],
                    source_file=exact_source[0],
                    source_line=exact_source[1],
                    source_excerpt=exact_source[2],
                ))
                continue
            grams = list(dict.fromkeys(iter_ngrams(tokens, self.ngram_size)))
            matched = [(gram, self._ngrams[(mode, gram)]) for gram in grams if (mode, gram) in self._ngrams]
            if matched:
                first_source = matched[0][1]
                hits.append(ContaminationHit(
                    kind=f"{self.ngram_size}-gram",
                    mode=mode,
                    overlap_count=len(matched),
                    query_ngram_count=len(grams),
                    overlap_ratio=round(len(matched) / len(grams), 6),
                    matched_ngrams=[gram for gram, _ in matched[:max_examples]],
                    source_file=first_source[0],
                    source_line=first_source[1],
                    source_excerpt=first_source[2],
                ))
        return hits


def load_drug_terms(path: Path | None = None) -> set[str]:
    """Load all active-ingredient, medicine and alias terms from drugs_acne.yaml."""
    source = path or ROOT / "config" / "drugs_acne.yaml"
    payload = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    terms: set[str] = set()
    for drug in payload.get("drugs", []):
        for name in drug.get("names", []):
            normalized = normalized_text(str(name), accentless=True)
            if len(normalized) >= 3:
                terms.add(normalized)
    return terms


def knowledge_leak_check(answer: str, drug_terms: Iterable[str]) -> dict[str, Any]:
    """Reject Group-A answers containing drug names or numeric regimens."""
    normalized = normalized_text(answer, accentless=True)
    term_hits = sorted(
        term for term in set(drug_terms)
        if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", normalized)
    )
    regimen_hits = sorted(set(NUMERIC_REGIMEN_RE.findall(normalized)))
    word_regimens = re.findall(
        r"\b(?:mot|hai|ba|bon|nam|sau)\s+lan(?:\s+(?:(?:moi|mot)\s+(?:ngay|tuan)|sang\s+toi))?\b",
        normalized,
    )
    regimen_hits.extend(value for value in word_regimens if value not in regimen_hits)
    reasons: list[str] = []
    if term_hits:
        reasons.append("drug_or_active_ingredient")
    if regimen_hits:
        reasons.append("numeric_regimen")
    return {
        "passed": not reasons,
        "pass": not reasons,
        "reasons": reasons,
        "drug_term_hits": term_hits,
        "numeric_regimen_hits": regimen_hits,
    }


def scenario_constraint_check(
    case_id: str,
    *,
    raw_users: Sequence[str],
    contexts: Sequence[str],
    answer: str,
    drug_terms: set[str],
) -> dict[str, Any]:
    """Enforce low-risk synthetic-context topics chosen for B2/B4/B5."""
    banned_causal_topics = (
        "hut thuoc",
        "thuoc la",
        "che do an",
        "sua tach beo",
        "hormone",
        "noi tiet",
    )
    context_text = normalized_text(" ".join(contexts), accentless=True)
    all_text = normalized_text(
        " ".join([*raw_users, *contexts, answer]),
        accentless=True,
    )
    topic_scope = all_text if case_id == "B5" else context_text
    banned_hits = sorted(topic for topic in banned_causal_topics if topic in topic_scope)
    b4_knowledge = (
        knowledge_leak_check(" ".join(contexts), drug_terms)
        if case_id == "B4"
        else {"pass": True, "reasons": [], "drug_term_hits": [], "numeric_regimen_hits": []}
    )
    applies = case_id in {"B2", "B4", "B5"}
    reasons: list[str] = []
    if banned_hits:
        reasons.append("banned_causal_topic")
    if not b4_knowledge["pass"]:
        reasons.extend(f"b4_{reason}" for reason in b4_knowledge["reasons"])
    if case_id == "B2":
        safe_topics = {
            "gentle_cleansing": any(value in context_text for value in ("lam sach", "rua mat")) and "diu nhe" in context_text,
            "moisturizer": "duong am" in context_text,
            "non_comedogenic": "khong gay bit tac" in context_text or "khong bit tac" in context_text,
            "no_picking": any(value in context_text for value in ("tranh nan", "khong nan", "tranh cay")),
        }
        if sum(safe_topics.values()) < 2:
            reasons.append("b2_requires_low_risk_context_facts")
        user_text = normalized_text(" ".join(raw_users), accentless=True)
        missing_topics = (
            "che do an", "do ngot", "an ngot", "an nhieu duong", "cat giam duong",
            "cat giam do an ngot", "cat giam do ngot", "thuc khuya", "giac ngu", "stress",
            "anh sang", "spa", "laser", "thuc pham", "sua", "ruou", "thuoc la",
        )
        truly_missing = [
            topic for topic in missing_topics
            if topic in user_text and topic not in context_text
        ]
        if not truly_missing:
            reasons.append("b2_question_answered_by_context")
    if case_id == "B5":
        required = {
            "gentle_cleansing": any(value in context_text for value in ("lam sach", "rua mat")) and "diu nhe" in context_text,
            "moisturizer": "duong am" in context_text,
            "non_comedogenic": "khong gay bit tac" in context_text or "khong bit tac" in context_text,
            "no_picking": bool(re.search(r"(?:tranh|khong)\s+(?:tu\s+)?(?:nan|cay)", context_text)),
        }
        for name, present in required.items():
            if not present:
                reasons.append(f"b5_missing_context_fact:{name}")
    passed = (not applies) or not reasons
    return {
        "passed": passed,
        "pass": passed,
        "reasons": reasons,
        "applies": applies,
        "banned_causal_topic_hits": banned_hits,
        "b4_drug_or_regimen_check": b4_knowledge,
    }


def validate_record(record: dict[str, Any], expected_system: str | None = None) -> list[str]:
    """Validate the public JSONL record contract and conversation shape."""
    errors: list[str] = []
    missing = sorted(REQUIRED_FIELDS - set(record))
    if missing:
        errors.append("missing_fields:" + ",".join(missing))
    if record.get("input_style") not in VALID_INPUT_STYLES:
        errors.append("invalid_input_style")
    if not isinstance(record.get("synthetic_context"), bool):
        errors.append("synthetic_context_must_be_bool")
    messages = record.get("messages")
    if not isinstance(messages, list) or len(messages) < 3:
        errors.append("messages_must_include_system_user_assistant")
        return errors
    if any(
        not isinstance(message, dict)
        or message.get("role") not in {"system", "user", "assistant"}
        or not str(message.get("content") or "").strip()
        for message in messages
    ):
        errors.append("invalid_message")
    if messages[0].get("role") != "system":
        errors.append("first_message_must_be_system")
    if expected_system is not None and messages[0].get("content") != expected_system:
        errors.append("system_prompt_not_verbatim")
    body_roles = [message.get("role") for message in messages[1:]]
    expected_roles = ["user" if index % 2 == 0 else "assistant" for index in range(len(body_roles))]
    if body_roles != expected_roles or body_roles[-1:] != ["assistant"]:
        errors.append("messages_must_alternate_and_end_assistant")
    if str(record.get("sample_kind", "")).startswith("R9_"):
        user_turns = body_roles.count("user")
        if not 4 <= user_turns <= 6:
            errors.append("r9_requires_4_to_6_user_turns")
    elif len(messages) != 3:
        errors.append("non_r9_requires_single_pair")
    return errors


def _salient_fact_misses(answer: str, contexts: Sequence[str], drug_terms: set[str]) -> list[str]:
    """Find drug/regimen strings in an answer that do not occur in its context."""
    answer_norm = normalized_text(answer, accentless=True)
    context_norm = normalized_text(" ".join(contexts), accentless=True)
    misses: list[str] = []
    for term in drug_terms:
        if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", answer_norm) and not re.search(
            rf"(?<!\w){re.escape(term)}(?!\w)", context_norm
        ):
            misses.append(term)
    for hit in NUMERIC_REGIMEN_RE.findall(answer_norm):
        if hit not in context_norm:
            misses.append(hit)
    return sorted(set(misses))


def _score_without_rule_boilerplate(answer: str, contexts: Sequence[str]) -> dict[str, Any]:
    sentences = split_vietnamese_sentences(answer)
    evidence_sentences: list[str] = []
    for sentence in sentences:
        normalized = normalize_grounding_text(sentence)
        fixed_boilerplate = any(pattern in normalized for pattern in _BOILERPLATE_PATTERNS)
        doctor_direction = "bac si" in normalized and any(
            action in normalized for action in ("hoi", "kham", "tu van", "trao doi", "mang theo cau hoi")
        )
        source_conflict_control = (
            any(reference in normalized for reference in ("nguon", "tai lieu", "huong dan"))
            and any(pattern in normalized for pattern in _CONFLICT_PATTERNS)
        )
        if not (fixed_boilerplate or doctor_direction or source_conflict_control):
            evidence_sentences.append(sentence)
    if not evidence_sentences:
        return {
            "grounded_sentence_rate": None,
            "eligible_sentence_count": 0,
            "unsupported_sentences": [],
            "sentence_scores": [],
        }
    return grounding_scorer().score("\n".join(evidence_sentences), list(contexts))


def grounded_role_check(answer: str, contexts: Sequence[str]) -> dict[str, Any]:
    result = grounding_scorer().score(answer, list(contexts))
    rate = result.get("grounded_sentence_rate")
    answer_norm = normalize_grounding_text(answer)
    context_norm = normalize_grounding_text(" ".join(contexts))
    salient_misses: list[str] = []
    for token in ("ph", "hang rao bao ve", "tiet nhieu ba nhon hon", "cham tay"):
        if token in answer_norm and token not in context_norm:
            salient_misses.append(token)
    result["salient_fact_misses"] = salient_misses
    result["pass"] = rate is not None and rate >= 0.8 and not salient_misses
    result["passed"] = result["pass"]
    reasons: list[str] = []
    if rate is None or rate < 0.8:
        reasons.append("grounding_rate_below_0.8")
    if salient_misses:
        reasons.append("salient_fact_not_in_context")
    result["reasons"] = reasons
    result["required_rate"] = 0.8
    return result


def _input_style_check(style: str, raw_users: Sequence[str]) -> dict[str, Any]:
    text = " ".join(raw_users)
    accent_chars = re.compile(
        r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡ"
        r"ùúụủũưừứựửữỳýỵỷỹđ]",
        re.IGNORECASE,
    )
    teencode = re.compile(r"(?<!\w)(?:k|ko|dc|đc|j|z|bt|mk)(?!\w)", re.IGNORECASE)
    reasons: list[str] = []
    if style == "teencode" and not teencode.search(text):
        reasons.append("missing_teencode_marker")
    elif style == "no_accent" and accent_chars.search(text):
        reasons.append("no_accent_contains_diacritic")
    elif style == "mixed" and not (teencode.search(text) or not accent_chars.search(text)):
        reasons.append("missing_mixed_style_marker")
    passed = not reasons
    return {"passed": passed, "pass": passed, "reasons": reasons}


def apply_rules(
    record: dict[str, Any],
    *,
    case_id: str,
    raw_users: Sequence[str],
    production_system: str,
    drug_terms: set[str],
    duplicate_guard: DuplicateGuard,
    contamination_index: EvaluationNgramIndex,
    phrase_guard: PhraseFrequencyGuard,
    structural_errors: Sequence[str] = (),
) -> dict[str, Any]:
    """Apply every inline gate and expose the LLMData ``passed/reasons`` contract."""
    answer_messages = [
        str(message.get("content") or "")
        for message in record.get("messages") or []
        if isinstance(message, dict) and message.get("role") == "assistant"
    ]
    answer = "\n".join(answer_messages)
    raw_text = "\n".join(str(value) for value in raw_users)
    contexts = list(record.get("synthetic_context_sources") or [])
    style = str(record.get("input_style") or "standard")

    details: dict[str, Any] = {
        "structure": {
            "passed": not structural_errors,
            "pass": not structural_errors,
            "reasons": list(structural_errors),
        },
        "format": {
            "passed": True,
            "pass": True,
            "reasons": validate_record(record, production_system),
        },
        "input_style": _input_style_check(style, raw_users),
        "naturalness": {
            "passed": True,
            "pass": True,
            "reasons": [],
        },
        "answer_language_quality": output_language_quality_check(answer),
        "case_behavior": case_behavior_check(case_id, answer),
        "code_switch": standard_code_switch_check(
            "\n".join([raw_text, answer]), input_style=style
        ),
        "vocative_consistency": {
            "passed": True,
            "pass": True,
            "reasons": [],
        },
        "contamination": {
            "passed": True,
            "pass": True,
            "reasons": [],
            "hits": contamination_hits(contamination_index, raw_text),
            "ngram_size": 8,
        },
        "dedupe": {
            "passed": True,
            "pass": True,
            "reasons": [],
            "hit": duplicate_guard.check(raw_text),
        },
        "phrase_frequency": phrase_guard.check(generated_text(record)),
        "scenario_constraints": scenario_constraint_check(
            case_id,
            raw_users=raw_users,
            contexts=contexts,
            answer=answer,
            drug_terms=drug_terms,
        ),
    }
    details["format"]["passed"] = details["format"]["pass"] = not details["format"]["reasons"]
    natural_reasons: list[str] = []
    for raw_user in raw_users:
        natural_reasons.extend(input_naturalness_check(raw_user, style)["reasons"])
    details["naturalness"]["reasons"] = list(dict.fromkeys(natural_reasons))
    details["naturalness"]["passed"] = details["naturalness"]["pass"] = not natural_reasons

    vocative_reasons: list[str] = []
    for user, assistant in zip(raw_users, answer_messages):
        vocative_reasons.extend(vocative_consistency_check(user, assistant)["reasons"])
    details["vocative_consistency"]["reasons"] = list(dict.fromkeys(vocative_reasons))
    details["vocative_consistency"]["passed"] = details["vocative_consistency"]["pass"] = not vocative_reasons

    if details["contamination"]["hits"]:
        details["contamination"]["passed"] = details["contamination"]["pass"] = False
        details["contamination"]["reasons"] = ["evaluation_contamination"]
    if details["dedupe"]["hit"] is not None:
        details["dedupe"]["passed"] = details["dedupe"]["pass"] = False
        details["dedupe"]["reasons"] = ["internal_duplicate"]

    if case_id.startswith("R"):
        details["knowledge_leak"] = knowledge_leak_check(answer, drug_terms)
        details["knowledge_leak"]["passed"] = details["knowledge_leak"]["pass"]
        record["knowledge_leak_check"] = (
            "pass" if details["knowledge_leak"]["pass"] else "fail"
        )
    elif case_id in {"B1", "B3", "B5"}:
        details["grounding"] = grounded_role_check(answer, contexts)
        details["grounding"]["passed"] = details["grounding"]["pass"]
        details["grounding"].setdefault("reasons", [] if details["grounding"]["pass"] else ["grounding_rate_below_0.8"])
        record["grounded_sentence_rate"] = details["grounding"].get("grounded_sentence_rate")
    elif case_id == "B2":
        details["missing_answer_rule"] = missing_answer_rule_check(answer, contexts, drug_terms)
        details["missing_answer_rule"]["passed"] = details["missing_answer_rule"]["pass"]
        details["missing_answer_rule"].setdefault("reasons", [] if details["missing_answer_rule"]["pass"] else ["missing_answer_rule_failed"])
    elif case_id == "B4":
        details["conflict_rule"] = conflict_rule_check(answer, contexts, drug_terms)
        details["conflict_rule"]["passed"] = details["conflict_rule"]["pass"]
        details["conflict_rule"].setdefault("reasons", [] if details["conflict_rule"]["pass"] else ["conflict_rule_failed"])

    reasons: list[str] = []
    for gate_name, gate in details.items():
        if not isinstance(gate, dict):
            continue
        gate_passed = bool(gate.get("passed", gate.get("pass", True)))
        if gate_passed:
            continue
        gate_reasons = gate.get("reasons") or ["failed"]
        reasons.extend(f"{gate_name}::{reason}" for reason in gate_reasons)
    reasons = list(dict.fromkeys(reasons))
    passed = not reasons
    return {"passed": passed, "pass": passed, "reasons": reasons, **details}


def missing_answer_rule_check(
    answer: str,
    contexts: Sequence[str],
    drug_terms: set[str],
) -> dict[str, Any]:
    normalized = normalize_grounding_text(answer)
    evidence = _score_without_rule_boilerplate(answer, contexts)
    evidence_rate = evidence.get("grounded_sentence_rate")
    salient_misses = _salient_fact_misses(answer, contexts, drug_terms)
    states_missing = any(pattern in normalized for pattern in _MISSING_PATTERNS)
    evidence_ok = evidence_rate is None or evidence_rate >= 0.8
    reasons: list[str] = []
    if not states_missing:
        reasons.append("missing_abstention_phrase")
    if not evidence_ok:
        reasons.append("unsupported_evidence")
    if salient_misses:
        reasons.append("salient_fact_not_in_context")
    passed = not reasons
    return {
        "passed": passed,
        "pass": passed,
        "reasons": reasons,
        "states_missing": states_missing,
        "evidence_grounding": evidence,
        "salient_fact_misses": salient_misses,
    }


def conflict_rule_check(
    answer: str,
    contexts: Sequence[str],
    drug_terms: set[str],
) -> dict[str, Any]:
    normalized = normalize_grounding_text(answer)
    evidence = _score_without_rule_boilerplate(answer, contexts)
    evidence_rate = evidence.get("grounded_sentence_rate")
    salient_misses = _salient_fact_misses(answer, contexts, drug_terms)
    mentions_both = "nguon 1" in normalized and "nguon 2" in normalized
    states_conflict = any(pattern in normalized for pattern in _CONFLICT_PATTERNS)
    escalates = any(pattern in normalized for pattern in _ESCALATION_PATTERNS)
    evidence_ok = evidence_rate is None or evidence_rate >= 0.8
    reasons: list[str] = []
    if not mentions_both:
        reasons.append("does_not_mention_both_sources")
    if not states_conflict:
        reasons.append("does_not_state_conflict")
    if not escalates:
        reasons.append("does_not_escalate")
    if not evidence_ok:
        reasons.append("unsupported_evidence")
    if salient_misses:
        reasons.append("salient_fact_not_in_context")
    passed = not reasons
    return {
        "passed": passed,
        "pass": passed,
        "reasons": reasons,
        "mentions_both_sources": mentions_both,
        "states_conflict": states_conflict,
        "escalates": escalates,
        "evidence_grounding": evidence,
        "salient_fact_misses": salient_misses,
    }


def contamination_hits(index: EvaluationNgramIndex, user_text: str) -> list[dict[str, Any]]:
    return [asdict(hit) for hit in index.check(user_text)]


def assistant_text(record: dict[str, Any]) -> str:
    return "\n".join(
        str(message.get("content") or "")
        for message in record.get("messages", [])
        if isinstance(message, dict) and message.get("role") == "assistant"
    )


def audit_record(record: dict[str, Any], drug_terms: set[str] | None = None) -> dict[str, Any]:
    """Standalone audit for an already generated record (no cross-record gates)."""
    terms = drug_terms or load_drug_terms()
    kind = str(record.get("sample_kind") or "")
    answer = assistant_text(record)
    contexts = list(record.get("synthetic_context_sources") or [])
    result: dict[str, Any] = {"format_errors": validate_record(record)}
    if kind.startswith("R"):
        result["knowledge_leak"] = knowledge_leak_check(answer, terms)
    elif kind.startswith(("B1_", "B3_", "B5_")):
        result["grounding"] = grounded_role_check(answer, contexts)
    elif kind.startswith("B2_"):
        result["missing_answer_rule"] = missing_answer_rule_check(answer, contexts, terms)
    elif kind.startswith("B4_"):
        result["conflict_rule"] = conflict_rule_check(answer, contexts, terms)
    result["pass"] = not result["format_errors"] and all(
        value.get("pass", True)
        for value in result.values()
        if isinstance(value, dict)
    )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsonl", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    failed = 0
    for line_no, line in enumerate(args.jsonl.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        record = json.loads(line)
        result = audit_record(record)
        if not result["pass"]:
            failed += 1
        print(json.dumps({"line": line_no, "id": record.get("id"), **result}, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
