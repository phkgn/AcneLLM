# FINDINGS / src.chat.session

Module: `src/acne_llm/chat/session/` — 5 file, 815 LOC
(`__init__.py` 46, `models.py` 75, `memory.py` 195, `view.py` 161, `fold.py` 338).

**Phép đếm khối (Bước 0):**
- `__init__.py`: 1 lời khai + `__all__` = **2**
- `models.py`: 1 lời khai + 5 hằng + 3 dataclass + 2 method = **11**
- `memory.py`: 1 lời khai + `SessionStore` + 11 method + `_store` + `_store_lock` + `get_session_store` = **16**
- `view.py`: 1 lời khai + `select_relevant_history` + `CONTEXT_FIELD_THRESHOLD` + `_UNGATED_FIELDS` + `build_confirmed_profile` + `format_history_block` + `_fmt` (nested) = **7**
- `fold.py`: 1 lời khai + `_STOP_PRODUCT_TERMS` + `_mentions_stop` + `_dedupe_values` + `snapshot_from_user` + `_SEVERITY_ORDER` + `_max_severity` + `fold_history_facts` = **8**

→ **44 khối × 8 mục = 352 mục.**

---

## `__init__.py`

### [x] docstring `__init__.py:1-14`
1. in/out: 14 dòng lời khai. {doc}
2-5. side effect / state / lỗi / config: không. {doc}
6. ai gọi: không ai đọc `__doc__`. {code}
7. invariant khai báo: package tách từ "một file 714 dòng ở Phase 7"; bốn nhóm
   đổi vì bốn lý do khác nhau; "mọi tên cũ vẫn lấy được từ `chat.session`, nên
   13+ chỗ gọi không phải sửa một dòng import nào". **Đối chiếu code:** phần
   re-export đúng — `__all__` phủ đủ 14 tên. Con số "13+ chỗ gọi" thì lời khai
   phóng đại: grep production (`src/` + `research/`) chỉ ra **2 file** gọi
   (`chat/intake.py`, `llm/prompt_builder.py`); phần còn lại là test. {code+doc}
8. deprecated: không. {doc}

### [x] `__all__` (`__init__.py:39-46`)
1. in/out: list 14 chuỗi. {code}
2. side effect: không. {code}
3. state: hằng module. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: chỉ có tác dụng với `from ... import *`. Grep `from .session import \*`
   và `from acne_llm.chat.session import \*` = **0 kết quả**. Không ai dùng. {code}
7. invariant: 14 tên trong `__all__` khớp đúng 14 tên được import ở `:17-37`.
   Kiểm tay từng tên: khớp. {code}
8. deprecated: không, nhưng vô dụng — xem mục 6. {code}

---

## `models.py`

