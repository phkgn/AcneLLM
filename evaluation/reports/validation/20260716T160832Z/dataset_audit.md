# Dataset audit

- Target: `E:\project\AcneLLM\evaluation\datasets\v1\d1_dev_seed.jsonl`
- Directory: `E:\project\AcneLLM\evaluation\datasets\v1`

| File | Rows | Schema errors | Approved | Frozen | Exact dup | Near dup | Contradictions |
|---|---:|---:|---:|---|---:|---:|---:|
| `d1_dev_seed.jsonl` | 100 | 0 | 0 | no | 20 | 20 | 0 |
| `d2_test.jsonl` | 140 | 0 | 140 | no | 0 | 0 | 0 |
| `d3_challenge.jsonl` | 60 | 0 | 60 | no | 0 | 0 | 0 |
| `d4_safety.jsonl` | 140 | 0 | 140 | no | 0 | 0 | 0 |
| `d5_multiturn.jsonl` | 72 | 0 | 72 | no | 0 | 0 | 0 |
| `d6_ood.jsonl` | 96 | 0 | 96 | no | 0 | 0 | 0 |
| `d7_adversarial.jsonl` | 120 | 0 | 120 | no | 0 | 0 | 0 |
| `d8_qrels_seed.jsonl` | 100 | 0 | 0 | no | 20 | 20 | 0 |
| `t1_guardrails_seed.jsonl` | 20 | 0 | 0 | no | 0 | 0 | 0 |
| `t1_intent_seed.jsonl` | 24 | 0 | 0 | no | 0 | 0 | 0 |

## Train contamination

- Status: **CHECKED**
- Train: `E:\project\AcneLLM\data\finetune\clean\acne_chat_response.train.jsonl`
- n-gram / threshold: `8` / `0.5`
- `d1_dev_seed.jsonl`: 2 flagged — d1-0003, d1-0023
- `d8_qrels_seed.jsonl`: 2 flagged — d8-0003, d8-0023
- `t1_intent_seed.jsonl`: 2 flagged — t1i-0010, t1i-0023

## Cross-split leakage

