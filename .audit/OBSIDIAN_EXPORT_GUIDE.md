---
title: AcneLLM Obsidian Export Guide
tags:
  - acnellm
  - obsidian
  - export
status: ready
as_of: 2026-08-25
---

# Obsidian export guide

## Mục tiêu

Đưa knowledge vào Obsidian mà vẫn giữ:

- đường dẫn evidence;
- nhãn thời gian và trạng thái;
- liên kết current truth ↔ historical snapshot ↔ roadmap;
- khả năng truy ngược finding về source snapshot.

## Gói tối thiểu

Copy nguyên `.audit/` làm một folder trong vault. Không flatten file/folder.
Mở [[OBSIDIAN_HOME]] làm note đầu tiên.

Gói tối thiểu này giữ toàn bộ audit snapshot, findings, remediation ledger và
roadmap. Link trỏ ra `../docs/**` chỉ hoạt động nếu repo docs cũng được copy.

## Gói đầy đủ khuyến nghị

Giữ cấu trúc sau trong cùng vault:

```text
AcneLLM/
  .audit/
  docs/
  research/evaluation/reports/   # nếu cần evidence eval
  README.md
```

Không cần đưa binary model, Chroma DB, cache hoặc raw dataset lớn vào vault.
Thay vào đó giữ manifest/hash/provenance note; binary không tạo knowledge graph
hữu ích và làm vault nặng.

## Thiết lập Obsidian

- Bật `Files & Links -> Automatically update internal links`.
- Giữ `New link format` là relative path hoặc shortest path only if unique.
- Không bật plugin tự động rewrite frontmatter hàng loạt trước lần kiểm đầu.
- Dùng tags: `#current`, `#historical`, `#planned`, `#unknown` khi bổ sung note.

## Kiểm sau export

1. Mở `OBSIDIAN_HOME.md` và đi đủ năm link đọc nhanh.
2. Kiểm link từ [[CURRENT_TRUTH]] tới remediation/roadmap.
3. Kiểm một finding module và truy ngược tới snapshot.
4. Tìm `LLMRouter`: kết quả current phải nói đã xóa; kết quả historical phải có
   ngày/run id, không được hiểu là runtime hiện hành.
5. Tìm `full evaluation`: phải thấy rõ “chưa chạy lại”, không suy thành pass.

## Cập nhật về sau

Không export lại bằng cách ghi đè mù toàn vault. Đồng bộ theo path, giữ note
người dùng riêng ngoài folder generated/audit, rồi cập nhật current truth và
reconciliation theo [[CONTEXT_INTEGRITY]].

Generator phải lấy HEAD/branch/ngày từ live repo, không hard-code snapshot cũ.
Sau mỗi build phải kiểm fingerprint trước/sau, manifest JSON/CSV parity,
wikilink, orphan, secret scan và hash của exact audit mirrors.
