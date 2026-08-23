# FINDINGS / src.guardrails

Module: `src/acne_llm/guardrails/` — 3 file, 255 LOC (`__init__.py` 0, `pii.py` 46, `runner.py` 209).
7 symbol + 3 khối lời khai + 1 khối file rỗng = 11 khối × 8 mục = 88.

---

## `__init__.py`

### [x] (file rỗng)
1. in/out: 0 LOC, không định nghĩa gì. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config/env: không. {code}
6. ai gọi: chỉ đánh dấu thư mục là package; `di.py:15` import `from .guardrails.runner import GuardrailRunner` chứ không qua `__init__`. {code}
7. invariant: khác `schemas/__init__.py` vốn re-export — module này **không có mặt tiền công khai**, caller phải biết đường dẫn con. {code}
8. deprecated/TODO: không. {code}

---

## `pii.py`

### [x] `_PII_PATTERNS`
1. in/out: `list[tuple[re.Pattern, str]]` — cặp (regex, chuỗi thay thế). {code} `[pii.py:14]`
2. side effect: biên dịch regex lúc import module. {code}
3. state: đọc bởi `mask_pii` và `contains_pii`; không ghi. {code}
4. lỗi: regex sai cú pháp sẽ ném lúc **import**, không phải lúc chạy. {code}
5. config/env: hằng cứng trong code, **không đọc file cấu hình** — khác `runner.py` vốn đọc `guardrails.yaml`. {code}
6. ai gọi: `mask_pii` `[:33]`, `contains_pii` `[:41]`. 0 caller ngoài file. {code}
7. invariant: mẫu đầu `\b\d{9}\b|\b\d{12}\b` `[:14]` bắt số 9 hoặc 12 chữ số — **trùng dạng với số điện thoại và mã đơn hàng**, nên nhận nhầm là hướng sai mặc định. Chấp nhận được vì chỉ dùng để log. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `mask_pii`
1. in/out: `(text: str) -> str` — trả bản đã thay PII bằng nhãn `[ID_MASKED]` v.v. {code} `[pii.py:32-37]`
2. side effect: không. {code}
3. state: đọc `_PII_PATTERNS`; không ghi. {code}
4. lỗi: không có nhánh lỗi. {code}
5. config/env: không. {code}
6. ai gọi: `src/acne_llm/chat/runtime.py:23` (import), `tests/test_guardrails.py:4`. Thực gọi tại `guardrails/runner.py:68` trong `pre_check`. {code}
7. invariant: docstring `[:33]` khai rõ "Dùng khi ghi log, KHÔNG dùng để từ chối" — ranh giới trách nhiệm được ghi thành lời, và code tuân thủ: không có caller nào dùng kết quả để chặn. {doc}
8. deprecated/TODO: không dấu. {code}

### [x] `contains_pii`
1. in/out: `(text: str) -> bool`. {code} `[pii.py:39-45]`
2. side effect: không. {code}
3. state: đọc `_PII_PATTERNS`. {code}
4. lỗi: không. {code}
5. config/env: không. {code}
6. ai gọi: `src/acne_llm/chat/intake.py:32` (import), `guardrails/runner.py:66`, `tests/test_guardrails.py:4`. {code}
7. invariant: docstring `[:40]` khai "để log cảnh báo" — khớp `runner.py:67-71` chỉ `logger.warning`, không raise. {doc}
8. deprecated/TODO: không dấu. {code}

### [x] docstring `pii.py:1`
1. in/out: lời khai `"""Phat hien va che PII trong text nguoi dung."""`. {doc}
2-6. side effect / state / lỗi / config / caller: không. {doc}
7. invariant: khai đúng phạm vi — **kiểm ngược**: cả hai hàm chỉ đọc, không có đường ghi hay từ chối. Khớp code. {code}
8. deprecated: không. {doc}

---

## `runner.py`