- `mun viem o cam nguyen nhan la gi` → `[('d1_dev_seed.jsonl', 'd1-0000', None), ('d1_dev_seed.jsonl', 'd1-0020', None), ('d8_qrels_seed.jsonl', 'd8-0000', None), ('d8_qrels_seed.jsonl', 'd8-0020', None)]`
- `benzoyl peroxide co dung đuoc cho da nhay cam khong` → `[('d1_dev_seed.jsonl', 'd1-0001', None), ('d1_dev_seed.jsonl', 'd1-0021', None), ('d8_qrels_seed.jsonl', 'd8-0001', None), ('d8_qrels_seed.jsonl', 'd8-0021', None)]`
- `isotretinoin co an toan khi mang thai` → `[('d1_dev_seed.jsonl', 'd1-0002', None), ('d1_dev_seed.jsonl', 'd1-0022', None), ('d8_qrels_seed.jsonl', 'd8-0002', None), ('d8_qrels_seed.jsonl', 'd8-0022', None)]`
- `cach cham soc da mun tuoi day thi` → `[('d1_dev_seed.jsonl', 'd1-0003', None), ('d1_dev_seed.jsonl', 'd1-0023', None), ('d8_qrels_seed.jsonl', 'd8-0003', None), ('d8_qrels_seed.jsonl', 'd8-0023', None)]`
- `mun trung ca nang co đe lai seo khong` → `[('d1_dev_seed.jsonl', 'd1-0004', None), ('d1_dev_seed.jsonl', 'd1-0024', None), ('d8_qrels_seed.jsonl', 'd8-0004', None), ('d8_qrels_seed.jsonl', 'd8-0024', None)]`
- `salicylic acid nong đo bao nhieu la phu hop` → `[('d1_dev_seed.jsonl', 'd1-0005', None), ('d1_dev_seed.jsonl', 'd1-0025', None), ('d8_qrels_seed.jsonl', 'd8-0005', None), ('d8_qrels_seed.jsonl', 'd8-0025', None)]`
- `phan biet mun đau đen va mun đau trang` → `[('d1_dev_seed.jsonl', 'd1-0006', None), ('d1_dev_seed.jsonl', 'd1-0026', None), ('d8_qrels_seed.jsonl', 'd8-0006', None), ('d8_qrels_seed.jsonl', 'd8-0026', None)]`
- `mun noi tiet o phu nu 30 tuoi xu ly the nao` → `[('d1_dev_seed.jsonl', 'd1-0007', None), ('d1_dev_seed.jsonl', 'd1-0027', None), ('d8_qrels_seed.jsonl', 'd8-0007', None), ('d8_qrels_seed.jsonl', 'd8-0027', None)]`
- `co nen nan mun tai nha khong` → `[('d1_dev_seed.jsonl', 'd1-0008', None), ('d1_dev_seed.jsonl', 'd1-0028', None), ('d8_qrels_seed.jsonl', 'd8-0008', None), ('d8_qrels_seed.jsonl', 'd8-0028', None)]`
- `retinol va retinoid khac nhau the nao` → `[('d1_dev_seed.jsonl', 'd1-0009', None), ('d1_dev_seed.jsonl', 'd1-0029', None), ('d8_qrels_seed.jsonl', 'd8-0009', None), ('d8_qrels_seed.jsonl', 'd8-0029', None)]`
- `mun mu o ma cach đieu tri` → `[('d1_dev_seed.jsonl', 'd1-0010', None), ('d1_dev_seed.jsonl', 'd1-0030', None), ('d8_qrels_seed.jsonl', 'd8-0010', None), ('d8_qrels_seed.jsonl', 'd8-0030', None)]`
- `niacinamide giup gi cho da mun` → `[('d1_dev_seed.jsonl', 'd1-0011', None), ('d1_dev_seed.jsonl', 'd1-0031', None), ('d8_qrels_seed.jsonl', 'd8-0011', None), ('d8_qrels_seed.jsonl', 'd8-0031', None)]`
- `toi đang cho con bu dung tretinoin đuoc khong` → `[('d1_dev_seed.jsonl', 'd1-0012', None), ('d1_dev_seed.jsonl', 'd1-0032', None), ('d8_qrels_seed.jsonl', 'd8-0012', None), ('d8_qrels_seed.jsonl', 'd8-0032', None)]`
- `mun boc viem o mat trong suot nhieu thang` → `[('d1_dev_seed.jsonl', 'd1-0013', None), ('d1_dev_seed.jsonl', 'd1-0033', None), ('d8_qrels_seed.jsonl', 'd8-0013', None), ('d8_qrels_seed.jsonl', 'd8-0033', None)]`
- `thuoc uong đieu tri mun la gi` → `[('d1_dev_seed.jsonl', 'd1-0014', None), ('d1_dev_seed.jsonl', 'd1-0034', None), ('d8_qrels_seed.jsonl', 'd8-0014', None), ('d8_qrels_seed.jsonl', 'd8-0034', None)]`
- `tai sao da nhon de bi mun hon da kho` → `[('d1_dev_seed.jsonl', 'd1-0015', None), ('d1_dev_seed.jsonl', 'd1-0035', None), ('d8_qrels_seed.jsonl', 'd8-0015', None), ('d8_qrels_seed.jsonl', 'd8-0035', None)]`
- `azelaic acid co tac dung gi` → `[('d1_dev_seed.jsonl', 'd1-0016', None), ('d1_dev_seed.jsonl', 'd1-0036', None), ('d8_qrels_seed.jsonl', 'd8-0016', None), ('d8_qrels_seed.jsonl', 'd8-0036', None)]`
- `lam sao giam tham sau mun` → `[('d1_dev_seed.jsonl', 'd1-0017', None), ('d1_dev_seed.jsonl', 'd1-0037', None), ('d8_qrels_seed.jsonl', 'd8-0017', None), ('d8_qrels_seed.jsonl', 'd8-0037', None)]`
- `kem chong nang cho da mun chon loai nao` → `[('d1_dev_seed.jsonl', 'd1-0018', None), ('d1_dev_seed.jsonl', 'd1-0038', None), ('d8_qrels_seed.jsonl', 'd8-0018', None), ('d8_qrels_seed.jsonl', 'd8-0038', None)]`
- `che đo an uong anh huong the nao toi mun` → `[('d1_dev_seed.jsonl', 'd1-0019', None), ('d1_dev_seed.jsonl', 'd1-0039', None), ('d8_qrels_seed.jsonl', 'd8-0019', None), ('d8_qrels_seed.jsonl', 'd8-0039', None)]`
- `mun o tran va long may do đau` → `[('d1_dev_seed.jsonl', 'd1-0040', None), ('d8_qrels_seed.jsonl', 'd8-0040', None)]`
- `doxycycline giup tri mun nhu the nao` → `[('d1_dev_seed.jsonl', 'd1-0041', None), ('d8_qrels_seed.jsonl', 'd8-0041', None)]`
- `mun o quanh mieng va cam o phu nu tuoi 35` → `[('d1_dev_seed.jsonl', 'd1-0042', None), ('d8_qrels_seed.jsonl', 'd8-0042', None)]`
- `co the dung cac san pham mun khac nhau cung luc khong` → `[('d1_dev_seed.jsonl', 'd1-0043', None), ('d8_qrels_seed.jsonl', 'd8-0043', None)]`
- `mun trung ca o lung cach khac phuc` → `[('d1_dev_seed.jsonl', 'd1-0044', None), ('d8_qrels_seed.jsonl', 'd8-0044', None)]`
- `spironolactone co hieu qua voi mun noi tiet khong` → `[('d1_dev_seed.jsonl', 'd1-0045', None), ('d8_qrels_seed.jsonl', 'd8-0045', None)]`
- `mun xuat hien sau khi dung my pham moi phai lam sao` → `[('d1_dev_seed.jsonl', 'd1-0046', None), ('d8_qrels_seed.jsonl', 'd8-0046', None)]`
- `aha bha co phu hop cho da nhay cam khong` → `[('d1_dev_seed.jsonl', 'd1-0047', None), ('d8_qrels_seed.jsonl', 'd8-0047', None)]`
- `tay da chet co lam mun tro nen toi te hon` → `[('d1_dev_seed.jsonl', 'd1-0048', None), ('d8_qrels_seed.jsonl', 'd8-0048', None)]`
- `mun o mui va quanh mui nguyen nhan va cach tri` → `[('d1_dev_seed.jsonl', 'd1-0049', None), ('d8_qrels_seed.jsonl', 'd8-0049', None)]`
- `minocycline dung đuoc bao lau đe đieu tri mun` → `[('d1_dev_seed.jsonl', 'd1-0050', None), ('d8_qrels_seed.jsonl', 'd8-0050', None)]`
- `mun o tai va co nguyen nhan gay ra` → `[('d1_dev_seed.jsonl', 'd1-0051', None), ('d8_qrels_seed.jsonl', 'd8-0051', None)]`
- `vitamin c serum co giup mun khong` → `[('d1_dev_seed.jsonl', 'd1-0052', None), ('d8_qrels_seed.jsonl', 'd8-0052', None)]`
- `mun nang tu thang thu 2 cua ky kinh nguyem nhu the nao` → `[('d1_dev_seed.jsonl', 'd1-0053', None), ('d8_qrels_seed.jsonl', 'd8-0053', None)]`
- `co the dung mat ong đe chua mun` → `[('d1_dev_seed.jsonl', 'd1-0054', None), ('d8_qrels_seed.jsonl', 'd8-0054', None)]`
- `mun mu nho lan rong tren da phai xu ly cap tap` → `[('d1_dev_seed.jsonl', 'd1-0055', None), ('d8_qrels_seed.jsonl', 'd8-0055', None)]`
- `dung kem duong am co gay mun khong` → `[('d1_dev_seed.jsonl', 'd1-0056', None), ('d8_qrels_seed.jsonl', 'd8-0056', None)]`
- `kem tri mun co chua sulfur co hieu qua` → `[('d1_dev_seed.jsonl', 'd1-0057', None), ('d8_qrels_seed.jsonl', 'd8-0057', None)]`
- `mun o nguoi lon tuoi 40 nguyen nhan va cach cham soc` → `[('d1_dev_seed.jsonl', 'd1-0058', None), ('d8_qrels_seed.jsonl', 'd8-0058', None)]`
- `zinc co giup giam mun khong` → `[('d1_dev_seed.jsonl', 'd1-0059', None), ('d8_qrels_seed.jsonl', 'd8-0059', None)]`
- `mun sau khi wax cao long phai lam sao` → `[('d1_dev_seed.jsonl', 'd1-0060', None), ('d8_qrels_seed.jsonl', 'd8-0060', None)]`
- `led light therapy co hieu qua voi mun khong` → `[('d1_dev_seed.jsonl', 'd1-0061', None), ('d8_qrels_seed.jsonl', 'd8-0061', None)]`
- `tretinoin bat đau tu nong đo nao la an toan` → `[('d1_dev_seed.jsonl', 'd1-0062', None), ('d8_qrels_seed.jsonl', 'd8-0062', None)]`
- `mun o nguoi nam tuoi 50 nguyen nhan tai sao` → `[('d1_dev_seed.jsonl', 'd1-0063', None), ('d8_qrels_seed.jsonl', 'd8-0063', None)]`
- `nen su dung kem tri mun buoi sang hay buoi toi` → `[('d1_dev_seed.jsonl', 'd1-0064', None), ('d8_qrels_seed.jsonl', 'd8-0064', None)]`
- `mun do stress đieu gi xay ra trong co the` → `[('d1_dev_seed.jsonl', 'd1-0065', None), ('d8_qrels_seed.jsonl', 'd8-0065', None)]`
- `sulfamethoxazole trimethoprim co tac dung voi mun khong` → `[('d1_dev_seed.jsonl', 'd1-0066', None), ('d8_qrels_seed.jsonl', 'd8-0066', None)]`
- `seo mun tham co lay laser đuoc khong` → `[('d1_dev_seed.jsonl', 'd1-0067', None), ('d8_qrels_seed.jsonl', 'd8-0067', None)]`
- `mun do kem chong nang chon loai nao` → `[('d1_dev_seed.jsonl', 'd1-0068', None), ('d8_qrels_seed.jsonl', 'd8-0068', None)]`
- `tam tay kho da co cai thien mun khong` → `[('d1_dev_seed.jsonl', 'd1-0069', None), ('d8_qrels_seed.jsonl', 'd8-0069', None)]`

## Human review queue

- `d2-0019` — Missing-information query has overly specific expected points. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d2_test.jsonl`
- `d2-0049` — Missing-information query has overly specific expected points. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d2_test.jsonl`
- `d3-0041` — Missing-information query has overly specific expected points. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d3_challenge.jsonl`
- `d7-0001` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0002` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0006` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0011` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0012` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0019` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0020` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0025` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0027` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0033` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0038` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0039` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0041` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0045` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0049` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0054` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0055` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0059` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0067` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0070` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0073` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0075` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0078` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0079` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0085` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0086` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0095` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0098` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0100` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0073-typo3` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0012-typo8` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0067-typo9` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0001-typo10` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `t1g-0006` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\t1_guardrails_seed.jsonl`
- `t1g-0010` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\t1_guardrails_seed.jsonl`
- `t1g-0014` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\t1_guardrails_seed.jsonl`
- `t1i-0010` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\t1_intent_seed.jsonl`

## Interpretation rule

Synthetic generation provenance is acceptable only after human approval and SHA-256 freeze. D8 remains a reference-only retrieval set while its labels are `needs_relabel`.
