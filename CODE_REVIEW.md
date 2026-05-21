# AcneLLM Code Review — Logic Bugs & Issues

**Reviewed by:** Senior AI Engineer Tester  
**Date:** 2026-05-19  
**Severity Levels:** 🔴 Critical | 🟠 High | 🟡 Medium | 🟢 Low

---

## Summary
This codebase is well-structured with good separation of concerns (RAG, LLM, pipelines, API). However, there are several **logic bugs and concurrency issues** that could cause silent failures, data inconsistency, and lost events in production.

---

## 🔴 CRITICAL ISSUES

### 1. **Thread-Safety Race Condition in Session Store** (`jsonl_session_store.py:194-206`)
**Location:** `get_or_create()` method

**Problem:**
```python
with self._lock:
    all_lines = self._read_lines(sid)
    meta = self._get_merged_meta(all_lines)
    if not meta or self._is_expired(meta):
        self._delete_file(sid)
        self._init_session(sid)
        all_lines = self._read_lines(sid)  # ← Race: file could be written here by other thread
```

The code reads metadata, then writes (init/touch), then reads again. **Between the write and second read, another thread could write to the file, causing the second read to see inconsistent state.**

**Impact:** Session initialization could fail silently, returning stale/corrupted turns history.

**Fix:**
```python
with self._lock:
    all_lines = self._read_lines(sid)
    meta = self._get_merged_meta(all_lines)
    needs_reset = not meta or self._is_expired(meta)
    if needs_reset:
        self._delete_file(sid)
        self._init_session(sid)
    else:
        self._touch(sid)
    # Read once after all writes are done
    all_lines = self._read_lines(sid)
    meta = self._get_merged_meta(all_lines)
    turns = self.get_history(sid)
```

---

### 2. **Concurrent Counter Update Without Synchronization** (`chat.py:61-62` and `runtime.py:70-71`)
**Location:** Metrics guardrail trigger counting

**Problem:**
```python
# Multiple concurrent requests could race
if metrics is not None:
    metrics.guardrail_trigger_count += 1  # NOT atomic!
```

**Impact:** Lost metric counts in high-concurrency scenarios; guardrail statistics become unreliable.

**Fix:** Use atomic increment or acquire lock before updating:
```python
if metrics is not None and hasattr(metrics, '_lock'):
    with metrics._lock:
        metrics.guardrail_trigger_count = getattr(metrics, 'guardrail_trigger_count', 0) + 1
```

---

### 3. **Silent Event Loss in WebSocket Frame Processing** (`chat.py:214-229`)
**Location:** WebSocket chat endpoint

**Problem:**
```python
for frame in frames:
    line = next(
        (item for item in frame.splitlines() if item.startswith("data: ")),
        "",  # Returns empty string if NO "data: " line found
    )
    if not line:
        continue  # ← SILENTLY SKIPS THIS EVENT
    await websocket.send_json(json.loads(line[6:]))
```

The code assumes ONE "data: " line per frame. SSE spec allows multiple events per frame. **Events without "data: " prefix are silently dropped.**

**Impact:** Missing citation events, safety suffixes, or partial responses never reach client.

**Fix:**
```python
for frame in frames:
    for line in frame.splitlines():
        if line.startswith("data: "):
            try:
                await websocket.send_json(json.loads(line[6:]))
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse SSE frame: {line}")
                continue
```

---

## 🟠 HIGH PRIORITY ISSUES

### 4. **Duplicate RRF Fusion Implementation** (hybrid.py:52-57 vs retriever.py:63-68 vs _retrieval.py:54-59)
**Problem:** Three identical RRF fusion functions exist in different modules.

**Impact:** 
- Code maintenance nightmare: bug fix in one might be missed in others
- Inconsistent behavior if implementations diverge
- If K parameter changes, need to update three places

**Fix:** Create shared utility:
```python
# In acne_llm/rag/fusion.py
def rrf_fusion(rank_lists: list[list[str]], k: int = 60) -> dict[str, float]:
    """Reciprocal Rank Fusion for combining multiple retrieval rankings."""
    scores: dict[str, float] = {}
    for ranks in rank_lists:
        for i, cid in enumerate(ranks):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + i + 1)
    return scores

# Then import everywhere
from ..rag.fusion import rrf_fusion
```

