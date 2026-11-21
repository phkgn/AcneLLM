# Kế hoạch hợp nhất schema & enum — bản định nghĩa

Mục tiêu: **một nguồn sự thật duy nhất** cho mọi field và enum, trước khi phát
triển thêm bất cứ thứ gì.

Tài liệu này **chỉ định nghĩa**, chưa đụng code. Duyệt xong mới làm.

Phạm vi loại trừ: `chat/routing/rule_extractor.py` và `chat/routing/rule_normalizer.py`
là tầng 3 fallback (chỉ chạy khi `llm_router` **và** `semantic_router` cùng hỏng).
Chúng có bản sao enum riêng nhưng không nằm trong phạm vi đợt này.

---

## 1. Kiểm kê — ai đang định nghĩa cái gì

| Nơi | Vai trò | Trên đường chạy? |
|---|---|---|
| `src/acne_llm/schemas/core.py` | `AcneClinicalInput`, `UserContext`, `UserInput` | **Có — runtime** |
| `src/acne_llm/schemas/clinical.py` | `NormalizedAcneCase`, `ClinicalDemographics` | Không — chỉ `research/LLMData/*` |
| `src/acne_llm/chat/_intake_parse.py` | 6 `frozenset` validate JSON của intaker | **Có — runtime** |
| `model/intaker/Modelfile` | text tiếng Việt dạy model trả enum nào | **Có — runtime** |
| `research/datagen/intakedata/schema.py` | 6 `frozenset` + JSON Schema sinh dữ liệu train | Không — offline |
| `research/evaluation/severity.py` | `LEVELS` + `MODELFILE_ANCHOR` cho `inflammation_level` | Không — offline |

Tổng: **6 nơi** định nghĩa enum, trong đó 3 nằm trên đường chạy thật.

---

## 2. Diff giữa các schema

### 2.1. Hai schema lâm sàng song song

`NormalizedAcneCase` (clinical.py) và `AcneClinicalInput` (core.py) mô tả **cùng
một khái niệm** nhưng khác nhau ở bốn chỗ:

| Field | `NormalizedAcneCase` | `AcneClinicalInput` |
|---|---|---|
| vị trí tổn thương | `distribution` | **`lesion_distribution`** |
| cờ nguy hiểm | `red_flags` | **`red_flags_input`** |
| nhân khẩu | lồng `demographics: ClinicalDemographics` | phẳng, nằm ở `UserContext` |
| `allergies`, `missing_info` | có | không |

Giá trị enum của `lesion_types`, `distribution`/`lesion_distribution`,
`inflammation_level` thì **giống hệt nhau**. Chỉ tên field lệch.

**Runtime dùng `AcneClinicalInput`.** `NormalizedAcneCase` chỉ còn được
`research/LLMData/{chunk_qa,clinical_case,injection_qa}` và một test dùng.

### 2.2. Nhân khẩu bị khai hai lần, lệch một giá trị

| Field | `ClinicalDemographics` (clinical.py) | `UserContext` (core.py) |
|---|---|---|
| `sex` | `male,female,other,`**`unknown`** — 4 giá trị | `male,female,other` — 3, Optional |
| `skin_type` | 6 giá trị, mặc định `"unknown"` | 6 giá trị, Optional |
| `age`, `is_pregnant`, `is_breastfeeding` | có | có |
| `allergies`, `current_products`, `medications`, `duration_weeks` | không | có |

**Đây là chỗ lệch enum duy nhất tìm được.** Chi tiết ở §3.

### 2.3. Ba định nghĩa mức độ nặng

| Tên | Nơi | Giá trị | Dùng ở đâu |
|---|---|---|---|
| `InflammationLevel` | clinical.py:15 | `none,mild,moderate,severe,unknown` | `NormalizedAcneCase` |
| `AcneClinicalInput.inflammation_level` | core.py:61 | **cùng 5 giá trị, khai inline** | runtime |
| `Severity` | clinical.py:14 | `mild,moderate,severe,unknown` — **thiếu `none`** | **0 caller — chết** |

`Severity` là type alias chết, và nguy hiểm ở chỗ nó **trông giống**
`InflammationLevel` nhưng thiếu một bậc. Ai import nhầm sẽ mất bậc `none` mà
không có lỗi nào.

### 2.4. Loại tổn thương bị khai hai thang

| Nơi | Số giá trị |
|---|---|
| `lesion_types` (core.py, clinical.py, `_intake_parse`, Modelfile, datagen) | **11** |
| `VisionLesion.type` (core.py:11) | **7** — thiếu `whitehead`, `blackhead`, `closed_comedone`, `post_inflammatory_hyperpigmentation` |

`VisionOutput` / `VisionLesion` hiện **không còn caller nào** trong `src/`
(module `vision/` đã bị xoá ở đợt dọn dead code, nhưng schema thì còn).

---

## 3. Bảng đối chiếu enum — kết quả đo

So ba nơi trên đường chạy: `Modelfile` ↔ `core.py` ↔ `_intake_parse.py`.

