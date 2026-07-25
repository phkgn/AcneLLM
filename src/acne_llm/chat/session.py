"""Conversation session store for multi-turn chat memory.

Design goals:
- Zero external dependency: in-memory only (dict + threading.Lock).
- Backward-compatible: session_id=None → all calls are no-ops, behavior
  identical to before this module existed.
- Lightweight: only plain dataclasses, no Pydantic, no DB.
- TTL-based expiry: sessions idle > SESSION_TTL seconds are dropped lazily
  on the next read/write to that session.
- Thread-safe: a single RLock guards all mutations.

Usage in runtime.py:
    store = get_session_store()          # module-level singleton
    history = store.get_history(sid)     # list[ConversationTurn], may be []
    store.append_turn(sid, turn)
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Literal

from ..schemas import AcneClinicalInput, UserContext, UserInput

# NOTE: defined here (not in guardrails.runner) to avoid circular import
_GENITAL_FILTER_TERMS = (
    "bìu", "biu", "dương vật", "duong vat", "sinh dục", "sinh duc",
    "âm đạo", "am dao", "âm hộ", "am ho", "hậu môn", "hau mon",
    "vùng kín", "vung kin", "bộ phận sinh dục",
)


# ── Constants ────────────────────────────────────────────────────────────────

SESSION_TTL: float = 1800.0        # seconds idle before session expires
MAX_HISTORY_TURNS: int = 6         # keep last N turns (0 = unlimited)
SESSION_SCHEMA_VERSION: int = 2
# Nguồn sự thật duy nhất cho ngân sách ký tự lịch sử.
HISTORY_CHAR_BUDGET: int = 2000    # ~570 tokens; prompt thực đo được 828 tokens / ctx 3072
FIRST_TURN_BUDGET: int = 0         # first-turn anchoring was removed in schema v2

# Nguồn sự thật duy nhất cho cửa sổ lịch sử đưa vào prompt.
HISTORY_WINDOW_TURNS: int = 6      # 3 lượt hỏi-đáp; budget chars mới là giới hạn thật


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class NormalizedSnapshot:
    """Structured facts extracted from one user turn.

    Stored beside the raw/clean turn text so later turns can fold memory
    without re-running regex normalization over the whole history.
    """
    context: dict = field(default_factory=dict)
    clinical: dict = field(default_factory=dict)
    clean_text: str = ""


@dataclass
class ConversationTurn:
    role: Literal["user", "assistant"]
    content: str                            # raw text of the turn
    timestamp: float = field(default_factory=time.time)
    mode: str = "hybrid"                    # pipeline mode that produced this turn
    used_chunks: list[str] = field(default_factory=list)
    normalized_snapshot: NormalizedSnapshot | None = None
    metadata: dict = field(default_factory=dict)
    # ── Intent routing fields ────────────────────────────────────────────────
    # Typed fields cho intent data — dễ query hơn metadata dict chung chung.
    intent_label: str = ""          # "advise" | "knowledge" | "clarify" | "reject" | ""
    intent_confidence: float = 0.0
    turn_type: str = ""             # "answer" | "clarify" | "reject" | "safety_clarify" | ...


@dataclass
class Session:
    session_id: str
    turns: list[ConversationTurn] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    # Accumulated user context across turns (age, skin_type, etc.)
    # Populated by callers; never overwritten, only merged.
    user_context: dict = field(default_factory=dict)
    # Tracks which follow-up fields have already been asked to avoid repeating.
    # e.g. {"lesion_types", "distribution", "duration_weeks"}
    asked_fields: set = field(default_factory=set)
    # ── Session-level intent tracking (task #6) ──────────────────────────────
    last_intent: str = ""           # intent label của turn user gần nhất
    total_clarify_count: int = 0    # số lần bot hỏi clarify trong session này
    accumulated_clinical_score: float = 0.0  # tổng score completeness tích lũy
    schema_version: int = SESSION_SCHEMA_VERSION

    def is_expired(self, ttl: float = SESSION_TTL) -> bool:
        return (time.time() - self.last_active) > ttl

    def touch(self) -> None:
        self.last_active = time.time()


# ── Store ────────────────────────────────────────────────────────────────────

class SessionStore:
    """Thread-safe in-memory session store.

    All public methods are no-ops when session_id is None or empty, which
    preserves the pre-history behavior of the chat pipeline exactly.
    """

    def __init__(
        self,
        ttl: float = SESSION_TTL,
        max_turns: int = MAX_HISTORY_TURNS,
    ) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.RLock()
        self.ttl = ttl
        self.max_turns = max_turns

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _is_valid_sid(self, session_id: str | None) -> bool:
        return bool(session_id and session_id.strip())

    def _expire_if_stale(self, session_id: str) -> bool:
        """Remove session if TTL exceeded. Returns True if removed."""
        sess = self._sessions.get(session_id)
        if sess is not None and sess.is_expired(self.ttl):
            del self._sessions[session_id]
            return True
        return False

    # ── Public API ────────────────────────────────────────────────────────────

    def get_or_create(self, session_id: str | None) -> Session | None:
        """Return existing session (if live) or create a new one.

        Returns None when session_id is falsy.
        """
        if not self._is_valid_sid(session_id):
            return None
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            self._expire_if_stale(sid)
            if sid not in self._sessions:
                self._sessions[sid] = Session(session_id=sid)
            sess = self._sessions[sid]
            sess.touch()
            return sess

    def get_history(self, session_id: str | None) -> list[ConversationTurn]:
        """Return the last max_turns turns for this session, oldest first.

        Returns [] when session_id is falsy or session does not exist / expired.
        """
        if not self._is_valid_sid(session_id):
            return []
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            self._expire_if_stale(sid)
            sess = self._sessions.get(sid)
            if sess is None:
                return []
            sess.touch()
            if self.max_turns and self.max_turns > 0:
                return list(sess.turns[-self.max_turns :])
            return list(sess.turns)

    def append_turn(
        self,
        session_id: str | None,
        turn: ConversationTurn,
    ) -> None:
        """Append a turn to the session's history.

        No-op when session_id is falsy.
        Cũng tự động populate typed intent fields từ metadata nếu chưa set.
        """
        if not self._is_valid_sid(session_id):
            return
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            self._expire_if_stale(sid)
            if sid not in self._sessions:
                self._sessions[sid] = Session(session_id=sid)
            sess = self._sessions[sid]

            # Populate typed intent fields từ metadata (backward-compat với code cũ)
            if turn.role == "user" and turn.metadata:
                if not turn.intent_label:
                    turn.intent_label = str(turn.metadata.get("primary_intent", ""))
                if not turn.intent_confidence:
                    turn.intent_confidence = float(turn.metadata.get("intent_confidence", 0.0))
                if not turn.turn_type:
                    turn.turn_type = str(turn.metadata.get("turn_type", ""))

            # Cập nhật session-level counters
            if turn.role == "user" and turn.intent_label:
                sess.last_intent = turn.intent_label
            if turn.role == "assistant" and turn.mode == "clarify":
                sess.total_clarify_count += 1

            sess.turns.append(turn)
            # Keep only the last max_turns when an explicit bound is configured.
            if self.max_turns and self.max_turns > 0 and len(sess.turns) > self.max_turns:
                sess.turns = sess.turns[-self.max_turns :]
            sess.touch()

    def merge_user_context(
        self,
        session_id: str | None,
        context: dict,
    ) -> None:
        """Update confirmed profile with latest explicit values."""
        if not self._is_valid_sid(session_id) or not context:
            return
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            sess = self._sessions.get(sid)
            if sess is None:
                return
            for k, v in context.items():
                if v is not None:
                    sess.user_context[k] = v

    def get_user_context(self, session_id: str | None) -> dict:
        """Return accumulated user context for session. Returns {} if not found."""
        if not self._is_valid_sid(session_id):
            return {}
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            sess = self._sessions.get(sid)
            return dict(sess.user_context) if sess else {}

    def get_asked_fields(self, session_id: str | None) -> set:
        """Return the set of follow-up fields already asked for this session."""
        if not self._is_valid_sid(session_id):
            return set()
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            sess = self._sessions.get(sid)
            return set(sess.asked_fields) if sess else set()

    def mark_fields_asked(self, session_id: str | None, fields: list[str]) -> None:
        """Record that these follow-up fields have been asked, to avoid repetition."""
        if not self._is_valid_sid(session_id) or not fields:
            return
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            sess = self._sessions.get(sid)
            if sess is not None:
                sess.asked_fields.update(fields)

    def increment_followup_count(self, session_id: str | None, amount: float = 1.0) -> None:
        """Increment accumulated follow-up/progress score for this session."""
        if not self._is_valid_sid(session_id):
            return
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            sess = self._sessions.get(sid)
            if sess is not None:
                sess.accumulated_clinical_score += float(amount)

    def delete(self, session_id: str | None) -> None:
        """Explicitly remove a session (e.g. on user logout)."""
        if not self._is_valid_sid(session_id):
            return
        sid = session_id.strip()  # type: ignore[union-attr]
        with self._lock:
            self._sessions.pop(sid, None)

    def active_count(self) -> int:
        """Return number of non-expired sessions (for metrics/debug)."""
        with self._lock:
            now = time.time()
            return sum(
                1 for s in self._sessions.values()
                if (now - s.last_active) <= self.ttl
            )


# ── Module-level singleton ────────────────────────────────────────────────────

_store: SessionStore | None = None
_store_lock = threading.Lock()


def get_session_store() -> SessionStore:
    """Return the process-wide SessionStore singleton (lazy init)."""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = SessionStore()
    return _store



def select_relevant_history(
    message: str,
    primary_intent: str,
    history: list[ConversationTurn],
    route_flags: list[str] | None = None,
) -> list[ConversationTurn]:
    """Return a recent window of in-scope turns for the answer prompt.

    Không đoán "đây có phải follow-up không" bằng whitelist tiền tố nữa: mọi
    câu trần thuật ("đã thử X rồi vẫn không đỡ") đều trượt whitelist và làm
    prompt mất sạch ngữ cảnh. format_history_block() đã cắt theo
    HISTORY_CHAR_BUDGET nên gửi cả cửa sổ là an toàn.
    """
    del message, route_flags
    filtered = [turn for turn in history if not _is_genital_turn(turn)]
    window = filtered[-HISTORY_WINDOW_TURNS:]
    if primary_intent == "knowledge":
        # Knowledge trả lời từ RAG: giữ prose cũ của bot ra ngoài prompt, và chỉ
        # lấy user turn gần nhất để giải đại từ ("loại này") mà không kéo cả
        # case cá nhân vào retrieval query.
        # ponytail: turn cá nhân tự đứng được vẫn lọt vào query, làm loãng match.
        # Cần intaker phát tín hiệu "referential" thay vì đoán bằng keyword.
        previous_user = next(
            (turn for turn in reversed(window) if turn.role == "user"), None
        )
        return [previous_user] if previous_user is not None else []
    return window


def build_confirmed_profile(
    existing: dict,
    extraction_confidence: object | None,
    clean_text: str,
    threshold: float = 0.82,
) -> dict:
    """Apply only high-confidence, explicit and stable facts to a profile.

    Clinical descriptors intentionally never enter this structure. Latest
    explicit scalar wins; explicit stop phrases remove products/medications.
    """
    profile = dict(existing or {})
    if extraction_confidence is None:
        return profile

    for field_name in ("age", "sex", "is_pregnant", "is_breastfeeding"):
        result = getattr(extraction_confidence, field_name, None)
        if result is not None and getattr(result, "value", None) is not None:
            if float(getattr(result, "confidence", 0.0)) >= threshold:
                profile[field_name] = result.value

    for result_name, profile_name in (
        ("allergies", "allergies"),
        ("products", "current_products"),
        ("medications", "medications"),
    ):
        result = getattr(extraction_confidence, result_name, None)
        current = list(profile.get(profile_name) or [])
        current = [value for value in current if not _mentions_stop(clean_text, str(value))]
        confident = (
            result.confident_values(threshold)
            if result is not None and hasattr(result, "confident_values")
            else []
        )
        for value in confident:
            if not _mentions_stop(clean_text, str(value)) and value not in current:
                current.append(value)
        profile[profile_name] = current
    return profile


# ── Normalized memory helpers ────────────────────────────────────────────────

def _dedupe_values(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        value = str(item).strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def snapshot_from_user(user: UserInput, clean_text: str = "") -> NormalizedSnapshot:
    """Create a compact, serializable-ish snapshot from a normalized UserInput."""
    context = user.context.model_dump(exclude_none=True)
    clinical = user.clinical.model_dump() if user.clinical is not None else {}
    context["current_products"] = [
        value for value in context.get("current_products", [])
        if not _mentions_stop(clean_text, value)
    ]
    context["medications"] = [
        value for value in context.get("medications", [])
        if not _mentions_stop(clean_text, value)
    ]
    if clinical:
        clinical["medication_history"] = [
            value for value in clinical.get("medication_history", [])
            if not _mentions_stop(clean_text, value)
        ]
        clinical["skincare_products"] = [
            value for value in clinical.get("skincare_products", [])
            if not _mentions_stop(clean_text, value)
        ]
    return NormalizedSnapshot(context=context, clinical=clinical, clean_text=clean_text)


_NEGATE_PREGNANCY_TERMS = (
    "không mang thai", "khong mang thai", "không có thai", "khong co thai",
    "không bầu", "khong bau", "đã sinh", "da sinh", "sau sinh",
)
_NEGATE_BREASTFEEDING_TERMS = (
    "không cho con bú", "khong cho con bu", "cai sữa", "cai sua",
    "ngưng cho bú", "ngung cho bu", "ngừng cho bú", "ngung cho bu",
)
_STOP_PRODUCT_TERMS = (
    "ngưng", "ngừng", "dừng", "không dùng", "khong dung", "bỏ",
    "không phải", "khong phai", "nói nhầm", "noi nham",
)


def _mentions_stop(clean_text: str, value: str) -> bool:
    lowered = clean_text.lower()
    value_lower = value.lower()
    aliases = {
        "salicylic_acid": ("salicylic acid", "bha"),
        "benzoyl_peroxide": ("benzoyl peroxide", "bpo"),
        "adapalene": ("adapalene", "differin"),
    }
    # Intaker canonical hoá ra "salicylic acid" (dấu cách) nhưng aliases lại key
    # bằng "salicylic_acid" -> nhánh alias chưa từng khớp dữ liệu thật, nên
    # "tôi ngưng BHA" không bao giờ gỡ được salicylic acid khỏi profile.
    alias_key = value_lower.replace(" ", "_")
    mentioned = next(
        (term for term in aliases.get(alias_key, (value_lower,)) if term in lowered),
        None,
    )
    if mentioned is None:
        return False
    pos = lowered.find(mentioned)
    before = lowered[max(0, pos - 40):pos]
    return any(term in before for term in _STOP_PRODUCT_TERMS)


_SEVERITY_ORDER = {"unknown": 0, "none": 0, "mild": 1, "moderate": 2, "severe": 3}


def _max_severity(a: str | None, b: str | None) -> str | None:
    """Trả về mức severity cao hơn giữa a và b."""
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return a if _SEVERITY_ORDER.get(a, 0) >= _SEVERITY_ORDER.get(b, 0) else b


def fold_history_facts(
    current: UserInput,
    history: list[ConversationTurn],
) -> UserInput:
    """Fold prior normalized snapshots into the current user.

    Strategy:
    - stable identity facts: first write wins (age, sex, skin_type);
    - pregnancy/breastfeeding: current turn wins; history only fills in khi
      current turn không mention (tránh contaminate từ turn khác session);
    - inflammation: lấy max severity giữa current và history (không downgrade);
    - products/medications: union, with simple stop-word removal on later turns;
    - allergies and clinical descriptors: union.
    """
    # Chỉ lấy snapshot từ user turns (assistant turns không có normalized_snapshot).
    # _is_genital_turn lọc cả assistant turns trong format_history_block() để tránh
    # history poisoning trong prompt — nhưng ở đây chỉ cần lọc user turns vì
    # snapshot chỉ được tạo từ user input (xem snapshot_from_user).
    snapshots = [
        turn.normalized_snapshot for turn in history
        if turn.role == "user"
        and turn.normalized_snapshot is not None
        and not _is_genital_turn(turn)
    ]
    if not snapshots:
        return current

    age = current.context.age
    sex = current.context.sex
    skin_type = current.context.skin_type
    duration_weeks = current.context.duration_weeks
    # Ghi nhận xem turn HIỆN TẠI có explicitly set pregnancy/breastfeeding không.
    # Nếu current turn đã True → không cần fold từ history (giữ nguyên).
    # Nếu current turn là False → chỉ fold từ history khi current turn không
    #   mention pregnancy/breastfeeding gì cả (tức là không negation, không positive).
    _current_text_lower = current.description.lower()
    _current_mentions_pregnant = any(
        t in _current_text_lower
        for t in ("mang thai", "có thai", "bầu", "pregnant", "pregnancy")
    )
    _current_mentions_breastfeed = any(
        t in _current_text_lower
        for t in ("cho con bú", "cho con bu", "đang bú", "breastfeed", "lactating")
    )
    is_pregnant = current.context.is_pregnant
    is_breastfeeding = current.context.is_breastfeeding
    allergies = list(current.context.allergies)
    # Current-turn corrections are tombstones. Normalization may still extract
    # the corrected-away name (for example "không phải doxycycline"), so drop
    # it before replaying prior facts and again after replay.
    products = [
        value for value in current.context.current_products
        if not _mentions_stop(current.description, value)
    ]
    medications = [
        value for value in current.context.medications
        if not _mentions_stop(current.description, value)
    ]

    lesion_types = list(current.clinical.lesion_types) if current.clinical else []
    distribution = list(current.clinical.lesion_distribution) if current.clinical else []
    inflammation = current.clinical.inflammation_level if current.clinical else None
    scarring = list(current.clinical.scarring_signs) if current.clinical else []
    med_history = list(current.clinical.medication_history) if current.clinical else []
    hormonal = list(current.clinical.hormonal_factors) if current.clinical else []
    skincare = list(current.clinical.skincare_products) if current.clinical else []
    canonical_ingredients = list(current.clinical.canonical_ingredients) if current.clinical else []
    usage_frequencies = list(current.clinical.usage_frequencies) if current.clinical else []
    concentrations = list(current.clinical.concentrations) if current.clinical else []
    goals = list(current.clinical.treatment_goals) if current.clinical else []
    red_flags = list(current.clinical.red_flags_input) if current.clinical else []

    current_has_age = current.context.age is not None
    current_has_sex = bool(current.context.sex)
    current_has_skin_type = bool(current.context.skin_type)
    current_has_duration = current.context.duration_weeks is not None

    # Replay oldest -> newest so later corrections/tombstones dominate earlier
    # facts. Reversed replay was the source of corrected medication resurrection.
    for snap in snapshots:
        ctx = snap.context or {}
        clean = (snap.clean_text or "").lower()

        if not current_has_age and ctx.get("age") is not None:
            age = ctx.get("age")
        if not current_has_sex and ctx.get("sex"):
            sex = ctx.get("sex")
        if not current_has_skin_type and ctx.get("skin_type"):
            skin_type = ctx.get("skin_type")
        if not current_has_duration and ctx.get("duration_weeks") is not None:
            duration_weeks = ctx.get("duration_weeks")

        # Pregnancy: chỉ fold từ history khi current turn KHÔNG mention pregnancy.
        # Tránh inject "mang thai" từ turn cũ vào session của người dùng mới hoặc
        # người dùng đã hỏi về chủ đề khác không liên quan đến thai kỳ.
        if not _current_mentions_pregnant:
            if any(term in clean for term in _NEGATE_PREGNANCY_TERMS):
                is_pregnant = False
            elif ctx.get("is_pregnant") and not is_pregnant:
                is_pregnant = True

        if not _current_mentions_breastfeed:
            if any(term in clean for term in _NEGATE_BREASTFEEDING_TERMS):
                is_breastfeeding = False
            elif ctx.get("is_breastfeeding") and not is_breastfeeding:
                is_breastfeeding = True

        allergies.extend(ctx.get("allergies") or [])
        products = [value for value in products if not _mentions_stop(clean, value)]
        medications = [value for value in medications if not _mentions_stop(clean, value)]
        med_history = [value for value in med_history if not _mentions_stop(clean, value)]
        for value in ctx.get("current_products") or []:
            if _mentions_stop(clean, value):
                products = [p for p in products if p.lower() != value.lower()]
            else:
                products.append(value)
        for value in ctx.get("medications") or []:
            if _mentions_stop(clean, value):
                medications = [m for m in medications if m.lower() != value.lower()]
            else:
                medications.append(value)

        clinical = snap.clinical or {}
        snapshot_topic_shift = any(marker in clean for marker in (
            "không phải ở", "khong phai o", "câu này tôi hỏi về",
            "cau nay toi hoi ve", "chuyển sang", "chuyen sang",
            "nói nhầm", "noi nham",
        ))
        if snapshot_topic_shift:
            if clinical.get("lesion_distribution"):
                distribution = []
            if clinical.get("lesion_types"):
                lesion_types = []
        lesion_types.extend(clinical.get("lesion_types") or [])
        distribution.extend(clinical.get("lesion_distribution") or [])
        # Inflammation: lấy max severity, không downgrade (moderate → mild là sai).
        history_infl = clinical.get("inflammation_level")
        inflammation = _max_severity(inflammation, history_infl)
        scarring.extend(clinical.get("scarring_signs") or [])
        med_history.extend(clinical.get("medication_history") or [])
        hormonal.extend(clinical.get("hormonal_factors") or [])
        skincare.extend(clinical.get("skincare_products") or [])
        canonical_ingredients.extend(clinical.get("canonical_ingredients") or [])
        usage_frequencies.extend(clinical.get("usage_frequencies") or [])
        concentrations.extend(clinical.get("concentrations") or [])
        goals.extend(clinical.get("treatment_goals") or [])
        red_flags.extend(clinical.get("red_flags_input") or [])

    # Apply current-turn tombstones last so an older snapshot cannot resurrect
    # a product/medication that the user explicitly removed or corrected.
    products = [value for value in products if not _mentions_stop(current.description, value)]
    medications = [value for value in medications if not _mentions_stop(current.description, value)]
    med_history = [value for value in med_history if not _mentions_stop(current.description, value)]

    # Explicit topic shifts replace location-dependent clinical facts instead
    # of unioning face/back or old/new lesions into one synthetic case.
    current_lower = current.description.lower()
    topic_shift = any(marker in current_lower for marker in (
        "không phải ở", "khong phai o", "câu này tôi hỏi về",
        "cau nay toi hoi ve", "chuyển sang", "chuyen sang",
        "nói nhầm", "noi nham",
    ))
    if topic_shift and current.clinical is not None:
        if current.clinical.lesion_distribution:
            distribution = list(current.clinical.lesion_distribution)
        if current.clinical.lesion_types:
            lesion_types = list(current.clinical.lesion_types)

    merged_context = UserContext(
        age=age,
        sex=sex,
        skin_type=skin_type,
        is_pregnant=bool(is_pregnant),
        is_breastfeeding=bool(is_breastfeeding),
        allergies=_dedupe_values(allergies),
        current_products=_dedupe_values(products),
        medications=_dedupe_values(medications),
        duration_weeks=duration_weeks,
    )
    merged_clinical = AcneClinicalInput(
        lesion_types=_dedupe_values(lesion_types),  # type: ignore[arg-type]
        lesion_distribution=_dedupe_values(distribution),  # type: ignore[arg-type]
        inflammation_level=inflammation,
        scarring_signs=_dedupe_values(scarring),
        medication_history=_dedupe_values(med_history),
        hormonal_factors=_dedupe_values(hormonal),
        skincare_products=_dedupe_values(skincare),
        canonical_ingredients=_dedupe_values(canonical_ingredients),
        usage_frequencies=_dedupe_values(usage_frequencies),
        concentrations=list(dict.fromkeys(float(x) for x in concentrations)),
        treatment_goals=_dedupe_values(goals),
        red_flags_input=_dedupe_values(red_flags),
    )
    has_clinical = any(
        (
            merged_clinical.lesion_types,
            merged_clinical.lesion_distribution,
            merged_clinical.inflammation_level,
            merged_clinical.scarring_signs,
            merged_clinical.medication_history,
            merged_clinical.hormonal_factors,
            merged_clinical.skincare_products,
            merged_clinical.canonical_ingredients,
            merged_clinical.usage_frequencies,
            merged_clinical.concentrations,
            merged_clinical.treatment_goals,
            merged_clinical.red_flags_input,
        )
    )
    return current.model_copy(update={
        "context": merged_context,
        "clinical": merged_clinical if has_clinical else None,
    })


# ── Prompt helpers ────────────────────────────────────────────────────────────

def _is_genital_turn(turn: ConversationTurn) -> bool:
    """True khi turn chứa nội dung vùng sinh dục/hậu môn — cần lọc khỏi history.

    Lọc cả user turn lẫn assistant turn liền kề để tránh history poisoning:
    bot mention "bìu" trong câu trả lời cũng bị loại.
    """
    lowered = turn.content.lower()
    return any(term in lowered for term in _GENITAL_FILTER_TERMS)


def format_history_block(
    turns: list[ConversationTurn],
    char_budget: int = HISTORY_CHAR_BUDGET,
    first_turn_budget: int = FIRST_TURN_BUDGET,
    keep_anchor: bool = False,
    max_turns: int | None = None,
) -> str:
    """Render only recent selected turns as a compact prompt block.

    Lọc các turn genital/out-of-scope trước khi inject vào prompt để tránh
    session history poisoning (LLM mention "bìu" trong câu hỏi acne tiếp theo).

    Ưu tiên anchor turn đầu tiên của user (tin nhắn gốc mô tả tình trạng):
    - Luôn giữ turn đầu (cắt tối đa first_turn_budget chars nếu quá dài).
    - Phần budget còn lại dùng cho các turns gần nhất (newest-first).

    Returns empty string when turns is empty (caller should skip the section).
    """
    if not turns:
        return ""

    # Lọc bỏ các turn (và turn assistant ngay sau) có nội dung genital
    filtered: list[ConversationTurn] = []
    skip_next = False
    for turn in turns:
        if skip_next:
            skip_next = False
            continue
        if turn.role == "user" and _is_genital_turn(turn):
            skip_next = True
            continue
        if turn.role == "assistant" and _is_genital_turn(turn):
            continue
        filtered.append(turn)

    if not filtered:
        return ""

    def _fmt(turn: ConversationTurn) -> str:
        role_label = "User" if turn.role == "user" else "Assistant"
        content = turn.content.strip()
        return "[" + role_label + "]: " + content

    # Schema v2 never anchors the first turn. Callers pre-select relevant turns;
    # this final bound prevents accidental history expansion.
    tail_limit = max_turns if max_turns is not None else 2
    tail = filtered[-tail_limit:] if tail_limit else []
    if not char_budget or char_budget <= 0:
        return "\n".join(_fmt(turn) for turn in tail)

    per_turn = max(80, char_budget // max(1, len(tail)))
    selected: list[str] = []
    for turn in tail:
        line = _fmt(turn)
        if len(line) > per_turn:
            line = line[:per_turn].rsplit(" ", 1)[0].strip() + "..."
        selected.append(line)
    return "\n".join(selected)