---

### 5. **Unsafe Chunk Object Mutation in Retrieved Data** (hybrid.py:222 and _retrieval.py:81)
**Location:** Chunk score assignment

**Problem:**
```python
chunks = []
for chunk_id, score in fused.items():
    chunk = by_id[chunk_id]
    chunk.score = float(score)  # ← MUTATING RetrievedChunk Pydantic model
    chunks.append(chunk)
```

Pydantic models can be frozen/immutable. Directly mutating fields violates schema contract.

**Impact:** 
- If RetrievedChunk becomes `frozen=True`, code crashes
- Same chunk object might be shared; mutation affects all references
- Difficult to debug where score changes came from

**Fix:** Create new chunk with updated score:
```python
chunks = []
for chunk_id, score in fused.items():
    chunk = by_id[chunk_id]
    new_chunk = chunk.model_copy(update={"score": float(score)})
    chunks.append(new_chunk)
```

---

### 6. **Unsafe JSON Fallback in WebSocket Handler** (chat.py:198-206)
**Location:** WebSocket message parsing

**Problem:**
```python
try:
    payload = json.loads(raw)
    message = str(payload.get("message", ""))
    mode = str(payload.get("mode", "auto"))
    session_id = payload.get("session_id")
except json.JSONDecodeError:
    message = raw  # ← Treats invalid JSON as literal message!
    mode = "auto"
    session_id = None
```

**Impact:** Malformed JSON sent by client is interpreted as user message instead of being rejected, potentially bypassing validation.

**Fix:**
```python
try:
    payload = json.loads(raw)
    ...
except json.JSONDecodeError:
    await websocket.send_json({"event": "error", "data": "Invalid JSON payload"})
    continue
```

---

### 7. **Session Path Sanitization Collision Risk** (jsonl_session_store.py:62)
**Location:** `_path()` method

**Problem:**
```python
safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in sid)
return self._dir / f"{safe}.jsonl"
```

**Collision example:**
- Input `"user-123"` → `"user-123.jsonl"`
- Input `"user_123"` → `"user_123.jsonl"` (no collision here, but...)
- Input `"user---123"` → `"user___123.jsonl"`

More problematic: No length limit. Filesystem has max filename length (usually 255 chars).

**Impact:** Extremely long session IDs could silently fail file operations.

**Fix:**
```python
safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in sid)
if len(safe) > 200:  # Leave buffer for .jsonl extension
    safe = safe[:200] + "_" + str(hash(sid))[-8:]
return self._dir / f"{safe}.jsonl"
```

---

## 🟡 MEDIUM PRIORITY ISSUES

### 8. **Config Paths Are Relative — Fails in Different CWD** (config.py:33-36)
**Location:** Settings class

**Problem:**
```python
chroma_dir: str = "./data/chroma_db"
bm25_path: str = "./data/bm25_index.pkl"
docs_jsonl: str = "./data/raw/documents.jsonl"
```

**Impact:**
- Running from different directory breaks: `python -m acne_llm` vs `cd src && python`
- Docker: working directory might not match expected paths
- Unit tests: might fail depending on test runner cwd

**Fix:** Convert to absolute paths relative to code location:
```python
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent
chroma_dir: str = str(BASE_DIR / "data" / "chroma_db")
bm25_path: str = str(BASE_DIR / "data" / "bm25_index.pkl")
```

---

### 9. **Query Building Inconsistency — Two Implementations** (hybrid.py:83-146 vs _retrieval.py:19-49)
**Location:** Query building for retrieval

**Problem:**
```python
# hybrid.py includes vision data, clinical details separately
if user.vision:
    vision_bits.append(...)

# _retrieval.py doesn't include vision at all
def build_query_from_user(user: UserInput) -> str:
    parts = [user.description]
    c = user.context
    # No vision handling!
```

**Impact:**
- `/chat` endpoint (hybrid.py) produces different query than `/chat/stream` (intake → _retrieval.py)
- Same user input retrieves different chunks depending on endpoint
- Vision information lost in streaming endpoint

**Fix:** Use consistent query builder everywhere:
```python
# Create canonical builder in _retrieval.py
# Import and use in both hybrid.py and streaming path
from .._retrieval import build_query_from_user
```