| Enum | Số giá trị | Kết quả |
|---|---|---|
| `lesion_types` | 11 | ✅ khớp |
| `lesion_distribution` | 12 | ✅ khớp |
| `inflammation_level` | 5 | ✅ khớp |
| `skin_type` | 6 | ✅ khớp |
| `intent` | 4 | ✅ khớp |
| **`sex`** | 3 vs 4 | ❌ **lệch** |

Chi tiết `sex`:

```
Modelfile        (3): female, male, other
_intake_parse    (3): female, male, other
UserContext      (3): female, male, other      ← runtime
ClinicalDemographics (4): + unknown            ← không trên đường chạy
```

**Mức nghiêm trọng: thấp.** Chỗ lệch nằm ở `ClinicalDemographics` — schema
không trên đường chạy — và lệch theo chiều *rộng hơn*. Model không bao giờ sinh
ra `unknown` nên validator không phải chặn. Nếu lệch chiều ngược lại thì đã là
lỗi mất nhãn im lặng.

**Nhưng bốn enum khớp không nhờ cơ chế nào.** Chỉ `inflammation_level` có test
canh (`test_severity_anchor.py`). Năm enum còn lại khớp vì chưa ai sửa, không
phải vì có gì bảo đảm.

---

## 4. Skeleton — thiết kế đề xuất

### 4.1. Một file, một nguồn

Tạo `src/acne_llm/schemas/enums.py`. Đặt trong `src/` vì runtime cần nó — hiện
`severity.py` nằm ở `research/` trong khi `_intake_parse.py` ở `src/` phải tự
chép lại, mà Docker chỉ copy `src/`.

Mỗi enum khai theo một dạng thống nhất: **giá trị → định nghĩa → ví dụ lời
người dùng**, đúng kiểu `severity.py::LEVELS` đang làm.

```
ENUMS: dict[str, dict[str, str]] = {
    "intent":              {...},
    "sex":                 {...},
    "skin_type":           {...},
    "lesion_types":        {...},
    "inflammation_level":  {...},   # chuyển nguyên từ severity.py
    "lesion_distribution": {...},
}
```

### 4.2. Ba thứ sinh ra từ nó

| Sinh ra | Thay cho | Dùng ở |
|---|---|---|
| `Literal[...]` | khai tay trong `core.py` | pydantic |
| `frozenset` | 6 frozenset trong `_intake_parse.py` | validate JSON intaker |
| khối text tiếng Việt | đoạn enum gõ tay trong Modelfile | system prompt |

Cơ chế đã có sẵn nguyên mẫu: `severity.py::MODELFILE_ANCHOR` sinh text từ
`LEVELS`. Nhân rộng cách đó cho cả sáu.

### 4.3. Một test canh cả sáu

Mở rộng `tests/test_severity_anchor.py` (hoặc thêm `test_enum_anchor.py`) để
chặn trôi cho **cả sáu enum**, không chỉ `inflammation_level`.

Kiểm hai chiều: `enums.py` ↔ `Modelfile`, và `enums.py` ↔ `datagen/intakedata/schema.py`.

---

## 5. Việc dọn kèm theo

| Việc | Lý do |
|---|---|
| Xoá `Severity` (clinical.py:14) | 0 caller, và thiếu bậc `none` so với `InflammationLevel` |
| Xoá `VisionOutput`, `VisionLesion` | module `vision/` đã xoá, schema mồ côi, và `VisionLesion.type` là thang 7 giá trị đối chọi thang 11 |
| Thống nhất `distribution` → `lesion_distribution` | runtime đã dùng tên sau |
| Thống nhất `red_flags` → `red_flags_input` | như trên |
| Quyết số phận `NormalizedAcneCase` | chỉ `research/LLMData/*` dùng — hoặc chuyển nó sang dùng `AcneClinicalInput`, hoặc giữ và ghi rõ là schema riêng của LLMData |

---

## 6. Thứ tự thực hiện

1. **Duyệt bản định nghĩa này** — chốt giá trị và định nghĩa cho từng enum, đặc
   biệt `intent` (đang là chỗ hỏng thật: định tuyến `reject` chỉ đúng 40%).
2. Dựng `enums.py` với đủ 6 enum, định nghĩa + ví dụ.
3. Sinh `Literal` / `frozenset` / text, thay 3 nơi trên đường chạy.
4. Thêm test canh trôi cho cả 6.
5. Đồng bộ `datagen/intakedata/schema.py` để dữ liệu train dùng chung nguồn.
6. Dọn theo §5.
7. **Chỉ sau khi xong** mới viết lại định nghĩa `reject` — lúc đó nó có neo.

---

## 7. Điểm cần bạn quyết trước khi code

1. **`sex` chốt 3 hay 4 giá trị?** Runtime đang 3. Thêm `unknown` cho cân xứng
   với `skin_type` (đã có `unknown`), hay bỏ `unknown` khỏi `ClinicalDemographics`?
2. **`NormalizedAcneCase` giữ hay gộp?** Nó chỉ phục vụ `research/LLMData/*`.
3. **`intent` — định nghĩa từng giá trị thế nào?** Đây là phần quan trọng nhất,
   vì `reject` hiện chỉ có một dòng không ví dụ, và đó là nguyên nhân trực tiếp
   của 9/15 ca định tuyến sai.
