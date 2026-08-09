# AcneLLM build-process visualization

Mở `index.html` trực tiếp trong trình duyệt. Trang là self-contained và không
gọi API; `source_snapshot.json` lưu lại các fact/metric đã dùng để dựng trang.

Snapshot được đối chiếu với source và artifact hiện có ngày 2026-08-09. Những
điểm quan trọng không được hiểu thành release approval:

- `docker/ollama-init.sh` đang trỏ tới hai model directory cũ.
- `data/kb_manifest.json` hiện không tồn tại.
- Generator roledata còn thiếu 35/3.500 records.
- Summary mới nhất của `full_evaluation` skip intake/retrieval và chỉ hoàn tất
  ablation; các metric intake/retrieval là artifact riêng có sẵn.