---

### 10. **Missing TTL Validation on Session ID Length** (jsonl_session_store.py:57-58)
**Location:** `_is_valid_sid()`

**Problem:**
```python
def _is_valid_sid(self, session_id: str | None) -> bool:
    return bool(session_id and session_id.strip())  # Only checks empty!
```

**Impact:** 
- No length limit check
- Filesystem filename limit (255 chars) not enforced
- Could create invalid files silently

**Fix:**
```python
def _is_valid_sid(self, session_id: str | None) -> bool:
    if not session_id:
        return False
    sid = session_id.strip()
    if len(sid) > 200:  # Reasonable limit
        return False
    if any(c in sid for c in ['/', '\\', '\x00']):  # Forbidden chars
        return False
    return True
```

---

### 11. **Compact Operation Could Leave Orphaned Temp Files** (jsonl_session_store.py:146-159)
**Location:** `_compact_if_needed()` error handling

**Problem:**
```python
try:
    with tmp.open("w", encoding="utf-8") as f:
        f.write(...)
    tmp.replace(p)  # Atomic on POSIX, not on Windows!
except OSError as e:
    logger.warning(f"[SessionStore] compact failed for {sid}: {e}")
    try:
        tmp.unlink(missing_ok=True)
    except OSError:
        pass  # Silent failure
```

**Impact:**
- On Windows, `tmp.replace(p)` is NOT atomic; could partially complete
- Orphaned `.jsonl.tmp` files accumulate over time
- Session data could be lost if replacement fails

**Fix:**
```python
try:
    with tmp.open("w", encoding="utf-8") as f:
        f.write(...)
    # On Windows, must remove dest before rename
    if p.exists():
        p.unlink()
    tmp.replace(p)
except OSError as e:
    logger.error(f"[SessionStore] compact FAILED for {sid} — session may be corrupted: {e}")
    try:
        tmp.unlink(missing_ok=True)
    except OSError:
        logger.error(f"[SessionStore] Could not cleanup temp file {tmp}")
    # Consider whether to rethrow or fall through
    raise  # Let caller know something went wrong
```

---

### 12. **First-Write-Wins Logic in User Context Merge is Confusing** (jsonl_session_store.py:286-291)
**Location:** `merge_user_context()`

**Problem:**
```python
# First write wins — không overwrite key đã có
updated = False
for k, v in context.items():
    if v is not None and k not in existing:  # Only adds if key MISSING
        existing[k] = v
        updated = True
```

**Impact:**
- Comment says "first write wins" but code actually does "never overwrite"
- If a key has a wrong value, it can NEVER be corrected in the session
- Semantically confusing for future maintainers

**Fix:** Either:
1. Change logic to actually implement "first write wins" (overwrite nulls, blank strings)
2. Or rename to `merge_user_context_no_overwrite()` and document clearly

---

### 13. **Uninitialized Computed Fields in Session Objects** (runtime.py:62-64 and elsewhere)
**Location:** Session usage in streaming

**Problem:**
```python
_sess_obj = sess._sessions.get(session_id) if hasattr(sess, "_sessions") else None
if _sess_obj is not None:
    _sess_obj.accumulated_clinical_score = getattr(_sess_obj, "accumulated_clinical_score", 0.0) + 1.0
```

**Impact:**
- Code relies on attribute existing with `getattr(..., 0.0)` fallback
- If someone refactors Session class, this breaks
- No type safety; computed field not declared in Session schema

**Fix:** Initialize in Session class:
```python
# In schemas/core.py or schemas/chat.py
@dataclass
class Session:
    ...
    accumulated_clinical_score: float = 0.0
    ...
```

---

### 14. **Latency Calculation Includes Async Overhead** (chat.py:49-50)
**Location:** Chat endpoint latency measurement

**Problem:**
```python
started = time.perf_counter()
try:
    intake = run_intake(c, message, ...)  # Sync call
    ...
    out = await asyncio.to_thread(pipeline.run, ...)  # Time here includes thread overhead
```

**Impact:**
- Reported latency includes thread pool scheduling delays
- Not representative of actual LLM inference time
- Makes performance metrics misleading