### [x] docstring `models.py:1-6`
1. in/out: 6 dòng lời khai. {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: "Không phụ thuộc module nào khác"; "`ConversationTurn`
   được import ở 13 nơi". **Đối chiếu:** import của file chỉ có `time`,
   `dataclasses`, `typing` — lời khai thứ nhất **đúng**. Lời khai thứ hai là con
   số của thời điểm tách, không kiểm lại được ở đây. {code+doc}
8. deprecated: không. {doc}

### [x] `SESSION_TTL` (`models.py:61`)
1. in/out: `float = 1800.0`. {code}
2-4. không. {code}
5. config: **hằng số cứng, không đọc từ `Settings`.** Đây là bản sao thứ hai của
   `settings.session_ttl` (`config.py:250`), cũng bằng 1800.0. Hai nguồn sự thật. {code}
6. ai gọi: `memory.py:24,40` (default của `SessionStore.__init__`),
   `models.py:117` (default của `Session.is_expired`), re-export ở `__init__.py:27`.
   `db/session_store.py` cũng đọc tên này (2 lần). {code}
7. invariant: nếu ai đó đổi `SESSION_TTL` trong `.env` (`SESSION_TTL=60`), chỉ
   `settings.session_ttl` đổi; hằng này vẫn 1800.0, và `SessionStore()` dựng
   không tham số vẫn dùng 1800.0. Xem Q-01. {code}
8. deprecated: không. {code}

### [x] `MAX_HISTORY_TURNS` (`models.py:62`)
1. in/out: `int = 6`. {code}
2-4. không. {code}
5. config: hằng cứng, không có field `Settings` tương ứng. {code}
6. ai gọi: `memory.py:23,41`, re-export `__init__.py:25`. {code}
7. invariant: comment nói "0 = unlimited", và code tôn trọng đúng thế —
   `memory.py:93,120` đều gác `if self.max_turns and self.max_turns > 0`. {code+comment}
8. deprecated: không. {code}

### [x] `SESSION_SCHEMA_VERSION` (`models.py:63`)
1. in/out: `int = 2`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `models.py:115` (default field của `Session`), re-export `__init__.py:26`. {code}
7. invariant: **có** nơi đọc ra để so sánh, và nó nằm ngoài package này:
   `db/session_store.py:127` — `int(row["schema_version"] or 0) != SESSION_SCHEMA_VERSION`
   → row lệch phiên bản bị coi như hết hạn và reset (`:122` docstring). Cột
   SQLite `schema_version INTEGER NOT NULL DEFAULT 0` (`:43`) nghĩa là mọi row
   cũ chưa có cột đều lệch 2 → reset sạch một lần khi nâng schema. Bản in-memory
   thì **không** kiểm gì cả — thêm một điểm hai store lệch nhau. {code}
8. deprecated: không. {code}

### [x] `HISTORY_CHAR_BUDGET` (`models.py:65`)
1. in/out: `int = 2000`. {code}
2-4. không. {code}
5. config: hằng cứng. Comment `:64` gọi nó là "Nguồn sự thật duy nhất cho ngân
   sách ký tự lịch sử". {code+comment}
6. ai gọi: `view.py:17,116` (default của `format_history_block`), re-export
   `__init__.py:23`. {code}
7. invariant: comment ghi "~570 tokens; prompt thực đo được 828 tokens / ctx 3072".
   `ctx 3072` là số cũ — `settings.llm_num_ctx` hiện là **8192** (`config.py:28`,
   và dòng đó còn giữ vết `#4096 #3072`). Lời khai trong comment đã lệch một hệ. {comment+code}
8. deprecated: không. {code}

### [x] `HISTORY_WINDOW_TURNS` (`models.py:68`)
1. in/out: `int = 6`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `view.py:17,34`, `llm/prompt_builder.py:228` (truyền vào
   `format_history_block(max_turns=...)`), re-export `__init__.py:24`. {code}
7. invariant: comment nói "3 lượt hỏi-đáp; budget chars mới là giới hạn thật".
   Đúng: `format_history_block` cắt theo `char_budget` sau khi đã cắt theo
   `max_turns`. Nhưng default `max_turns=2` của `format_history_block`
   (`view.py:149`) khác hẳn 6 — chỉ vì `prompt_builder.py:228` truyền tường minh
   `HISTORY_WINDOW_TURNS` mà production mới thấy 6 turn. Test gọi không tham số
   thì thấy 2. Xem Q-03. {code}
8. deprecated: không. {code}

### [x] `NormalizedSnapshot` (`models.py:73-82`)
1. in/out: dataclass 3 field — `context: dict`, `clinical: dict`, `clean_text: str`. {code}
2. side effect: không. {code}
3. state: mutable (dict mặc định qua `field(default_factory=dict)` — đúng cách,
   không dính bẫy mutable default). {code}
4. lỗi: không validate gì; `context`/`clinical` nhận bất kỳ dict nào. {code}
5. config: không. {code}
6. ai gọi: `fold.py:16` (import), `fold.py:104` (dựng), `models.py:92`
   (field của `ConversationTurn`), re-export. {code}
7. invariant: đây là dataclass **không phải pydantic**, khác hẳn `schemas/` —
   nên không có validation nào giữa `UserInput.model_dump()` và cấu trúc này.
   Sai key ở đây không ai bắt. {code}
8. deprecated: không. {code}

### [x] `ConversationTurn` (`models.py:85-97`)
1. in/out: dataclass 7 field — `role`, `content`, `timestamp`, `mode`,
   `used_chunks`, `normalized_snapshot`, `metadata`. {code}
2. side effect: `timestamp` gọi `time.time()` qua `default_factory` khi dựng. {code}
3. state: mutable. {code}
4. lỗi: `role` khai `Literal["user","assistant"]` nhưng dataclass **không ép**
   — truyền `role="system"` chạy bình thường. {code}
5. config: không. {code}
6. ai gọi: nhiều nhất trong package; production: `chat/intake.py`,
   `chat/runtime.py`, `db/session_store.py`, `llm/prompt_builder.py`. {code}
7. invariant: comment `ponytail:` ở `:94-97` khai rằng
   `intent_label`/`intent_confidence`/`turn_type` đã bị xoá vì "chỉ được GHI bởi
   SessionStore in-memory và không dòng nào đọc ra", và "bản SQLite còn không
   khôi phục chúng khi đọc, nên hai store lệch nhau mà không ai biết". Đây là
   {comment} — tôi **chưa** đối chiếu với `db/session_store.py`; việc đó thuộc
   `src.db`, ghi lại để module đó phải kiểm. {comment}
8. deprecated: không. {code}

### [x] `Session` (`models.py:100-115`)
1. in/out: dataclass 9 field. {code}
2. side effect: `created_at`/`last_active` gọi `time.time()` khi dựng. {code}
3. state: mutable; `turns` bị cắt tại chỗ bởi `SessionStore.append_turn`. {code}
4. lỗi: không validate. {code}
5. config: `schema_version` mặc định `SESSION_SCHEMA_VERSION`. {code}
6. ai gọi: `memory.py:74,112` (dựng), `db/session_store.py`. {code}
7. invariant: comment `:107` nói `user_context` "never overwritten, only merged"
   — `memory.py:137-139` giữ đúng: gán từng key, bỏ qua `None`. Nhưng "merge"
   ở đây là **ghi đè per-key**, không phải hợp nhất list; `merge_user_context`
   với `{"allergies": []}` sẽ thay thế list cũ bằng list rỗng. {code+comment}
8. deprecated: `asked_fields` — comment `memory.py:150-152` khai rằng cơ chế
   "đừng hỏi lại field đã hỏi" đã bị gỡ ở `runtime.py`, cột vẫn còn trong schema
   SQLite. Field còn nhưng chết. {code+comment}

### [x] `Session.is_expired` (`models.py:117-118`)
1. in/out: `(self, ttl: float = SESSION_TTL) -> bool`. {code}
2. side effect: đọc `time.time()`. {code}
3. state: đọc `self.last_active`. {code}
4. lỗi: không. {code}
5. config: default `ttl` = hằng module, không phải `settings`. {code}
6. ai gọi: `memory.py:56` (`sess.is_expired(self.ttl)` — luôn truyền tường minh,
   nên default không bao giờ dùng ở đường in-memory). {code}
7. invariant: so sánh `>` chứ không `>=` — session đúng bằng TTL vẫn sống. Vô hại. {code}
8. deprecated: không. {code}

### [x] `Session.touch` (`models.py:120-121`)
1. in/out: `(self) -> None`; đặt `last_active = time.time()`. {code}
2. side effect: sửa `self`. {code}
3. state: có. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `memory.py:76,92,122`. {code}
7. invariant: `merge_user_context`, `get_user_context`, `increment_followup_count`
   và `delete` **không** gọi `touch()` — nên một session chỉ được cập nhật
   context mà không append turn sẽ hết hạn như thể không ai đụng tới. Xem Q-04. {code}
8. deprecated: không. {code}

---

## `memory.py`

### [x] docstring `memory.py:1-16`
1. in/out: 16 dòng lời khai. {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: "đây KHÔNG phải đường chạy production"; "`di.py:94` wire
   `db.session_store.SQLiteSessionStore`, không có nhánh dự phòng"; "`get_session_store()`
   chỉ được TEST gọi (17 chỗ)". **Đối chiếu code:** grep production
   (`src/` + `research/`, loại trừ chính package) tìm `get_session_store` =
   **0 kết quả**; tất cả 13 lần gọi nằm trong `tests/`. Lời khai **đúng về bản
   chất**; con số "17 chỗ" tôi đếm được 13 (test_intake 7, test_chat_stream 4,
   test_session 2). Lệch số, không lệch kết luận. {code+doc}
8. deprecated: cả file là test double đang sống trong `src/`. Xem Q-05. {code+doc}

### [x] `SessionStore` (`memory.py:31-179`)
1. in/out: lớp; dựng bằng `SessionStore(ttl, max_turns)`. {code}
2. side effect: giữ dict trong bộ nhớ tiến trình. {code}
3. state: `self._sessions` (dict), `self._lock` (RLock), `self.ttl`, `self.max_turns`. {code}
4. lỗi: không raise gì; mọi method no-op khi `session_id` rỗng. {code}
5. config: không đọc `settings`; nhận qua tham số dựng. {code}
6. ai gọi: production = 0. Test = `tests/test_session.py` (20 lần dựng). {code}
7. invariant: docstring lớp nói "All public methods are no-ops when session_id
   is None or empty". **Kiểm từng method:** `get_or_create` → None,
   `get_history` → [], `append_turn` → return, `merge_user_context` → return,
   `get_user_context` → {}, `increment_followup_count` → return, `delete` →
   return. 7/7 đúng. `active_count` không nhận `session_id` nên không áp dụng. {code}
8. deprecated: xem Q-05. {code}

### [x] `SessionStore.__init__` (`memory.py:38-46`)
1. in/out: `(self, ttl=SESSION_TTL, max_turns=MAX_HISTORY_TURNS) -> None`. {code}
2. side effect: tạo dict + RLock. {code}
3. state: khởi tạo 4 thuộc tính. {code}
4. lỗi: không. {code}
5. config: default từ hằng `models.py`, **không** từ `settings.session_ttl`. {code}
6. ai gọi: chỉ test và `get_session_store()`. {code}
7. invariant: dùng `RLock` chứ không `Lock` — cần thiết vì `get_or_create` và
   `append_turn` đều gọi `_expire_if_stale` **bên trong** `with self._lock`. Với
   `Lock` thường thì không deadlock (vì `_expire_if_stale` không tự lấy lock),
   nên `RLock` ở đây là dự phòng chứ không bắt buộc. {code}
8. deprecated: không. {code}

### [x] `SessionStore._is_valid_sid` (`memory.py:50-51`)
1. in/out: `(self, session_id: str | None) -> bool`; `bool(session_id and session_id.strip())`. {code}
2-3. không side effect, không state. {code}
4. lỗi: `session_id` là int sẽ `AttributeError` ở `.strip()`. Không ai truyền int. {code}
5. config: không. {code}
6. ai gọi: 7 method công khai trong chính lớp. {code}
7. invariant: chuỗi toàn khoảng trắng bị coi là không hợp lệ. {code}
8. deprecated: không. {code}

### [x] `SessionStore._expire_if_stale` (`memory.py:53-59`)
1. in/out: `(self, session_id: str) -> bool`; True nếu đã xoá. {code}
2. side effect: `del self._sessions[session_id]`. {code}
3. state: sửa dict. {code}
4. lỗi: không (dùng `.get`). {code}
5. config: `self.ttl`. {code}
6. ai gọi: `get_or_create:72`, `get_history:88`, `append_turn:110`. **Không**
   được gọi bởi `merge_user_context`, `get_user_context`,
   `increment_followup_count`, `delete`, `active_count`. {code}
7. invariant: hết hạn là **lazy** — session quá hạn vẫn nằm trong dict cho đến
   khi có ai chạm vào đúng `session_id` đó. `active_count` vì thế đếm bằng cách
   lọc theo thời gian chứ không dựa vào dict, và đó là lý do nó không gọi hàm này. {code}
8. deprecated: không. {code}

### [x] `SessionStore.get_or_create` (`memory.py:63-77`)
1. in/out: `(self, session_id: str | None) -> Session | None`. {code}
2. side effect: có thể tạo `Session` mới, có thể xoá session cũ. {code}
3. state: sửa `self._sessions`. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: production 0; `tests/test_session.py`. {code}
7. invariant: trả về **tham chiếu sống** tới `Session` trong dict, không phải
   bản sao — người gọi sửa được state của store từ bên ngoài lock. {code}
8. deprecated: không. {code}

### [x] `SessionStore.get_history` (`memory.py:79-95`)
1. in/out: `(self, session_id) -> list[ConversationTurn]`. {code}
2. side effect: `touch()` + có thể xoá session hết hạn. Một hàm tên "get" có
   ghi state. {code}
3. state: sửa `last_active`. {code}
4. lỗi: không. {code}
5. config: `self.max_turns`. {code}
6. ai gọi: production 0. {code}
7. invariant: trả `list(...)` — bản sao **nông**; các `ConversationTurn` bên
   trong vẫn là tham chiếu sống. {code}
8. deprecated: không. {code}

### [x] `SessionStore.append_turn` (`memory.py:97-122`)
1. in/out: `(self, session_id, turn: ConversationTurn) -> None`. {code}
2. side effect: append + cắt list + `touch()` + tăng `total_clarify_count`. {code}
3. state: sửa `Session`. {code}
4. lỗi: không. {code}
5. config: `self.max_turns`. {code}
6. ai gọi: production 0. {code}
7. invariant: `total_clarify_count` chỉ tăng khi `role == "assistant"` **và**
   `mode == "clarify"`. `mode` là chuỗi tự do (`models.py:90`, default `"hybrid"`),
   không có Literal nào chặn — gõ sai `"clarify "` là đếm hụt im lặng. {code}
8. deprecated: không. {code}

### [x] `SessionStore.merge_user_context` (`memory.py:124-139`)
1. in/out: `(self, session_id, context: dict) -> None`. {code}
2. side effect: ghi vào `sess.user_context`. {code}
3. state: có. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: production 0. {code}
7. invariant: **không tạo session** nếu chưa có (khác `append_turn`), và
   **không gọi `touch()`** — xem Q-04. Bỏ qua value `None` nhưng **không** bỏ qua
   list rỗng, nên `{"allergies": []}` xoá sạch dị ứng đã lưu. {code}
8. deprecated: không. {code}

### [x] `SessionStore.get_user_context` (`memory.py:141-148`)
1. in/out: `(self, session_id) -> dict`; trả `dict(...)` bản sao nông. {code}
2. side effect: không (không `touch`, không expire). {code}
3. state: chỉ đọc. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: production 0. {code}
7. invariant: **không kiểm hết hạn** — trả context của session đã quá TTL nếu
   dict còn giữ. Khác hẳn `get_history`, vốn expire trước khi đọc. Hai đường đọc
   của cùng một session cho hai câu trả lời khác nhau về "session còn sống không". {code}
8. deprecated: không. {code}

### [x] `SessionStore.increment_followup_count` (`memory.py:154-162`)
1. in/out: `(self, session_id, amount: float = 1.0) -> None`. {code}
2. side effect: cộng vào `accumulated_clinical_score`. {code}
3. state: có. {code}
4. lỗi: `float(amount)` raise `ValueError` nếu truyền chuỗi không parse được. {code}
5. config: không. {code}
6. ai gọi: **bản in-memory này 0 chỗ trong production.** Nhưng tên method thì
   có người gọi: `chat/runtime.py:95-96` gọi
   `sess.increment_followup_count(session_id, 1.0)` sau khi gác `hasattr` — và
   `sess` ở đó là `SQLiteSessionStore` (`db/session_store.py:288`), không phải
   lớp này. Test gọi cả hai bản. {code}
7. invariant: tên hàm nói "followup_count", field nói "clinical_score", kiểu là
   float. Ba cách gọi cho một thứ. Ngoài ra `runtime.py:95` gác bằng `hasattr`
   thay vì tin interface — dấu hiệu người viết không chắc store nào được wire. {code}
8. deprecated: không. {code}

### [x] `SessionStore.delete` (`memory.py:164-170`)
1. in/out: `(self, session_id) -> None`. {code}
2. side effect: `pop`. {code}
3. state: có. {code}
4. lỗi: không (`pop(sid, None)`). {code}
5. config: không. {code}
6. ai gọi: production 0. {code}
7. invariant: docstring nói "e.g. on user logout" — không có endpoint logout nào
   gọi tới (`api/routes/` không import store in-memory). {code}
8. deprecated: không. {code}

### [x] `SessionStore.active_count` (`memory.py:172-179`)
1. in/out: `(self) -> int`. {code}
2. side effect: không (đếm, không xoá). {code}
3. state: chỉ đọc. {code}
4. lỗi: không. {code}
5. config: `self.ttl`. {code}
6. ai gọi: **bản in-memory này 0 chỗ trong production.** Tên method có người
   gọi: `api/routes/admin.py:41` — `{"active_sessions": sess.active_count()}` —
   nhưng `sess` là `SQLiteSessionStore` (`db/session_store.py:311`). Không phải
   `metrics.py` như docstring "for metrics/debug" gợi ý. {code}
7. invariant: đếm theo `now - last_active <= ttl` — dùng `<=` trong khi
   `Session.is_expired` dùng `>`. Hai vế bù nhau đúng, không lệch biên. {code}
8. deprecated: không. {code}

### [x] `_store` (`memory.py:184`)
1. in/out: `SessionStore | None = None`. {code}
2-3. biến module, bị `get_session_store` gán. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: chỉ `get_session_store`. {code}
7. invariant: singleton toàn tiến trình; test nào gọi `get_session_store()` sẽ
   chia sẻ state với test khác trừ khi tự reset. {code}
8. deprecated: không. {code}

### [x] `_store_lock` (`memory.py:185`)
1. in/out: `threading.Lock()`. {code}
2-3. hằng module. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `get_session_store:192`. {code}
7. invariant: `Lock` chứ không `RLock` — đúng, vì không có tái nhập. {code}
8. deprecated: không. {code}

### [x] `get_session_store` (`memory.py:188-195`)
1. in/out: `() -> SessionStore`. {code}
2. side effect: tạo singleton lần đầu. {code}
3. state: gán `_store` toàn cục. {code}
4. lỗi: không. {code}
5. config: dựng `SessionStore()` **không tham số** → TTL 1800.0 từ hằng module,
   bỏ qua `settings.session_ttl` hoàn toàn. {code}
6. ai gọi: 13 lần, **toàn bộ trong `tests/`**. Production 0. {code}
7. invariant: double-checked locking đúng chuẩn (kiểm ngoài lock, kiểm lại trong
   lock). {code}
8. deprecated: xem Q-05. {code}

---

## `view.py`

### [x] docstring `view.py:1-13`
1. in/out: 13 dòng lời khai. {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: "Phụ thuộc một chiều: view → fold (`build_confirmed_profile`
   dùng `_mentions_stop`) và view → models. Không có chiều ngược lại."
   **Đối chiếu code:** `view.py:16-17` import từ `.fold` và `.models`; `fold.py`
   import từ `...schemas` và `.models`, **không** import `.view`. Lời khai đúng. {code+doc}
8. deprecated: không. {doc}

### [x] `select_relevant_history` (`view.py:20-45`)
1. in/out: `(message, primary_intent, history, route_flags=None) -> list[ConversationTurn]`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: `HISTORY_WINDOW_TURNS` (6). {code}
6. ai gọi: production `chat/intake.py:572` và `:731`; test `test_session.py`. {code}
7. invariant: **2 trong 4 tham số là chết** — `view.py:33` viết
   `del message, route_flags` ngay dòng đầu thân hàm. Chữ ký vẫn đòi chúng, và
   `intake.py` vẫn tính rồi truyền vào. Nhánh `primary_intent == "knowledge"`
   trả **đúng một** user turn gần nhất; mọi intent khác trả cả cửa sổ 6. {code}
8. deprecated: hai tham số chết chưa được đánh dấu. Xem Q-07. {code}

### [x] `CONTEXT_FIELD_THRESHOLD` (`view.py:67`)
1. in/out: `float = 0.60`. {code}
2-4. không. {code}
5. config: hằng cứng; **đồng thời** là giá trị dự phòng khi
   `chat/intake.py:748-755` không lấy được `settings.extract_min_field_conf`. Hai
   nguồn, cùng số 0.60 (`config.py:225`). {code}
6. ai gọi: `view.py:75` (default), `chat/intake.py:754` (fallback của getattr
   lồng hai lớp), re-export `__init__.py:33`. {code}
7. invariant: comment `:48-66` (19 dòng) giải thích số này được chọn theo **hướng
   hỏng**, không theo mức quan trọng, và neo vào dải confidence mà system prompt
   của intaker tự định nghĩa. Đây là comment hiếm hoi nêu được ràng buộc ngoài
   code. Nó cũng khai rằng ngưỡng cũ 0.82 là "tàn dư của thang điểm rule cũ". {comment}
8. deprecated: không. {code}

### [x] `_UNGATED_FIELDS` (`view.py:68`)
1. in/out: `frozenset({"is_pregnant", "is_breastfeeding"})`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `view.py:89`. {code}
7. invariant: hai trường này được gán `field_threshold = 0.0`, tức **mọi**
   giá trị không-None đều vào profile bất kể confidence. Comment `:56-60` nêu lý
   do: bỏ sót thai kỳ là hướng hỏng nguy hiểm hơn nhận nhầm. Code khớp lời khai. {code+comment}
8. deprecated: không. {code}

### [x] `build_confirmed_profile` (`view.py:71-110`)
1. in/out: `(existing: dict, extraction_confidence: object | None, clean_text: str,
   threshold: float = 0.60) -> dict`. {code}
2. side effect: không (copy `existing` ở `:82`). {code}
3. state: không. {code}
4. lỗi: `float(getattr(result, "confidence", 0.0))` raise `ValueError` nếu
   confidence là chuỗi không parse được. Không có test cho nhánh đó. {code}
5. config: `threshold` từ người gọi; `chat/intake.py:746-757` truyền
   `settings.extract_min_field_conf` qua **getattr lồng hai lớp** —
   `getattr(getattr(c, "settings", None), "extract_min_field_conf", CONTEXT_FIELD_THRESHOLD)`.
   Nếu container không có `.settings`, giá trị lặng lẽ về 0.60. {code}
6. ai gọi: `chat/intake.py:746`. {code}
7. invariant: `extraction_confidence` khai kiểu `object | None` — tức hàm này
   nhận **bất kỳ** object nào và dò field bằng `getattr`. Không có protocol,
   không có TypedDict. Object sai kiểu không raise, chỉ trả profile không đổi.
   Ba field list (`allergies`/`products`/`medications`) đi qua
   `result.confident_values(threshold)` — dùng `hasattr` để gác, nên object
   thiếu method cũng im lặng cho ra list rỗng. {code}
8. deprecated: không. {code}

### [x] `format_history_block` (`view.py:114-161`)
1. in/out: `(turns, char_budget=2000, max_turns=None) -> str`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: `HISTORY_CHAR_BUDGET`. {code}
6. ai gọi: production `llm/prompt_builder.py:227`, truyền
   `max_turns=HISTORY_WINDOW_TURNS` (=6); test gọi không tham số (thấy 2). {code}
7. invariant có vấn đề: `:137` gán `filtered = turns` rồi `:139-140` kiểm
   `if not filtered: return ""` — cả hai là **tàn dư** của bộ lọc genital đã bị
   gỡ (comment `:133-136` khai rõ). Biến `filtered` không còn lọc gì; nhánh
   `if not filtered` trùng với `if not turns` ở `:129-130`. Code chết nhưng vô
   hại. Ngoài ra `per_turn = max(80, char_budget // max(1, len(tail)))` — với
   `max_turns=6` và budget 2000, mỗi turn được 333 ký tự; sàn 80 nghĩa là
   **budget tổng có thể bị vượt** khi số turn lớn (6 × 80 = 480 < 2000 nên không
   vượt ở cấu hình hiện tại, nhưng với 30 turn thì 30 × 80 = 2400 > 2000). {code+comment}
8. deprecated: `filtered` và nhánh của nó. {code}

### [x] `_fmt` (nested trong `format_history_block`, `view.py:142-145`)
1. in/out: `(turn: ConversationTurn) -> str`; trả `"[User]: ..."` hoặc `"[Assistant]: ..."`. {code}
2. side effect: không. {code}
3. state: không (closure không bắt biến ngoài). {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `:152` và `:157`. {code}
7. invariant: mọi `role` không phải `"user"` đều thành `"Assistant"` — kể cả
   `"system"` nếu ai đó nhét vào (dataclass không chặn, xem `ConversationTurn`). {code}
8. deprecated: không. {code}

---

## `fold.py`

### [x] docstring `fold.py:1-11`
1. in/out: 11 dòng lời khai. {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: "File nguy hiểm nhất trong package: `medication_safety_refusal`
   — cổng tất định DUY NHẤT còn lại — đọc `is_pregnant`, `is_breastfeeding` và
   `medications` do chính các hàm ở đây trả về." **Đối chiếu:** lời khai
   "cổng tất định duy nhất còn lại" **mâu thuẫn** với `guardrails/runner.py:1`
   (khai chính nó là cổng tất định duy nhất) và với `chat/_safety.py` (372 dòng
   khớp chuỗi tất định, được `docs/rulebase_audit.md:161` xếp "Tier 5 — Giữ").
   Ba nơi cùng tự nhận là cổng duy nhất. Xem Q-08. {code+doc}
8. deprecated: không. {doc}

### [x] `_STOP_PRODUCT_TERMS` (`fold.py:18-21`)
1. in/out: tuple 10 chuỗi tiếng Việt (có dấu và không dấu). {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `fold.py:62`. {code}
7. invariant: chứa cả `"bỏ"` — một từ hai ký tự, khớp trong `"bỏ sung"`,
   `"bỏ qua"`, `"bôi bỏ"`... Không có ranh giới từ. Cùng hạng lỗi với các bảng
   term khác trong repo. {code}
8. deprecated: không. {code}

### [x] `_mentions_stop` (`fold.py:24-62`)
1. in/out: `(clean_text: str, value: str) -> bool`. {code}
2. side effect: không. {code}
3. state: không (dict `aliases` dựng lại mỗi lần gọi — hàm này chạy trong vòng
   lặp lồng, mỗi giá trị mỗi snapshot). {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `fold.py:80,86,90,95,220-222,264-266`, `view.py:100,107`. {code}
7. invariant: docstring `:24-39` là lời khai **tự tố cáo**, và code khớp:
   - quét 40 ký tự trước tên thuốc → `"bác sĩ bảo KHÔNG DÙNG isotretinoin chung
     với doxycycline"` gỡ isotretinoin khỏi profile, tắt cổng iso+tetra đúng trên
     câu hỏi về chính tương tác đó;
   - `aliases` key bằng `"salicylic_acid"` trong khi intaker canonical hoá ra
     `"salicylic acid"`; `alias_key = value_lower.replace(" ", "_")` chuyển
     `"salicylic acid"` → `"salicylic_acid"` nên nhánh alias **có** khớp. Comment
     `:48-51` nói nhánh này "chưa từng khớp dữ liệu thật" — **lời khai sai**,
     phép biến đổi ở `:51` chính là thứ làm nó khớp. Xem Q-09.
   {code+comment}
8. deprecated: docstring ghi "KHÔNG mở rộng hàm này thêm" và nêu đường ra
   (intaker phát tín hiệu `medications_stopped[]`). Chưa làm. {doc}

### [x] `_dedupe_values` (`fold.py:65-74`)
1. in/out: `(items: list[str]) -> list[str]`; giữ thứ tự, bỏ trùng, bỏ rỗng. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không (`str(item)` nuốt mọi kiểu). {code}
5. config: không. {code}
6. ai gọi: 15 lần trong `fold.py:281-311`. {code}
7. invariant: so sánh **phân biệt hoa thường** (`seen` chứa chuỗi đã `.strip()`
   nhưng không `.lower()`), trong khi các nhánh gỡ thuốc ở `:227,232` lại so
   bằng `.lower()`. Hai chuẩn so sánh trong cùng một hàm gọi. `"Tretinoin"` và
   `"tretinoin"` sống chung sau dedupe. {code}
8. deprecated: không. {code}

### [x] `snapshot_from_user` (`fold.py:76-104`)
1. in/out: `(user: UserInput, clean_text: str = "") -> NormalizedSnapshot`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `chat/intake.py:766`; test. {code}
7. invariant: `context` dùng `model_dump(exclude_none=True)` còn `clinical` dùng
   `model_dump()` **không** exclude_none — hai nhánh, hai quy ước. Hệ quả:
   snapshot clinical mang đầy key giá trị `None`, và `fold_history_facts` phải
   dùng `or []` khắp nơi để chịu. {code}
8. deprecated: không. {code}

### [x] `_SEVERITY_ORDER` (`fold.py:102`)
1. in/out: `{"unknown": 0, "none": 0, "mild": 1, "moderate": 2, "severe": 3}`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `fold.py:113` (hai lần trong một biểu thức). {code}
7. invariant: `"unknown"` và `"none"` cùng hạng 0 — nên `_max_severity("unknown",
   "none")` trả `"unknown"` (nhánh `>=` giữ `a`). Không ai phụ thuộc điều đó. {code}
8. deprecated: không. {code}

### [x] `_max_severity` (`fold.py:105-113`)
1. in/out: `(a: str | None, b: str | None) -> str | None`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không — `.get(a, 0)` nuốt severity lạ thành hạng 0. {code}
5. config: `_SEVERITY_ORDER`. {code}
6. ai gọi: `fold.py:250`. {code}
7. invariant: giá trị lạ (`"critical"`) tụt về hạng 0 im lặng, thua cả `"mild"`. {code}
8. deprecated: không. {code}

### [x] `fold_history_facts` (`fold.py:116-334`)
1. in/out: `(current: UserInput, history: list[ConversationTurn]) -> UserInput`;
   trả `current.model_copy(update={...})`. 219 dòng — hàm to nhất package. {code}
2. side effect: không (mọi list đều dựng mới). {code}
3. state: không. {code}
4. lỗi: `AcneClinicalInput(...)` ở `:292` raise `ValidationError` nếu
   `inflammation_level` là None — comment `:294-303` kể đúng lỗi này đã xảy ra
   giữa stream, và `:305` vá bằng `inflammation or "unknown"`. {code+comment}
5. config: không đọc `settings`. {code}
6. ai gọi: `chat/intake.py:764`, chỉ khi `is_personal_case` True; test
   `test_session_fold_branches.py` (8 lần). {code}
7. **invariant hỏng — nhánh chết:** `:317-331` tính
   `has_clinical = any((... merged_clinical.inflammation_level ...))`, rồi
   `:333` trả `merged_clinical if has_clinical else None`. Nhưng `:305` vừa ép
   `inflammation_level = inflammation or "unknown"` — luôn là chuỗi khác rỗng,
   luôn truthy. Nên `has_clinical` **luôn True** và nhánh `else None` không bao
   giờ chạy. Bản vá ValidationError ở `:305` đã vô hiệu hoá cái gác ở `:317`.
   Hệ quả: `UserInput.clinical` không bao giờ còn là None sau khi fold, kể cả
   khi không có một tín hiệu lâm sàng nào. Xem Q-10. {code}
8. deprecated: không. {code}

---

## §5 — Điều tìm được (câu hỏi)

**Q-01 — `SESSION_TTL` có hai nguồn sự thật, và nguồn `.env` không tới được store.**
`models.py:61` đặt `SESSION_TTL = 1800.0`; `config.py:250` đặt
`session_ttl: float = 1800.0`. Cả `SessionStore()` (`memory.py:194`) lẫn
`Session.is_expired` (`models.py:117`) đều lấy hằng module. Đặt `SESSION_TTL=60`
trong `.env` chỉ đổi `settings.session_ttl` — cần kiểm ở `src.db` xem
`SQLiteSessionStore` có đọc `settings` không, vì đó mới là store chạy thật. {code}

**Q-02 — `SESSION_SCHEMA_VERSION` có người đọc, nhưng chỉ ở một trong hai store.**
`db/session_store.py:127` dùng nó để reset row lệch phiên bản; bản in-memory
không kiểm. Đây là điểm lệch thứ ba giữa hai store (hai điểm kia: các field
intent đã xoá, và `asked_fields`). Kiểm đủ ở `src.db`. {code}

**Q-03 — `format_history_block` có hai hành vi mặc định khác nhau.**
Production truyền `max_turns=HISTORY_WINDOW_TURNS` (6) từ
`llm/prompt_builder.py:228`; default của hàm là 2 (`view.py:149`). Test gọi
không tham số nên đo hành vi 2-turn, production chạy 6-turn. Bất kỳ test nào
khẳng định về nội dung history block đều **không** đo cái production làm. {code+test}

**Q-04 — bốn method không `touch()`, nên session bị hết hạn oan.**
`merge_user_context`, `get_user_context`, `increment_followup_count`, `delete`
đều không gọi `Session.touch()`. Một phiên chỉ cập nhật profile mà không append
turn sẽ già đi như thể không ai dùng. Cần kiểm bản SQLite có cùng lỗ không. {code}

**Q-05 — `memory.py` là test double sống trong `src/`.**
Docstring của chính nó khai điều đó, và grep xác nhận: `get_session_store` được
gọi 13 lần, **tất cả** trong `tests/`. 195 dòng code production-shaped mà không
đường production nào chạy qua. Với khoá luận, đây là thứ giám khảo sẽ hỏi: hoặc
chuyển vào `tests/`, hoặc ghi rõ trong báo cáo là in-memory reference
implementation dùng để đối chiếu hành vi với bản SQLite. {code+doc}

**Q-06 — (rút lại)** Ghi chú ban đầu của tôi nói `increment_followup_count` và
`active_count` không có caller nào. Sai: `chat/runtime.py:95-96` và
`api/routes/admin.py:41` **có** gọi hai tên đó, chỉ là gọi trên
`SQLiteSessionStore` chứ không phải lớp trong file này. Đã sửa tại chỗ ở hai
khối tương ứng. Không còn là câu hỏi.

**Q-07 — `select_relevant_history` có 2/4 tham số chết.**
`view.py:33`: `del message, route_flags`. `chat/intake.py:572,731` vẫn tính và
truyền chúng. Chữ ký nói hàm dùng nội dung tin nhắn và route flags để chọn
history; thực tế nó chỉ nhìn `primary_intent`. Docstring `:28-31` giải thích lý
do bỏ whitelist tiền tố nhưng không nói hai tham số đã thành vô nghĩa. {code+doc}

**Q-08 — ba nơi cùng tự nhận là "cổng tất định duy nhất còn lại".**
`fold.py:3-4` (nói `medication_safety_refusal` là cổng duy nhất),
`guardrails/runner.py:1` (nói chính nó là cổng duy nhất), và `chat/_safety.py`
(372 dòng khớp chuỗi tất định, `docs/rulebase_audit.md:161` xếp "Tier 5 — Giữ").
Ba lời khai không thể cùng đúng. Cần một câu trả lời dứt khoát trước khi viết
chương kiến trúc của báo cáo. {code+doc}

**Q-09 — comment `fold.py:48-51` khai sai về chính dòng ngay dưới nó.**
Comment nói nhánh alias "chưa từng khớp dữ liệu thật" vì intaker trả
`"salicylic acid"` (dấu cách) còn key là `"salicylic_acid"` (gạch dưới). Nhưng
`:51` làm đúng phép chuyển đó: `alias_key = value_lower.replace(" ", "_")`.
Nhánh alias **có** khớp. Cần quyết: comment sai (xoá) hay code từng khác (thì
comment là hoá thạch). Không phải lỗi hành vi, nhưng là lời khai sai trong file
mà docstring gọi là "nguy hiểm nhất trong package". {code+comment}

**Q-10 — nhánh chết ở `fold_history_facts`: `clinical` không bao giờ còn là None.**
`:305` ép `inflammation_level = inflammation or "unknown"`. `:317-331` rồi tính
`has_clinical = any((..., merged_clinical.inflammation_level, ...))`. Chuỗi
`"unknown"` luôn truthy → `has_clinical` **luôn True** → `:333`
`merged_clinical if has_clinical else None` không bao giờ trả None.
Hệ quả thật: sau khi fold, `UserInput.clinical` luôn là object đầy đủ, kể cả với
hai lượt liên tiếp không có một tín hiệu lâm sàng nào — đúng tổ hợp mà comment
`:296-301` mô tả. Downstream nào phân biệt "có clinical" bằng
`user.clinical is not None` sẽ luôn thấy True. Bản vá ValidationError đã vô hiệu
hoá cái gác ngay dưới nó. Cần kiểm ở `src.chat` xem có ai dựa vào
`clinical is None` không. {code}

---

## §6 — Tự kiểm (Bước 4)

- Khối khai báo ở Bước 0: **44** (2 + 11 + 16 + 7 + 8)
- Khối `### [x]` đếm được: 44 — khớp.
- Mục: 44 × 8 = **352**.
- Không dùng nén khai báo trong module này; mọi khối viết đủ 8 mục.

**Đính chính đã áp trong lượt này:** ba khẳng định "0 caller" của tôi bị chính
grep bác bỏ (`SESSION_SCHEMA_VERSION`, `increment_followup_count`,
`active_count`). Đã sửa tại chỗ trước khi chốt, và ghi lại ở Q-02, Q-06.
