# Kế hoạch dọn cấu trúc thư mục (top-level)

Trạng thái: **Đợt 0, 1, 2 ĐÃ THỰC HIỆN (2026-08-14). Đợt 3 làm một phần.**

- Đợt 0-1: xong — `research/{dashboards,dataset_viz,notebooks}`, docs đã tách archive/reports.
- Đợt 2: xong — `datagen/`, `evaluation/`, `ablation/`, `LLMData/`, `guideline_docs/`
  đã vào `research/`; `pythonpath = ["src", "research"]`; 52 tham chiếu đường dẫn
  và 24 `parents[N]` đã sửa. Kiểm chứng: `research/evaluation/tests` cho kết quả
  y hệt tree gốc (8 failed / 115 passed / 3 skipped — 8 lỗi đó có từ trước).
- Đợt 3: README đã có cây thư mục + bảng entrypoint. `docs/archive/README.md` chưa viết.

Root: 20 thư mục → **10**. Giữ tài liệu này làm bản ghi quyết định.

---

## 1. Nguyên tắc chia

Có một ranh giới sẵn có trong repo mà không cần tôi phát minh ra: **Dockerfile
copy cái gì thì cái đó là runtime.** Đọc `Dockerfile` thấy nó chỉ cần
`requirements.txt`, `pyproject.toml`, `README.md`, `src/`; compose mount thêm
`data/`, `config/`, `model/`, `docker/`, `frontend/`. Tổng cộng 8 mục.

Root hiện có **20 thư mục + 7 file lẻ**. Nghĩa là 12 thư mục đang đứng ngang
hàng với runtime nhưng không tham gia phục vụ một request nào. Đó là toàn bộ
vấn đề, và cũng là toàn bộ cách giải: đẩy 12 thứ đó xuống một tầng, đặt tên cho
tầng đó, xong.

Không đổi tên package, không sửa import. Lý do ở mục 3.

---

## 2. Cây trước → sau

**Trước** (root, 20 dir):

```
ablation/  config/  data/  datagen/  docker/  docs/  evaluation/  frontend/
guideline_docs/  LLMData/  logs/  model/  notebooks/  scripts/  src/  tests/
visualization/  visualize/  .agents/  .codex/
+ AcneLLM_config_audit.xlsx  context.md  report.md  runtime_audit.md
  smoke_review.md  tasks.sh  README.md
```

**Sau** (root, 11 dir):

```
AcneLLM/
├── src/acne_llm/        ← RUNTIME. Docker copy đúng cái này.
├── config/              ← runtime (prompts, guardrails.yaml, drugs_acne.yaml)
├── frontend/            ← runtime
├── docker/              ← runtime (nginx, ollama-init)
├── tests/               ← test của runtime
├── scripts/             ← vận hành: build_kb, crawl, convert dataset
├── data/                ← artifact sinh ra (chroma, bm25, sqlite, cache)
├── model/               ← artifact Modelfile + GGUF
├── research/            ← MỚI: mọi thứ offline, không phục vụ request
│   ├── datagen/
│   ├── evaluation/
│   ├── ablation/
│   ├── LLMData/
│   ├── guideline_docs/
│   ├── notebooks/
│   ├── dashboards/      (từ visualization/)
│   └── dataset_viz/     (từ visualize/)
├── docs/
│   ├── archive/         ← MỚI: ~25 file CODEX_TASK_*, *_PLAN cũ
│   └── reports/         ← MỚI: context.md, report.md, smoke_review.md,
│                           runtime_audit.md, AcneLLM_config_audit.xlsx
└── Dockerfile  docker-compose*.yml  pyproject.toml  requirements.txt
    README.md  tasks.sh  .env*
```

Người mới clone về nhìn root sẽ thấy: chỗ code chạy, chỗ test, chỗ script, chỗ
nghiên cứu, chỗ tài liệu. Năm nhóm, không phải hai mươi mục ngang hàng.

Hai cái tên `visualization/` và `visualize/` đứng cạnh nhau ở root hiện tại là
thứ khó chịu nhất khi đọc — chúng khác nhau thật (`visualization/` là dashboard
HTML cho báo cáo, `visualize/` là biểu đồ phân bố dataset) nhưng tên không nói
lên điều đó. Đổi thành `dashboards/` và `dataset_viz/` khi di chuyển, không tốn
thêm công vì đằng nào cũng đang `git mv`.

---

## 3. Vì sao KHÔNG đổi tên import

Tôi đã dò đồ thị import. Năm thư mục sắp chuyển là **package Python thật, được
import bằng tên tuyệt đối**, và chúng phụ thuộc chéo nhau:

- `evaluation/datasets/make_intake_set.py` → `from datagen.intakedata...` (5 dòng)
- `evaluation/datasets/make_intake_set_v2.py` → `from datagen.intakedata...` (5 dòng)
- `datagen/gates.py` → `from evaluation.metrics.grounding import ...`
  (**vòng tròn**: datagen ↔ evaluation)