**Better approach:**
```python
started = time.perf_counter()
intake = run_intake(...)  # Sync, measure this separately

t_llm_start = time.perf_counter()
out = await asyncio.to_thread(pipeline.run, ...)
llm_latency = int((time.perf_counter() - t_llm_start) * 1000)

total_latency = int((time.perf_counter() - started) * 1000)
```

---

## 🟢 LOW PRIORITY / OBSERVATIONS

### 15. Prompt Injection Defense is Incomplete (prompt_builder.py:22-34)
**Current defense:** Escapes Jinja delimiters and replaces lowercase injection markers
**Limitation:** Case-sensitive check might miss mixed-case variants like "Ignore Previous" or "FORGET"

**Recommendation:** Use case-insensitive matching:
```python
def _sanitize_chunk_text(text: str) -> str:
    ...
    lower = text.lower()
    for marker in _INJECTION_MARKERS:
        if marker in lower:
            text = re.sub(re.escape(marker), "[nội dung đã lọc]", text, flags=re.IGNORECASE)
```

---

### 16. Missing Validation on Chat Message Length
**Location:** chat.py routes don't validate `message` length before processing

**Recommendation:** Add:
```python
MAX_MESSAGE_LENGTH = 2000
if len(message) > MAX_MESSAGE_LENGTH:
    raise HTTPException(status_code=400, detail=f"Message too long (max {MAX_MESSAGE_LENGTH})")
```

---

### 17. No Timeout on Streaming Operations
**Location:** `stream_chat_sse()` and LLM calls could run indefinitely

**Recommendation:** Wrap with timeout:
```python
import asyncio
try:
    async for chunk in stream_with_timeout(stream_chat_sse(...), timeout=60):
        yield chunk
except asyncio.TimeoutError:
    yield _event("error", "Request timeout")
```

---

### 18. Vision Output Not Validated Before Storage
**Location:** Session store stores `used_chunks` without validation that they exist in KB

**Recommendation:** Validate chunk IDs before persisting to avoid orphaned references

---

### 19. No Atomic Multi-Turn Session Append
**Location:** chat.py appends user and assistant turns separately
```python
store.append_turn(session_id, user_turn)
store.append_turn(session_id, assistant_turn)
```

If process crashes between these, session is in inconsistent state. **Consider atomic batch append.**

---

### 20. Log Levels Mixed with Business Logic
**Location:** Multiple places like runtime.py use `logger.debug()` for important decisions

**Recommendation:** Use DEBUG only for tracing; use INFO for decision points:
```python
logger.info(f"[{session_id}] Mode decision: {intake.effective_mode}")
logger.debug(f"[{session_id}] Detailed trace: {detailed_data}")
```

---

## Testing Recommendations

### Add Concurrent Access Tests:
```python
# Test concurrent session creation with same ID
# Test concurrent turn appends
# Test concurrent metrics updates
```

### Add Path Safety Tests:
```python
# Test with very long session IDs (>255 chars)
# Test with special characters: /\x00
# Test cross-platform (Windows/Linux) path handling
```

### Add WebSocket Frame Tests:
```python
# Test multiple events in single SSE frame
# Test malformed JSON fallback behavior
# Test missing "data: " prefix in frames
```

---

## Quick Fix Priority Order

1. **First:** Thread-safety race condition in session store (Issue #1)
2. **Second:** Concurrent metrics update (Issue #2)  
3. **Third:** Silent event loss in WebSocket (Issue #3)
4. **Fourth:** Chunk mutation bug (Issue #5)
5. **Fifth:** RRF fusion consolidation (Issue #4)
6. **Sixth:** Config path resolution (Issue #8)
7. **Seventh:** Session ID validation (Issue #10)

---

## Code Quality Summary

**Strengths:**
- ✅ Clean architecture (RAG/LLM separation)
- ✅ Good error logging throughout
- ✅ Prompt injection defense implemented
- ✅ Type hints used consistently

**Weaknesses:**
- ❌ Thread-safety issues in session storage
- ❌ Duplicate code (RRF fusion, query builders)
- ❌ Silent failure modes (WebSocket event loss)
- ❌ Missing validation on critical paths
- ❌ Relative paths cause environment issues

---

**Overall Assessment:** The codebase is **production-ready with critical issues that need immediate attention** before handling high-concurrency load. Focus on thread-safety and silent failure modes first.
