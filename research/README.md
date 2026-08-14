# research/

Không có gì trong thư mục này phục vụ một request runtime. Dockerfile không
copy nó; `docker-compose` không mount nó.

| Thư mục | Là gì |
|---|---|
| `dashboards/` | Dashboard HTML + sơ đồ kiến trúc (trước đây là `visualization/`) |
| `dataset_viz/` | Biểu đồ phân bố dataset (trước đây là `visualize/`) |
| `notebooks/` | Notebook thăm dò |

Hai cái tên `visualization/` và `visualize/` cũ đứng cạnh nhau ở root và không
nói lên chúng khác nhau ở chỗ nào. Đổi tên khi chuyển, xem `docs/CLEANUP_PLAN.md`.

Các package offline còn lại (`datagen/`, `evaluation/`, `ablation/`, `LLMData/`,
`guideline_docs/`) **chưa** chuyển vào đây — chúng import chéo nhau bằng tên
tuyệt đối nên cần thêm `research` vào `PYTHONPATH` trước. Xem Đợt 2 trong
`docs/CLEANUP_PLAN.md`.