### [x] `GuardrailRunner`
1. in/out: class, khởi tạo từ `config_path: str`; phơi `self.cfg: dict`, `self.rules: list[dict]`, và thuộc tính động `trigger_count` do `runtime.py:96` gán. {code} `[runner.py:30]`
2. side effect: đọc file YAML lúc khởi tạo. {code}
3. state: giữ `cfg`/`rules` trong instance; `trigger_count` bị tăng từ bên ngoài `[src/acne_llm/chat/runtime.py:96-98]` — **thuộc tính không khai báo trong class**. {code}
4. lỗi: file không tồn tại → log warning, chạy với `{"rules": []}` `[:43-45]`, không ném. {code}
5. config/env: `settings.guardrails_yaml`, mặc định `'./config/guardrails.yaml'` `[config.py:165]`, truyền vào tại `di.py:225`. {code}
6. ai gọi: `di.py:15`, `api/routes/metrics.py:13` (đọc `trigger_count`), `tests/test_guardrails.py:3`. {code}
7. invariant: docstring `[:31-36]` khai "co y KHONG doc van ban tu do — moi dau vao cua no la truong co cau truc tren UserInput". **Kiểm ngược**: `pre_check` đọc `user.description` `[:66]` — nhưng chỉ để đo độ dài và dò PII, không phán quyết. `medication_safety_refusal` chỉ đọc `context.medications`, `clinical.medication_history`, `context.is_pregnant`, `age`, `sex` — đúng là trường có cấu trúc. Lời khai khớp code. {code}
8. deprecated: `self.rules` `[:46]` được nạp từ YAML nhưng **không hàm nào trong file đọc nó** — grep `self.rules` chỉ ra một dòng gán. Trường chết. {code}

### [x] `GuardrailRunner.__init__`
1. in/out: `(config_path: str) -> None`. {code} `[runner.py:38-46]`
2. side effect: `Path.exists()` và `open()` đọc đĩa `[:39-42]`; `yaml.safe_load`; log warning khi thiếu file. {code}
3. state: ghi `self.cfg`, `self.rules`. {code}
4. lỗi: thiếu file → nhánh mềm `[:43-45]`. YAML hỏng cú pháp → `yaml.safe_load` **ném ra ngoài**, không bắt. Hai chế độ lỗi khác nhau cho cùng một file. {code}
5. config/env: như trên, `settings.guardrails_yaml`. {code}
6. ai gọi: `di.py:225`. Nó gọi `yaml.safe_load`, `open`, `logger.warning`. {code}
7. invariant: `or {}` `[:42]` biến file YAML rỗng thành dict rỗng thay vì `None`. {code}
8. deprecated: comment `[:47-54]` khai `DrugChecker` 358 dòng và tra cứu `drugs_acne.yaml` đã xoá ở Phase 5, và rằng `config/drugs_acne.yaml` **vẫn giữ** vì `datagen/gates.py:520` đọc nó. **Kiểm ngược**: `datagen/gates.py` là file có import gãy `evaluation.metrics.grounding` `[gates.py:36]`, nên consumer duy nhất của `drugs_acne.yaml` hiện **không import được**. Lời khai đúng lúc viết, đã quá hạn. {code}

### [x] `GuardrailRunner.pre_check`
1. in/out: `(user: UserInput) -> None` — không trả gì, chỉ raise hoặc log. {code} `[runner.py:56-72]`
2. side effect: log warning khi thấy PII `[:69-72]`. {code}
3. state: đọc `user.description`; không ghi. {code}
4. lỗi: `description` sau `.strip()` rỗng → `raise ValueError("description quá ngắn")` `[:65-66]`. **Không bắt tại đây**; caller `chat/intake.py:236` chịu trách nhiệm. {code}
5. config/env: không. {code}
6. ai gọi: `chat/intake.py:236`, `tests/test_api.py:37`, `tests/test_chat_stream.py:118`, tổng 8 chỗ. {code}
7. invariant: PII **chỉ log, không chặn** — comment `[:67-68]` giải thích vì sao (người dùng có thể nhập tuổi, giới tính hợp lệ). {comment}
8. deprecated: docstring `[:59-63]` ghi "check prompt injection da bo" kèm lý do: blocklist 146 chuỗi khớp thô vừa chặn nhầm tiếng Việt sinh hoạt vừa bị né bằng một dấu cách. **Kiểm ngược**: `_INJECTION_MARKERS` vẫn tồn tại nhưng ở `llm/prompt_builder.py:15`, làm sanitize chứ không từ chối — khớp lời khai "prompt_builder van sanitize". {code}

