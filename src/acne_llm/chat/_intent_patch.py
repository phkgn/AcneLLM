"""Va tam cho mot loi DU LIEU, khong phai luat nghiep vu.

═══ LOI GOC ═══

Intaker duoc fine-tune tren 4.000 dong, trong do 200 dong co lich su hoi thoai
va **ca 200 deu gan nhan `clarify`**. Do khong phai tai nan boc mau -- no bi dong
cung boi hai cho:

  1. `datagen/intakedata/taxonomy.yaml` chi co DUNG MOT case type sinh ra lich su
     (`clarify_followup_multiturn`), va `intent_hint` cua no ghi cung la `clarify`.
  2. `datagen/intakedata/generator.py::to_record` nem loi neu case type khac ma
     co lich su: "non-follow-up cases must have empty history".

Nen trong toan bo corpus KHONG TON TAI duong nao sinh ra mot luot follow-up mang
nhan `advise`. Thiet ke gop nham hai chieu vuong goc: "co lich su" la HINH DANG
cua mau du lieu, con "clarify" la Y DINH cua nguoi dung. Moi y dinh deu co the
xuat hien o luot thu hai.

Model hoc dung quy luat do -- tu goc nhin cua no, quy luat ay dung 100%.

═══ VI SAO VAN CHAP NHAN DUOC ═══

Thien kien tren la mot PRIOR, khong phai luat cung. Do bang tay: hoi "cho tao cai
code python dfs di" ngay sau mot luot tu van ve mun -> model van tra `reject`,
confidence 0.99. Tin hieu van ban du manh thi de duoc prior.

Nen ta chi ngung tin RIENG nhan `clarify`. `reject`, `knowledge`, `advise` van
nghe model. Pham vi hep nay quan trong: neu noi rong thanh "co lich su thi bo qua
intent" thi mot cu jailbreak o luot ba se di thang vao duong tu van.

Huong sai cua va nay cung la huong re hon. Ep advise khi le ra nen clarify thi
generator hoi lai -- no thay du kien trong va tu hoi. Nguoc lai, ep clarify khi
le ra nen advise thi nguoi dung bi chan khong duoc tra loi.

═══ XOA FILE NAY KHI ═══

Tap train co ca multi-turn mang nhan advise/knowledge/reject va intaker duoc
fine-tune lai. Kiem duoc bang mot dong:

    intent cua cac dong co >= 2 luot user trong intake.train.jsonl
    khong con la {'clarify': 100%}

Truoc do, `evaluation/datasets/make_intake_set.py` can nhom ca multi-turn de DO
xem model sai bao nhieu -- ke ca nhom reject-o-luot-hai, vi gia dinh "model van
nhan ra reject o luot sau" hien moi chi co mot mau chung minh.
"""
from __future__ import annotations

# Gan vao route_flags khi va duoc ap dung, de log/trace truy nguoc duoc.
CLARIFY_DOWNGRADED = "clarify_downgraded"

# Nhan DUY NHAT duoc phep sua. Khong noi rong danh sach nay.
_REPAIRABLE = "clarify"
_TARGET = "advise"


def repaired_intent(intent: str, has_established_case: bool) -> str:
    """Intent sau khi va. Tra NGUYEN BAN neu khong thuoc dien sua.

    `has_established_case` do caller tinh (intake._has_established_case) -- giu
    module nay thuan tuy, khong import nguoc.

    ponytail: mot ham, khong phai mot predicate + mot mapper. Caller so intent
    cu voi moi la biet co doi hay khong; xuat ca hai thi caller goi hai lan va
    dieu kien nam o hai cho.
    """
    if intent == _REPAIRABLE and has_established_case:
        return _TARGET
    return intent


def _demo() -> None:
    # Chi `clarify` bi sua, va chi khi phien da co ca that.
    assert repaired_intent("clarify", True) == "advise"
    assert repaired_intent("clarify", False) == "clarify"

    # Ba nhan con lai KHONG duoc dong toi, ke ca khi co lich su. Day la ranh gioi
    # an toan: noi rong ra la mot jailbreak o luot ba di thang vao duong tu van.
    for intent in ("reject", "knowledge", "advise"):
        assert repaired_intent(intent, True) == intent, intent
        assert repaired_intent(intent, False) == intent, intent

    assert CLARIFY_DOWNGRADED == "clarify_downgraded"
    print("intent patch demo OK")


if __name__ == "__main__":
    _demo()
