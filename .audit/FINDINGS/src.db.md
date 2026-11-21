# FINDINGS / src.db

Module: `src/acne_llm/db/` — 4 file, 602 LOC
(`__init__.py` 5, `base.py` 100, `audit.py` 175, `session_store.py` 322).

**Phép đếm khối (Bước 0):**
- `__init__.py`: 1 lời khai + `__all__` = **2**
- `base.py`: 1 lời khai + `_SCHEMA` + `_AUDIT_EXTRA_COLUMNS` + `_ensure_audit_columns`
  + `DBConnection` + 6 method (`__init__`, `_get_conn`, `execute`, `executemany`,
  `commit`, `close`) = **11**
- `audit.py`: 1 lời khai + `AuditEntry` + `AuditStore` + 7 method (`__init__`,
  `log`, `query`, `count`, `log_feedback`, `feedback_stats`, `recent_feedback`) = **10**
- `session_store.py`: 1 lời khai + `_SCHEMA` + `SQLiteSessionStore` + 20 method = **23**

→ **46 khối × 8 mục = 368 mục.**

---

## `__init__.py`

### [x] docstring `__init__.py:1`
1. in/out: 1 dòng. {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: "SQLite sessions + SQLite audit log". Đúng — hai file,
   **hai DB tách rời** (`sessions.db` và `audit.db`), không dùng chung connection. {code+doc}
8. deprecated: không. {doc}

### [x] `__all__` (`__init__.py:5`)
1. in/out: `["SQLiteSessionStore", "AuditStore"]`. {code}
2-5. không. {code}
6. ai gọi: `import *` = 0 kết quả toàn repo. Vô dụng như `chat/session/__init__.py`. {code}
7. invariant: **không export `DBConnection`**, nhưng `di.py:24` vẫn import nó
   trực tiếp từ `.db.base`. Mặt tiền công khai và cách dùng thật không khớp. {code}
8. deprecated: không. {code}

---

## `base.py`

### [x] docstring `base.py:1`
1. in/out: 1 dòng — "SQLite connection + schema init dùng chung cho session store và audit log". {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. **invariant khai báo SAI:** `DBConnection` **không** được session store dùng.
   `session_store.py:77` tự `sqlite3.connect` và tự `executescript(_SCHEMA)`
   riêng, và `session_store.py:5` nói rõ "không phụ thuộc audit schema ở
   db/base.py". `DBConnection` chỉ có đúng một người dùng: `di.py:105` →
   `AuditStore`. Xem Q-01. {code+doc}
8. deprecated: không. {doc}

### [x] `_SCHEMA` (`base.py:11-47`)
1. in/out: chuỗi DDL — 2 bảng (`audit_log`, `feedback`), 4 index, 2 PRAGMA. {code}
2. side effect: khi chạy, tạo bảng/index. {code}
3. state: hằng module. {code}
4. lỗi: `executescript` raise nếu DDL sai. {code}
5. config: không. {code}
6. ai gọi: `base.py:75`. {code}
7. invariant: `feedback.rating TEXT NOT NULL CHECK(rating IN ('up','down'))` —
   ràng buộc **trùng lặp** với kiểm ở tầng Python (`audit.py:120-121`). Hai lớp
   gác cùng một điều; lớp DB mới là lớp không bỏ sót được. `audit_id INTEGER
   REFERENCES audit_log(id)` là FK **liên bảng trong cùng DB** — hợp lệ vì cả hai
   ở `audit.db`. {code}
8. deprecated: comment `:8-10` khai "sessions và turns đã chuyển sang JSONL
   (data/sessions/<id>.jsonl)". **Sai với hiện tại:** `session_store.py:1` nói
   ngược lại — "một file sessions.db thay cho nhiều file JSONL". Comment này là
   hoá thạch của bước JSONL ở giữa, đã bị bước SQLite vượt qua. Xem Q-02. {code+comment}

### [x] `_AUDIT_EXTRA_COLUMNS` (`base.py:49-54`)
1. in/out: dict 4 cột → DDL fragment. {code}
2-3. hằng module. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `base.py:61`. {code}
7. invariant: 4 cột trong dict (`normalized_query`, `extracted_entities`,
   `pii_detected`, `teencode_replaced`) **cũng có** trong `_SCHEMA` ở `:26-29`.
   Nghĩa là DB mới tạo có sẵn chúng; dict chỉ phục vụ DB cũ. Hai khai báo phải
   giữ đồng bộ bằng tay — thêm cột mà quên một trong hai chỗ là lệch im lặng. {code}
8. deprecated: không. {code}

### [x] `_ensure_audit_columns` (`base.py:57-63`)
1. in/out: `(conn: sqlite3.Connection) -> None`. {code}
2. side effect: `ALTER TABLE audit_log ADD COLUMN ...`. {code}
3. state: sửa schema DB. {code}
4. lỗi: `sqlite3.OperationalError` nếu ALTER hỏng — **không bắt**, nên
   `DBConnection.__init__` raise. `di.py:104-107` có try/except bọc ngoài và
   rơi về DB tạm trong `tempfile.gettempdir()`. {code}
5. config: `_AUDIT_EXTRA_COLUMNS`. {code}
6. ai gọi: `base.py:76`. {code}
7. invariant: migration **một chiều, chỉ thêm cột** — không có bản tương ứng cho
   `sessions`/`turns` ở `session_store.py`. Đổi schema session phải dựa hoàn toàn
   vào `SESSION_SCHEMA_VERSION` + reset. Hai chiến lược migration khác nhau trong
   cùng một module. {code}
8. deprecated: không. {code}

### [x] `DBConnection` (`base.py:66-100`)
1. in/out: `DBConnection(db_path: str)`. {code}
2. side effect: tạo thư mục cha, chạy schema. {code}
3. state: `_db_path`, `_local` (threading.local). {code}
4. lỗi: raise từ `__init__` nếu không tạo được file/schema. {code}
5. config: `settings.audit_db_path` (qua `di.py:96`). {code}
6. ai gọi: `di.py:105` (và fallback `:110` nếu lần đầu hỏng). Một người dùng duy nhất. {code}
7. invariant: docstring nói "một connection per thread via threading.local" —
   code khớp (`_get_conn`). Nhưng **không có lock**; `AuditStore` tự lock cho
   ghi. Đọc không lock — an toàn với SQLite WAL. {code}
8. deprecated: không. {code}

### [x] `DBConnection.__init__` (`base.py:69-76`)
1. in/out: `(self, db_path: str) -> None`. {code}
2. side effect: `mkdir(parents=True, exist_ok=True)`; mở connection riêng để chạy DDL. {code}
3. state: khởi tạo 2 thuộc tính. {code}
4. lỗi: `OSError` nếu không tạo được thư mục; `sqlite3.Error` nếu DDL hỏng. {code}
5. config: `db_path` từ người gọi. {code}
6. ai gọi: `di.py:105,110`. {code}
7. invariant: `with sqlite3.connect(...) as conn` — context manager của sqlite3
   **commit transaction**, nó **không đóng connection**. Connection dùng để chạy
   DDL bị bỏ lại cho GC. Không rò rỉ đáng kể vì chỉ chạy một lần, nhưng là mẫu
   sai phổ biến và nên ghi ra. {code}
8. deprecated: không. {code}

### [x] `DBConnection._get_conn` (`base.py:78-86`)
1. in/out: `(self) -> sqlite3.Connection`. {code}
2. side effect: mở connection mới cho thread chưa có. {code}
3. state: `self._local.conn`. {code}
4. lỗi: `sqlite3.Error` nếu mở hỏng. {code}
5. config: `check_same_thread=False` + WAL + `foreign_keys=ON`. {code}
6. ai gọi: `execute`, `executemany`, `commit`, `close`. {code}
7. invariant: `check_same_thread=False` **cộng với** threading.local là thừa một
   nửa — local đã đảm bảo mỗi thread một connection. Cờ này chỉ cần nếu
   connection bị chuyển giữa thread, điều mà thiết kế này cấm. Vô hại. {code}
8. deprecated: không. {code}

### [x] `DBConnection.execute` (`base.py:88-89`)
1. in/out: `(sql: str, params: tuple = ()) -> sqlite3.Cursor`. {code}
2. side effect: tuỳ SQL. {code}
3. state: không của chính nó. {code}
4. lỗi: mọi `sqlite3.Error` nổi lên người gọi. {code}
5. config: không. {code}
6. ai gọi: `audit.py` — 8 chỗ. {code}
7. invariant: **không tự commit**. Người gọi phải gọi `commit()`. `AuditStore.log`
   và `log_feedback` có; `query`/`count`/`feedback_stats`/`recent_feedback` là
   SELECT nên không cần. {code}
8. deprecated: không. {code}

### [x] `DBConnection.executemany` (`base.py:91-92`)
1. in/out: `(sql: str, params_seq) -> sqlite3.Cursor`. {code}
2-3. như `execute`. {code}
4. lỗi: như `execute`. {code}
5. config: không. {code}
6. ai gọi: **0 chỗ** — grep `executemany` toàn repo chỉ ra dòng định nghĩa này. {code}
7. invariant: `params_seq` không có type hint. {code}
8. deprecated: không đánh dấu, 0 caller. Xem Q-03. {code}

### [x] `DBConnection.commit` (`base.py:94-95`)
1. in/out: `() -> None`. {code}
2. side effect: commit transaction của thread hiện tại. {code}
3. state: không. {code}
4. lỗi: `sqlite3.Error`. {code}
5. config: không. {code}
6. ai gọi: `audit.py:65,130`. {code}
7. invariant: commit **connection của thread gọi** — đúng ngữ nghĩa vì
   `execute` cũng chạy trên connection đó. {code}
8. deprecated: không. {code}

### [x] `DBConnection.close` (`base.py:97-100`)
1. in/out: `() -> None`. {code}
2. side effect: đóng connection của thread hiện tại. {code}
3. state: đặt `_local.conn = None`. {code}
4. lỗi: không bắt. {code}
5. config: không. {code}
6. ai gọi: **0 chỗ** trong `src/`. {code}
7. invariant: chỉ đóng được connection của **chính thread gọi** — connection của
   các thread worker khác không bao giờ được đóng. Với server sống lâu thì đây là
   rò rỉ file descriptor theo số thread. Xem Q-03. {code}
8. deprecated: 0 caller. {code}

---

## `audit.py`

### [x] docstring `audit.py:1`
1. in/out: 1 dòng — "ghi nhận mọi tư vấn y tế cho trách nhiệm pháp lý và debug". {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. **invariant khai báo mâu thuẫn với code:** lời khai đặt mục tiêu *trách nhiệm
   pháp lý*, nhưng `log()` (`:41-67`) bọc toàn bộ trong `try/except Exception` và
   chỉ `logger.warning`. Một audit log dùng cho pháp lý mà mất bản ghi im lặng thì
   không dùng được cho pháp lý. Xem Q-04. {code+doc}
8. deprecated: không. {doc}

### [x] `AuditEntry` (`audit.py:15-29`)
1. in/out: dataclass 13 field. {code}
2. side effect: `timestamp` gọi `time.time()` khi dựng. {code}
3. state: mutable. {code}
4. lỗi: không validate. {code}
5. config: không. {code}
6. ai gọi: `chat/runtime.py:287` — chỗ dựng duy nhất trong production. {code}
7. invariant: 13 field của dataclass so với 13 cột được INSERT ở `:44-48` —
   khớp về số, nhưng cột `id` là AUTOINCREMENT nên bảng có 14 cột. Kiểm tay:
   dataclass không có field `id`. Đúng. {code}
8. deprecated: không. {code}

### [x] `AuditStore` (`audit.py:32-175`)
1. in/out: `AuditStore(db: DBConnection)`. {code}
2. side effect: ghi/đọc `audit.db`. {code}
3. state: `_db`, `_lock` (threading.Lock). {code}
4. lỗi: `log`/`log_feedback` nuốt; các method đọc thì không. {code}
5. config: không đọc `settings`; nhận `DBConnection` từ `di.py:108`. {code}
6. ai gọi: `di.py:108` dựng; `api/routes/admin.py` và `api/routes/chat.py` dùng. {code}
7. invariant: docstring nói "dùng chung DBConnection với session store" —
   **sai**, session store không dùng `DBConnection` (xem Q-01). {code+doc}
8. deprecated: không. {code}

### [x] `AuditStore.__init__` (`audit.py:35-37`)
1. in/out: `(self, db: DBConnection) -> None`. {code}
2. side effect: không. {code}
3. state: gán 2 thuộc tính. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `di.py:108`. {code}
7. invariant: dùng `threading.Lock` (không tái nhập) — đúng, vì không method nào
   gọi method khác cùng lớp trong lúc giữ lock. Kiểm tay 6 method: đúng. {code}
8. deprecated: không. {code}

### [x] `AuditStore.log` (`audit.py:39-67`)
1. in/out: `(entry: AuditEntry) -> None`. {code}
2. side effect: INSERT + commit. {code}
3. state: DB. {code}
4. **lỗi: nuốt tất cả.** `except Exception` → `logger.warning`. Người gọi
   (`runtime.py:287`) không có cách nào biết bản ghi đã mất. {code}
5. config: không. {code}
6. ai gọi: `chat/runtime.py:287`, sau khi gác `getattr(c, "audit_store", None)`. {code}
7. invariant: `pii_detected` được ép `1 if ... else 0` (`:61`) vì SQLite không có
   kiểu bool; `query()` ép ngược lại bằng `bool(...)` ở `:93`. Cặp ép này khớp. {code}
8. deprecated: không. {code}

### [x] `AuditStore.query` (`audit.py:69-95`)
1. in/out: `(session_id=None, limit=50, offset=0) -> list[dict]`. {code}
2. side effect: không. {code}
3. state: chỉ đọc. {code}
4. lỗi: `json.loads` raise `JSONDecodeError` nếu cột JSON hỏng — **không bắt**,
   trong khi `_row_to_turn` của session store thì có bắt. Hai chuẩn xử lý JSON
   hỏng trong cùng module. {code}
5. config: không. {code}
6. ai gọi: `api/routes/admin.py:29`. {code}
7. invariant: `SELECT *` — thêm cột vào `audit_log` là tự động lọt ra API response.
   Endpoint này được `admin_api_key` bảo vệ (`config.py:270-274`), nên rò rỉ chỉ
   trong phạm vi admin. {code}
8. deprecated: không. {code}

### [x] `AuditStore.count` (`audit.py:97-107`)
1. in/out: `(session_id=None) -> int`. {code}
2. side effect: không. {code}
3. state: chỉ đọc. {code}
4. lỗi: `sqlite3.Error` nổi lên. {code}
5. config: không. {code}
6. ai gọi: `api/routes/admin.py:30`. {code}
7. invariant: không lấy `_lock` — an toàn cho đọc dưới WAL. {code}
8. deprecated: không. {code}

### [x] `AuditStore.log_feedback` (`audit.py:111-134`)
1. in/out: `(message_id, rating, session_id=None, audit_id=None, comment="") -> int`. {code}
2. side effect: INSERT + commit. {code}
3. state: DB. {code}
4. lỗi: `ValueError` nếu `rating` không thuộc `("up","down")` — **raise trước
   try**, nên nó thoát ra ngoài (khác với lỗi DB, bị nuốt và trả 0). Hai hành vi
   lỗi trong một hàm. {code}
5. config: không. {code}
6. ai gọi: `api/routes/chat.py:229`. {code}
7. invariant: trả `0` vừa nghĩa "ghi hỏng" vừa có thể là rowid hợp lệ nếu
   `lastrowid` là None. SQLite AUTOINCREMENT bắt đầu từ 1, nên 0 an toàn làm
   sentinel — nhưng đó là may, không phải hợp đồng. {code}
8. deprecated: không. {code}

### [x] `AuditStore.feedback_stats` (`audit.py:136-155`)
1. in/out: `() -> dict` — `{"up","down","total","satisfaction_rate"}`. {code}
2. side effect: không. {code}
3. state: chỉ đọc. {code}
4. lỗi: `sqlite3.Error` nổi lên. {code}
5. config: không. {code}
6. ai gọi: `api/routes/admin.py:51`. {code}
7. invariant: bảng rỗng → `SUM(...)` trả NULL, `COUNT(*)` trả 0 → nhánh
   `if not row or not row["total"]` bắt được, trả `satisfaction_rate=None` thay
   vì chia cho 0. Đúng. Dòng `:155` còn một `if total else None` thừa — nhánh
   `total == 0` đã return ở `:146`. {code}
8. deprecated: không. {code}

### [x] `AuditStore.recent_feedback` (`audit.py:157-175`)
1. in/out: `(rating=None, limit=50, offset=0) -> list[dict]`. {code}
2. side effect: không. {code}
3. state: chỉ đọc. {code}
4. lỗi: `sqlite3.Error` nổi lên. {code}
5. config: không. {code}
6. ai gọi: `api/routes/admin.py:66`; route đã chặn rating bằng
   `pattern="^(up|down)$"` (`admin.py:57`) nên giá trị lạ không tới đây. {code}
7. invariant: khác `query()`, hàm này **không** parse JSON cột nào — bảng
   `feedback` không có cột JSON. Đúng. {code}
8. deprecated: không. {code}

---

## `session_store.py`

### [x] docstring `session_store.py:1-12`
1. in/out: 12 dòng lời khai. {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: "Session store duy nhất của hệ thống"; "Tự quản schema
   riêng trong file DB độc lập, không phụ thuộc audit schema ở db/base.py"; và 4
   dòng ngữ nghĩa (TTL lazy, schema_version lệch → reset, append-only,
   user_context last-write-wins per key). **Đối chiếu code:** cả 4 dòng ngữ nghĩa
   đều đúng — nhưng "TTL xoá lazy" chỉ đúng ở 5/8 method công khai (xem Q-05), và
   "schema_version lệch → reset" chỉ đúng ở 3/8 (xem Q-06). "Store duy nhất" đúng
   với production: `di.py:94` wire lớp này, không nhánh dự phòng. {code+doc}
8. deprecated: không. {doc}

### [x] `_SCHEMA` (`session_store.py:31-59`)
1. in/out: DDL — bảng `sessions`, bảng `turns`, 1 index, 2 PRAGMA. {code}
2. side effect: khi chạy, tạo bảng. {code}
3. state: hằng module. {code}
4. lỗi: raise nếu DDL sai. {code}
5. config: không. {code}
6. ai gọi: `session_store.py:78`. {code}
7. invariant: `turns.session_id ... REFERENCES sessions(session_id) ON DELETE
   CASCADE` + `PRAGMA foreign_keys=ON` được đặt lại trên **mỗi** connection
   (`:88`) — cần thiết, vì PRAGMA này là per-connection ở SQLite. Nếu thiếu, xoá
   session sẽ bỏ lại turn mồ côi. Đặt đúng chỗ. {code}
8. deprecated: cột `asked_fields` — comment `:284-286` khai cơ chế đã gỡ ở
   `runtime.py`, cột giữ lại để tránh một lần migration. Dữ liệu chết có chủ đích. {code+comment}

### [x] `SQLiteSessionStore` (`session_store.py:62-322`)
1. in/out: `SQLiteSessionStore(db_path, ttl=SESSION_TTL, max_turns=0)`. {code}
2. side effect: tạo file DB + schema khi dựng. {code}
3. state: `_db_path`, `ttl`, `max_turns`, `_local`, `_lock` (RLock). {code}
4. lỗi: `__init__` raise nếu không tạo được DB; **không có** try/except bọc ở
   `di.py:94` (khác `DBConnection`, vốn có fallback tempdir ở `di.py:104-110`).
   Sessions DB hỏng = server không khởi động được. {code}
5. config: `di.py:89-94` truyền `ttl=getattr(settings,"session_ttl",1800.0)` và
   `max_turns=HISTORY_WINDOW_TURNS` (=6). Đây là điểm **duy nhất** trong hệ mà
   `.env SESSION_TTL` thực sự có hiệu lực. {code}
6. ai gọi: `di.py:94`; test `test_sqlite_session_store.py`, `test_intake.py`,
   `test_chat_stream.py`. {code}
7. invariant: interface trùng khít 8 method công khai với `chat/session/memory.py`
   (`SessionStore`), thừa `close`. Kiểm tay: `get_or_create`, `get_history`,
   `append_turn`, `merge_user_context`, `get_user_context`,
   `increment_followup_count`, `delete`, `active_count` — 8/8 có ở cả hai. {code}
8. deprecated: không. {code}

### [x] `SQLiteSessionStore.__init__` (`session_store.py:65-79`)
1. in/out: `(db_path, ttl=SESSION_TTL, max_turns=0) -> None`. {code}
2. side effect: mkdir, executescript, `logger.info`. {code}
3. state: 5 thuộc tính. {code}
4. lỗi: `OSError` / `sqlite3.Error` nổi lên. {code}
5. config: default `max_turns=0` (= không giới hạn) **khác** default 6 của bản
   in-memory. Production truyền 6 tường minh nên không lệch; test dựng
   `SQLiteSessionStore(db)` không tham số thì đo hành vi không-giới-hạn. {code}
6. ai gọi: `di.py:94` + test. {code}
7. invariant: `with sqlite3.connect(...) as conn` — cùng mẫu sai như
   `DBConnection.__init__`: context manager commit chứ không đóng. {code}
8. deprecated: không. {code}

### [x] `SQLiteSessionStore._conn` (`session_store.py:83-90`)
1. in/out: `() -> sqlite3.Connection`. {code}
2. side effect: mở connection cho thread mới. {code}
3. state: `_local.conn`. {code}
4. lỗi: `sqlite3.Error`. {code}
5. config: WAL + `foreign_keys=ON` + `check_same_thread=False`. {code}
6. ai gọi: 12 method trong lớp. {code}
7. invariant: dùng `getattr(self._local, "conn", None) is None` — gọn hơn cặp
   `hasattr` + kiểm None của `DBConnection._get_conn:80`. Hai file cùng module,
   hai cách viết cho cùng một việc. {code}
8. deprecated: không. {code}

### [x] `SQLiteSessionStore._is_valid_sid` (`session_store.py:94-95`)
1. in/out: `(session_id: str | None) -> bool`. {code}
2-3. không. {code}
4. lỗi: `AttributeError` nếu truyền non-str. {code}
5. config: không. {code}
6. ai gọi: 8 method công khai. {code}
7. invariant: **bản sao từng ký tự** của `memory.py:50-51`. Trùng lặp giữa hai
   store, không có chỗ dùng chung. {code}
8. deprecated: không. {code}

### [x] `SQLiteSessionStore._is_expired` (`session_store.py:97-98`)
1. in/out: `(last_active: float) -> bool`. {code}
2-3. không. {code}
4. lỗi: không (`float(last_active or 0)`). {code}
5. config: `self.ttl`. {code}
6. ai gọi: `_stale:125`, `merge_user_context:253`, `get_user_context:279`,
   `increment_followup_count:294`. {code}
7. invariant: `last_active = 0` (falsy) → `time.time() - 0` luôn > ttl → coi là
   hết hạn. Hợp lý làm fail-safe. {code}
8. deprecated: không. {code}

### [x] `SQLiteSessionStore._row` (`session_store.py:100-103`)
1. in/out: `(sid: str) -> sqlite3.Row | None`. {code}
2. side effect: không. {code}
3. state: chỉ đọc. {code}
4. lỗi: `sqlite3.Error`. {code}
5. config: không. {code}
6. ai gọi: `_ensure`, `get_or_create`, `get_history`, `merge_user_context`,
   `get_user_context`, `increment_followup_count`. {code}
7. invariant: `SELECT *` — thêm cột vào `sessions` không làm hỏng gì vì mọi chỗ
   đọc đều theo tên cột. {code}
8. deprecated: không. {code}

### [x] `SQLiteSessionStore._delete` (`session_store.py:105-108`)
1. in/out: `(sid: str) -> None`. {code}
2. side effect: DELETE + commit; **cascade xoá `turns`** nhờ FK. {code}
3. state: DB. {code}
4. lỗi: `sqlite3.Error`. {code}
5. config: không. {code}
6. ai gọi: `_ensure:133`, `get_history:200`, `merge_user_context:255`,
   `get_user_context:280`, `increment_followup_count:296`, `delete:309`. {code}
7. invariant: cascade chỉ chạy khi `foreign_keys=ON` trên connection đang dùng —
   `_conn:88` đặt PRAGMA đó. Nếu ai đó thêm đường tạo connection khác mà quên
   PRAGMA, turn mồ côi tích lại im lặng. {code}
8. deprecated: không. {code}

### [x] `SQLiteSessionStore._create` (`session_store.py:110-119`)
1. in/out: `(sid: str) -> None`. {code}
2. side effect: INSERT + commit. {code}
3. state: DB. {code}
4. lỗi: `sqlite3.IntegrityError` nếu sid đã tồn tại — người gọi (`_ensure`) luôn
   `_delete` trước nên không xảy ra. {code}
5. config: ghi `SESSION_SCHEMA_VERSION` vào row mới. {code}
6. ai gọi: `_ensure:134`. {code}
7. invariant: `created_at` và `last_active` cùng `now` — nên session mới không
   bao giờ hết hạn ngay. {code}
8. deprecated: không. {code}

### [x] `SQLiteSessionStore._stale` (`session_store.py:121-127`)
1. in/out: `(row) -> bool`. {code}
2. side effect: không. {code}
3. state: chỉ đọc. {code}
4. lỗi: không. {code}
5. config: `self.ttl` (gián tiếp), `SESSION_SCHEMA_VERSION`. {code}
6. ai gọi: `_ensure:132`, `get_history:199`. **Chỉ 2 chỗ.** {code}
7. invariant: `row is None → False` — "không có row" không phải "row cũ". Người
   gọi phải tự kiểm None, và cả hai đều có. {code}
8. deprecated: không. {code}

### [x] `SQLiteSessionStore._ensure` (`session_store.py:129-136`)
1. in/out: `(sid: str) -> sqlite3.Row`. {code}
2. side effect: có thể xoá + tạo lại session. {code}
3. state: DB. {code}
4. lỗi: `sqlite3.Error`. {code}
5. config: không. {code}
6. ai gọi: `get_or_create:176`, `append_turn:220`. {code}
7. invariant: reset là **xoá rồi tạo** → cascade xoá hết `turns`. Đúng ngữ nghĩa
   "schema_version lệch → reset session" ở docstring `:9`. {code}
8. deprecated: không. {code}

### [x] `SQLiteSessionStore._touch` (`session_store.py:138-141`)
1. in/out: `(sid: str) -> None`. {code}
2. side effect: UPDATE + commit. {code}
3. state: DB. {code}
4. lỗi: `sqlite3.Error`. {code}
5. config: không. {code}
6. ai gọi: `get_or_create:177`, `append_turn:245`. **Chỉ 2 chỗ** — giống hệt lỗ
   hổng của bản in-memory (Q-04 trong `src.chat.session`): `merge_user_context`,
   `get_user_context`, `increment_followup_count` không làm tươi `last_active`. {code}
7. invariant: mỗi lần `touch` là một UPDATE + commit riêng; `append_turn` do đó
   commit **hai lần** (`:244` và `:245`). Không sai, chỉ tốn. {code}
8. deprecated: không. {code}

### [x] `SQLiteSessionStore._row_to_turn` (`session_store.py:143-167`)
1. in/out: `(r: sqlite3.Row) -> ConversationTurn`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `json.loads` của `normalized_snapshot` và `metadata` **có** bắt
   `(ValueError, TypeError)`; `json.loads(r["used_chunks"] or "[]")` ở `:164`
   **không bắt** → JSON hỏng ở cột đó làm hỏng cả `get_history`. Ba cột JSON, hai
   chuẩn xử lý. {code}
5. config: không. {code}
6. ai gọi: `get_history:213`. {code}
7. invariant: dựng lại `NormalizedSnapshot` từ 3 key, khớp đúng 3 field mà
   `append_turn:223-227` ghi. Không khôi phục field intent nào — khớp với comment
   `chat/session/models.py:94-97` (các field đó đã bị xoá khỏi dataclass, nên
   giờ đây là nhất quán chứ không còn là lệch). {code}
8. deprecated: không. {code}

### [x] `SQLiteSessionStore.get_or_create` (`session_store.py:171-189`)
1. in/out: `(session_id) -> Session | None`. {code}
2. side effect: có thể tạo/reset session; `_touch`. {code}
3. state: DB. {code}
4. lỗi: `sqlite3.Error`; `json.loads` của `user_context`/`asked_fields` không bắt. {code}
5. config: không. {code}
6. ai gọi: production — `chat/intake.py` và `chat/runtime.py` qua `c.session_store`. {code}
7. invariant: gọi `self.get_history(sid)` ở `:181` **bên trong** `with self._lock`,
   mà `get_history` cũng lấy `self._lock`. Đây là lý do lớp dùng `RLock` chứ không
   `Lock` — với `Lock` thường sẽ deadlock ngay lần gọi đầu. Ràng buộc này không
   được ghi ở đâu; ai đổi `RLock` thành `Lock` sẽ treo server. Xem Q-07. {code}
8. deprecated: không. {code}

### [x] `SQLiteSessionStore.get_history` (`session_store.py:191-213`)
1. in/out: `(session_id) -> list[ConversationTurn]`. {code}
2. side effect: có thể `_delete` nếu stale. {code}
3. state: DB. {code}
4. lỗi: xem `_row_to_turn`. {code}
5. config: `self.max_turns` (=6 ở production). {code}
6. ai gọi: `get_or_create:181`, và production qua `c.session_store`. {code}
7. invariant: nhánh có giới hạn dùng `ORDER BY timestamp DESC, id DESC LIMIT ?`
   rồi `reversed(rows)` — đúng cách lấy N turn **mới nhất** theo thứ tự cũ→mới.
   Tie-break bằng `id` xử lý được hai turn cùng `timestamp` (khả năng thật vì
   `time.time()` độ phân giải thấp trên Windows). Nhánh không giới hạn dùng
   `ASC, ASC`. Hai nhánh nhất quán về thứ tự trả về. {code}
8. deprecated: không. {code}

### [x] `SQLiteSessionStore.append_turn` (`session_store.py:215-245`)
1. in/out: `(session_id, turn: ConversationTurn) -> None`. {code}
2. side effect: INSERT turn, có thể UPDATE `total_clarify_count`, commit, `_touch`. {code}
3. state: DB. {code}
4. lỗi: `sqlite3.Error`. {code}
5. config: không. {code}
6. ai gọi: production qua `c.session_store`. {code}
7. invariant: **append-only** — khác bản in-memory, vốn cắt list còn `max_turns`
   (`memory.py:120-121`). Ở đây `max_turns` chỉ áp lúc **đọc**. Hệ quả: bảng
   `turns` phình theo toàn bộ lịch sử phiên; không có job dọn. Docstring `:10`
   khai đúng điều này ("Lịch sử append-only"). {code}
8. deprecated: không. {code}

### [x] `SQLiteSessionStore.merge_user_context` (`session_store.py:247-269`)
1. in/out: `(session_id, context: dict) -> None`. {code}
2. side effect: UPDATE nếu có thay đổi. {code}
3. state: DB. {code}
4. lỗi: `json.loads(row["user_context"])` không bắt. {code}
5. config: không. {code}
6. ai gọi: `chat/intake.py:758` (qua `store.merge_user_context`). {code}
7. invariant: chỉ kiểm `_is_expired`, **không** kiểm `_stale` → session lệch
   `schema_version` vẫn nhận được context mới. Và không `_touch`. Hai điểm này
   khác `get_history`. Xem Q-05, Q-06. Cũng như bản in-memory, `{"allergies": []}`
   ghi đè list cũ bằng rỗng (`v is not None` cho list rỗng đi qua). {code}
8. deprecated: không. {code}

### [x] `SQLiteSessionStore.get_user_context` (`session_store.py:271-282`)
1. in/out: `(session_id) -> dict`. {code}
2. side effect: có thể `_delete` nếu hết hạn. {code}
3. state: DB. {code}
4. lỗi: `json.loads` không bắt. {code}
5. config: không. {code}
6. ai gọi: `chat/intake.py:741`. {code}
7. invariant: **có** kiểm hết hạn ở đây — trong khi bản in-memory
   (`memory.py:141-148`) **không** kiểm. Đây là một lệch hành vi thật giữa hai
   store, và nó nằm đúng ở đường mà test in-memory hay chạy qua. Xem Q-05. {code}
8. deprecated: không. {code}

### [x] `SQLiteSessionStore.increment_followup_count` (`session_store.py:288-303`)
1. in/out: `(session_id, amount: float = 1.0) -> None`. {code}
2. side effect: UPDATE cộng dồn. {code}
3. state: DB. {code}
4. lỗi: `float(amount)` raise nếu không parse được. {code}
5. config: không. {code}
6. ai gọi: `chat/runtime.py:95-96`, sau khi gác `hasattr`. {code}
7. invariant: cộng dồn **trong SQL** (`accumulated_clinical_score+?`) nên an toàn
   với đồng thời, khác bản in-memory vốn cộng trong Python dưới lock. Không
   `_touch`. {code}
8. deprecated: không. {code}

### [x] `SQLiteSessionStore.delete` (`session_store.py:305-309`)
1. in/out: `(session_id) -> None`. {code}
2. side effect: `_delete` (cascade). {code}
3. state: DB. {code}
4. lỗi: `sqlite3.Error`. {code}
5. config: không. {code}
6. ai gọi: **0 chỗ trong `src/`** — không endpoint nào xoá session. Test có gọi. {code}
7. invariant: không kiểm tồn tại; DELETE của row không có là no-op. {code}
8. deprecated: không đánh dấu, 0 caller production. {code}

### [x] `SQLiteSessionStore.active_count` (`session_store.py:311-316`)
1. in/out: `() -> int`. {code}
2. side effect: không. {code}
3. state: chỉ đọc. {code}
4. lỗi: `sqlite3.Error`. {code}
5. config: `self.ttl`. {code}
6. ai gọi: `api/routes/admin.py:41` (`GET /sessions/stats`). {code}
7. invariant: **method công khai duy nhất không lấy `self._lock`.** Đọc dưới WAL
   nên không sai, nhưng là ngoại lệ không được ghi. Dùng `last_active > cutoff`
   (strict) trong khi `_is_expired` dùng `>` trên hiệu — hai vế tương đương. {code}
8. deprecated: không. {code}

### [x] `SQLiteSessionStore.close` (`session_store.py:318-322`)
1. in/out: `() -> None`. {code}
2. side effect: đóng connection của thread hiện tại. {code}
3. state: `_local.conn = None`. {code}
4. lỗi: không bắt. {code}
5. config: không. {code}
6. ai gọi: **0 chỗ trong `src/`**. Đây là method duy nhất mà bản in-memory không
   có — docstring `memory.py:11-12` gọi đó là "SQLite thừa `close`". {code}
7. invariant: cùng giới hạn như `DBConnection.close` — chỉ đóng được connection
   của thread gọi. {code}
8. deprecated: 0 caller. {code}

---

## §5 — Điều tìm được (câu hỏi)

**Q-01 — `base.py` docstring và `AuditStore` docstring cùng khai sai một điều.**
`base.py:1` nói `DBConnection` "dùng chung cho session store và audit log";
`audit.py:33` nói `AuditStore` "dùng chung DBConnection với session store". Cả
hai sai: `session_store.py:77` tự `sqlite3.connect` vào **file DB khác**
(`sessions.db` vs `audit.db`), và `session_store.py:5` nói thẳng là không phụ
thuộc `db/base.py`. `DBConnection` có đúng một người dùng. {code+doc}

**Q-02 — comment `base.py:8-10` là hoá thạch của kiến trúc đã bị thay hai lần.**
Nó nói "sessions và turns đã chuyển sang JSONL (data/sessions/<id>.jsonl)".
Thực tế bây giờ là SQLite (`session_store.py:35-56`), và `session_store.py:1`
mô tả đúng bước đó ("một file sessions.db thay cho nhiều file JSONL"). Với báo
cáo khoá luận, comment này sẽ dẫn người đọc sai về tầng lưu trữ. {code+comment}

**Q-03 — 3 method 0 caller trong `src/`: `DBConnection.executemany`,
`DBConnection.close`, `SQLiteSessionStore.delete`, `SQLiteSessionStore.close`.**
(Bốn, tính cả hai `close`.) `close` đáng chú ý hơn hai cái kia: cả hai chỉ đóng
được connection của thread gọi, nên với server nhiều thread, mỗi thread giữ một
sqlite connection cho tới khi tiến trình chết. Không ai gọi, và kể cả có gọi
cũng không dọn hết. {code}

**Q-04 — audit log cho "trách nhiệm pháp lý" mất bản ghi im lặng.**
`audit.py:39-67`: `except Exception` → `logger.warning`. `runtime.py:287` gọi
không kiểm kết quả. Nếu `audit.db` đầy đĩa, khoá, hoặc rơi về DB tạm
(`di.py:104-110` có nhánh fallback vào `tempfile.gettempdir()`), hệ vẫn trả lời
người dùng bình thường và không ai biết bản ghi tư vấn y tế đã mất. Cần quyết:
giữ nguyên và ghi rõ giới hạn này trong báo cáo, hay nâng thành lỗi thấy được. {code}

**Q-05 — "TTL xoá lazy" không đồng đều giữa 8 method, và hai store lệch nhau.**
Trong `SQLiteSessionStore`: `get_or_create`, `get_history`, `merge_user_context`,
`get_user_context`, `increment_followup_count` có kiểm hết hạn; `append_turn`
(qua `_ensure`) có; `delete` và `active_count` không cần. Nhưng bản in-memory
`memory.py:141-148` `get_user_context` **không** kiểm hết hạn. Cùng một lời gọi,
hai store trả hai kết quả khác nhau cho session quá TTL. Test chạy bản in-memory
không phát hiện được. {code}

**Q-06 — `schema_version` chỉ được kiểm ở 2 trong 8 đường vào.**
`_stale` (nơi duy nhất so `schema_version`) được gọi từ `_ensure` và
`get_history`. `merge_user_context`, `get_user_context`,
`increment_followup_count` chỉ gọi `_is_expired`. Nên một session lệch phiên bản
schema vẫn đọc/ghi được `user_context` cho tới khi có ai gọi `get_history` hoặc
`append_turn`. Docstring `:9` khai "schema_version lệch → reset session" không
kèm điều kiện đó. {code+doc}

**Q-07 — `RLock` là bắt buộc chứ không phải phòng xa, và không ai ghi lại.**
`get_or_create:175-181` giữ `self._lock` rồi gọi `self.get_history`, hàm này
cũng `with self._lock`. Đổi `RLock` → `Lock` là deadlock ngay request đầu tiên.
Ràng buộc này không có comment nào bảo vệ. (Ngược lại, `RLock` ở
`memory.py:44` thì **không** cần — kiểm tay: không method nào ở đó gọi method
khác cùng lớp trong lúc giữ lock.) {code}

---

## §6 — Tự kiểm (Bước 4)

- Khối khai báo ở Bước 0: **46** (2 + 11 + 10 + 23)
- Khối `### [x]` đếm được: xem `grep -c '^### \[x\]'`
- Mục: 46 × 8 = **368**. Không dùng nén khai báo; mọi khối viết đủ 8 mục.