### [x] `GuardrailRunner.medication_safety_refusal`
1. in/out: `(user: UserInput, mentioned_terms: list[str] | None = None) -> AdviseOutput | None`. `None` = không chặn. {code} `[runner.py:75-188]`
2. side effect: không — thuần hàm, không I/O, không log. {code}
3. state: đọc `user.context.medications`, `user.clinical.medication_history`, `user.context.is_pregnant`, `user.context.is_breastfeeding`, `user.context.age`, `user.context.sex`, `user.mode`. Không ghi. {code}
4. lỗi: không có nhánh ném. Không khớp luật nào → `return None` `[:143]`. {code}
5. config/env: **không đọc `settings`** — tập `drug_terms` 13 tên `[:87-91]` và bốn luật đều là hằng cứng trong code. {code}
6. ai gọi: `chat/intake.py:348`, `chat/_safety.py:11`, `chat/session/fold.py:3`, tổng 7 chỗ. Nó gọi `AdviseOutput`, `RedFlag`. {code}
7. invariant: **thai kỳ đọc DUY NHẤT từ `user.context.is_pregnant`**, không từ `mentioned_terms` — comment `[:106-118]` ghi lại phép đo end-to-end: bản cũ chặn 5/5 câu trong đó 4 sai, gồm "em không mang thai, dùng tretinoin được không". Đây là invariant quan trọng nhất của module và có bằng chứng kèm theo. {comment}
8. deprecated: comment `[:125-133]` cảnh báo cặp `isotretinoin + tetracycline` **từng** do `DrugChecker.interactions_triggered` phát hiện; bỏ `DrugChecker` mà quên điều kiện `interaction_block` `[:134]` thì cổng im lặng. Ghi rõ `test_intake` bắt được. Là ghi chú phòng hồi quy, không phải code chết. {comment}

### [x] khối `ponytail:` cuối `runner.py` `[:190-209]`
1. in/out: lời khai 20 dòng. {comment}
2-6. side effect / state / lỗi / config / caller: không. {comment}
7. invariant: khai `post_check` và 9 hàm `_apply_*` (251 dòng) đã xoá ở Phase 3, và đối chiếu 7 luật bên trong: retinoid+thai kỳ / tuổi <12 / tự nặn / disclaimer đã có ở `chat/_safety.get_safety_suffix`; luật liều đã port sang `chat/_safety`, có `tests/test_safety_dose_rule.py`; ba luật còn lại **cố ý bỏ**. **Kiểm ngược**: `chat/_safety.py` có `_DOSE_RE` `[_safety.py:24]`, `_SELF_PROCEDURE_TERMS` `[_safety.py:170]`, `_GENERIC_DISCLAIMER_VI` `[_safety.py:117]`, nhánh retinoid+thai kỳ `[_safety.py:253]`, nhánh tuổi <12 `[_safety.py:302]`. Lời khai khớp code ở cả năm điểm. {code}
8. deprecated: đây là bản ghi quyết định đúng chuẩn — nêu cái đã xoá, nơi đã chuyển tới, và cái cố ý bỏ kèm lý do. {comment}

### [x] docstring `runner.py:1`
1. in/out: lời khai `"""Cong tat dinh duy nhat con lai: chong chi dinh / tuong tac thuoc."""`. {doc}
2-6. side effect / state / lỗi / config / caller: không. {doc}
7. invariant: khai đây là **cổng tất định duy nhất còn lại**. **Kiểm ngược — LỆCH**: `src/acne_llm/chat/_safety.py` là 372 dòng khớp chuỗi tất định chạy sau generator, và `docs/rulebase_audit.md:161` xếp nó vào "Tier 5 — Post-processing" với phán quyết "Giữ". Có hai cổng tất định, không phải một; cái này chạy trước generator, cái kia chạy sau. {code}
8. deprecated: docstring hẹp hơn thực tế. {doc}

---

## BƯỚC 4 — TỰ KIỂM

```
file trong module / file đã tick   :  3 / 3
symbol đã liệt kê / đã tick        :  7 / 7   (+3 lời khai +1 file rỗng)
mục 1-8 cần điền / đã điền         : 88 / 88
```
"Chưa rõ" còn lại: **0**.