- `evaluation/tests/*` → cả `evaluation.*` lẫn `datagen.*`
- `LLMData/injection_qa/*` → `from LLMData.chunk_qa...`
- `tests/test_approve_eval_labels.py` → `from scripts.approve_eval_labels import ...`
- `ablation/*` dùng relative import (`from .cases import ...`) → chạy bằng
  `python -m ablation.run`, cần thư mục cha nằm trên `sys.path`

Đổi `from datagen.x` thành `from research.datagen.x` là sửa vài chục dòng ở
những file mà bạn không định đụng tới, chỉ để đạt một mục tiêu thẩm mỹ. Cách
lười hơn và cũng ít rủi ro hơn: **giữ nguyên mọi câu import, chỉ nói cho Python
biết thêm một chỗ để tìm package.**

Cụ thể là thêm `research` vào `sys.path` ở đúng 3 nơi:

```toml
# pyproject.toml
[tool.pytest.ini_options]
pythonpath = ["src", "research"]        # đang là ["src"]
```

```bash
# tasks.sh — thêm gần đầu file
export PYTHONPATH="${PYTHONPATH}:$(pwd)/research"
```

```powershell
# research/evaluation/e2e.ps1, research/ablation/run_all.ps1
$env:PYTHONPATH = "$PWD\research;$env:PYTHONPATH"
```

Sau đó `python -m evaluation.full_evaluation`, `python -m ablation.run`,
`pytest` đều chạy y như cũ. Đây là 3 dòng config thay cho ~40 dòng sửa import.

Đánh đổi phải nói rõ: đường dẫn file không còn khớp với tên module (file nằm ở
`research/datagen/` nhưng import là `datagen`). Hơi lệch, nhưng lệch một cách
nhất quán và có ghi chú, còn hơn một đợt sửa import to đùng lẫn vào cùng commit
với việc di chuyển — lúc đó `git log --follow` mất dấu và review không nổi.

`scripts/` giữ nguyên ở root: nó ngắn, quy ước phổ biến, `tests/` đang import
nó, và `tasks.sh` gọi nó. Di chuyển chỉ để cho đẹp thì không đáng.

---

## 4. Ba đợt, xếp theo rủi ro tăng dần

### Đợt 0 — dọn rác trước khi di chuyển (5 phút, rủi ro 0)

`__pycache__` đang nằm rải rác trong `ablation/`, `datagen/`, `evaluation/`,
`guideline_docs/`, `scripts/`, `tests/`, `visualization/`. Đừng `git mv` chúng.

```bash
find . -path ./.venv -prune -o -name __pycache__ -prune -exec rm -rf {} +
find . -path ./.venv -prune -o -name '.pytest_cache' -prune -exec rm -rf {} +
grep -n '__pycache__\|.ruff_cache\|.pytest_cache' .gitignore   # xác nhận đã ignore
git status --short                                             # phải sạch
```

### Đợt 1 — thứ không ai import (rủi ro rất thấp)

Chỉ là file dữ liệu, ảnh, notebook, tài liệu. Không có module Python nào bên
ngoài trỏ vào.

```bash
mkdir -p research docs/archive docs/reports

git mv notebooks      research/notebooks
git mv visualization  research/dashboards
git mv visualize      research/dataset_viz

git mv context.md report.md smoke_review.md runtime_audit.md docs/reports/
git mv AcneLLM_config_audit.xlsx docs/reports/

# 25 file prompt/plan đã xong việc — vào archive, không xoá
git mv docs/CODEX_TASK_*.md docs/*_PLAN.md docs/*_PROMPT.md docs/archive/
```

**Cần kiểm tra tay trước khi chạy dòng cuối:** `docs/` có ~30 file, một số vẫn
còn giá trị tham chiếu (`CONFIG_MAP.md`, `config_reference.md`,
`DOCKER_QUICKSTART.md`, `config_layout.md`). Chỉ archive những file mang tên
`CODEX_TASK_*`, `*_PROMPT`, `*_PLAN` đã hoàn thành. Liệt kê ra rồi duyệt từng
cái, đừng dùng wildcard mù.

**Cần sửa sau đợt này:**
- `tasks.sh:191` — khối "Generating dataset visualizations" (đọc xem nó gọi
  `visualize/` hay `scripts/visualize/`, sửa đường dẫn tương ứng)
- `research/dashboards/generate_all.py` và
  `research/dashboards/architecture/build_drawio.py` — hai file này tự tính
  đường dẫn tương đối tới root, kiểm tra lại
- `README.md` — mọi link tới `report.md`, `context.md`
- `.gitignore` — nếu có dòng nào trỏ `visualize/` hoặc `visualization/`

**Kiểm chứng:** `pytest -q` (phải giữ nguyên số test pass), `git status` sạch.

### Đợt 2 — package Python (rủi ro trung bình)

```bash
git mv datagen         research/datagen
git mv evaluation      research/evaluation
git mv ablation        research/ablation
git mv LLMData         research/LLMData
git mv guideline_docs  research/guideline_docs
```

Rồi sửa 3 chỗ `PYTHONPATH` ở mục 3, cộng thêm:

| File | Dòng | Sửa gì |
|---|---|---|
| `pyproject.toml` | 18 | `pythonpath = ["src", "research"]` |
| `tasks.sh` | đầu file | thêm `export PYTHONPATH=...:$(pwd)/research` |
| `tasks.sh` | 286, 296 | `root / "LLMData"` → `root / "research" / "LLMData"` |
| `tasks.sh` | 339 | `ruff check src/ scripts/ config/` — cân nhắc thêm `research/` |
| `research/evaluation/e2e.ps1` | — | set `$env:PYTHONPATH` |
| `research/ablation/run_all.ps1` | — | set `$env:PYTHONPATH` |
| `research/datagen/RUN.bat` | — | như trên |
| `research/guideline_docs/TAI-PDF.bat` | — | như trên |
| `research/evaluation/common.py` | — | có hằng `ROOT` tính từ `__file__`, **phải kiểm tra**: nó lùi mấy cấp để ra repo root? Thêm một cấp thư mục là nó trỏ sai |
| `scripts/build_intent_dataset.py`, `scripts/build_kb.py` | — | có tham chiếu tới các thư mục vừa chuyển |
| `.gitignore` | — | các dòng `evaluation/reports/`, `datagen/output/`, `ablation/runs/` nếu có |

Dòng `research/evaluation/common.py` là chỗ dễ vỡ nhất trong cả kế hoạch. Bất kỳ
file nào tính `ROOT = Path(__file__).parents[N]` đều sai đi một cấp sau khi
chuyển. Tìm hết trước khi chạy:

```bash
grep -rn "parents\[" research/ scripts/ --include=*.py
```

**Kiểm chứng, chạy đủ cả 5:**

```bash
pytest -q                                    # tests/ + research/evaluation/tests/
python -c "import acne_llm; print('runtime ok')"
python -m evaluation.full_evaluation --help  # import graph evaluation ↔ datagen
python -m ablation.run --dry-run             # relative import + không cần model
docker build -t acnellm:check .              # runtime không được ảnh hưởng
```

Nếu `docker build` đổi kết quả thì có gì đó sai về nguyên tắc — Dockerfile không
chạm vào thư mục nào vừa chuyển cả.

### Đợt 3 — cập nhật tài liệu (rủi ro 0, nhưng đừng bỏ)

- `README.md`: thêm cây thư mục 11 dòng ở mục 2 vào phần đầu, kèm một câu cho
  mỗi nhóm. Đây là thứ mang lại phần lớn giá trị "nhìn vào là hiểu" — cấu trúc
  đẹp mà không ai giải thích thì người sau vẫn phải đoán.
- `docs/archive/README.md`: một dòng — "file trong này đã hoàn thành nhiệm vụ,
  giữ để truy vết, không phải tài liệu đang có hiệu lực".
- `research/README.md`: một dòng — "không có gì trong này phục vụ request
  runtime; cần `PYTHONPATH=research` để chạy".

---

## 5. Thứ tự commit và cách lùi

Bốn commit riêng, mỗi commit chỉ làm một việc:

1. `chore: remove __pycache__, verify gitignore`
2. `chore: move docs/notebooks/viz into docs/ and research/`
3. `chore: move offline packages into research/, add research to PYTHONPATH`
4. `docs: describe new layout in README`

Không trộn sửa code vào commit di chuyển. `git mv` thuần thì `git log --follow`
còn theo được lịch sử file; trộn thêm sửa nội dung thì mất dấu.

Lùi: `git revert` từng commit theo thứ tự ngược. Vì không có commit nào sửa
`src/`, việc lùi không đụng tới runtime.

---

## 6. Những gì KHÔNG làm trong đợt này

- **Không đụng `src/acne_llm/`.** Kể cả `crawler/` (chỉ dùng offline nhưng đang
  nằm trong package runtime) và 12 file `chat/_*.py`. Đó là đợt khác, và nó
  cần chạy sau khi xoá dead code chứ không phải trước — dọn xong rồi mới biết
  còn lại thật sự là gì.
- **Không xoá dead code chung đợt này.** Bạn đã chọn tách ra, và đó là lựa chọn
  đúng: diff di chuyển thuần đọc được bằng mắt, diff trộn xoá thì không.
- **Không đổi tên module.** Xem mục 3.
- **Không đụng `data/`, `model/`, `logs/`.** Chúng là artifact, có thể rất nặng,
  và `docker-compose` mount trực tiếp.

---

## 7. Ước lượng

| Đợt | Việc | Thời gian | Rủi ro |
|---|---|---|---|
| 0 | dọn `__pycache__` | 5 phút | 0 |
| 1 | move docs + viz + notebooks | 20 phút | rất thấp |
| 2 | move 5 package + sửa PYTHONPATH + `parents[N]` | 1-2 giờ | trung bình |
| 3 | viết lại README | 30 phút | 0 |

Phần lớn thời gian của đợt 2 nằm ở việc dò `Path(__file__).parents[N]`, không
phải ở lệnh `git mv`. Làm đợt 0 và 1 trước, merge, rồi mới làm đợt 2 vào một
buổi riêng khi có thể chạy đủ 5 lệnh kiểm chứng.
