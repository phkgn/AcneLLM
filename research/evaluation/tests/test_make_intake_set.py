"""Bộ đề intake mới — cổng "đặt hàng gì phải ra đúng thứ đó".

Cả giá trị của bộ này nằm ở `satisfies`. Nếu nó hỏng, ta được một file trông
phủ đủ nhưng nội dung lệch y như bộ cũ — tệ hơn không có, vì lần này ta TIN nó.

Bối cảnh: bộ cũ có 0 dòng `is_pregnant=True` trên 400 dòng val, và không có
cảnh báo nào. Field đó quyết định chống chỉ định isotretinoin.

Provider giả, không gọi mạng.
"""
from __future__ import annotations

import asyncio
import json

import pytest

import random

from evaluation.datasets.make_intake_set import (
    ANY,
    CASES,
    CUE,
    TOTAL,
    Case,
    build,
    coverage,
    dig,
    patch_seed,
    satisfies,
    spec_of,
)

ANCHOR = "neo giả"


def _payload(**over):
    base = {
        "intent": "advise", "confidence": 0.9, "description": "x",
        "context": {"is_pregnant": None, "is_breastfeeding": None,
                    "allergies": [], "medications": []},
        "clinical": {"inflammation_level": None, "lesion_types": [],
                     "lesion_distribution": []},
    }
    for key, value in over.items():
        grp = "context" if key in base["context"] else "clinical"
        base[grp][key] = value
    return base


def _case(path, expect, name="t", quota=1):
    return Case(name, quota, "advise_selfreport_rich", path, expect, "b")


# ── cổng kiểm ───────────────────────────────────────────────────────────────

def test_dat_hang_co_thai_ma_ra_so_1_van_la_SAI():
    """Python coi 1 == True. Nếu `satisfies` dùng `==` thì một payload hỏng trả
    số 1 sẽ lọt qua như 'có thai'. Đây là field chống chỉ định isotretinoin."""
    assert satisfies(_payload(is_pregnant={"value": True}),
                     _case("context.is_pregnant", True))
    assert not satisfies(_payload(is_pregnant={"value": 1}),
                         _case("context.is_pregnant", True))
    assert not satisfies(_payload(is_pregnant={"value": "yes"}),
                         _case("context.is_pregnant", True))


def test_khong_khai_khac_khai_la_False():
    assert satisfies(_payload(is_pregnant={"value": False}),
                     _case("context.is_pregnant", False))
    assert not satisfies(_payload(), _case("context.is_pregnant", False))


def test_list_phai_CHUA_dung_gia_tri_dat_hang():
    p = _payload(lesion_types=[{"value": "papule"}, {"value": "cyst"}])
    assert satisfies(p, _case("clinical.lesion_types", "cyst"))
    assert not satisfies(p, _case("clinical.lesion_types", "scar"))


def test_ANY_chi_can_khac_rong():
    assert satisfies(_payload(allergies=[{"value": "retinol"}]),
                     _case("context.allergies", ANY))
    assert not satisfies(_payload(), _case("context.allergies", ANY))
    assert not satisfies(_payload(inflammation_level={"value": "unknown"}),
                         _case("clinical.inflammation_level", ANY))


def test_dig_go_lop_value_va_khong_vo_voi_duong_dan_sai():
    p = _payload(inflammation_level={"value": "severe", "confidence": 0.9})
    assert dig(p, "clinical.inflammation_level") == "severe"
    assert dig(p, "khong.co.duong") is None
    assert dig(p, "intent") == "advise"


# ── bảng đặt hàng ───────────────────────────────────────────────────────────

def test_dung_500_dong_va_khong_trung_ten():
    assert TOTAL == 500
    assert len({c.name for c in CASES}) == len(CASES)
    assert all(c.quota > 0 for c in CASES)


@pytest.mark.parametrize("path", [
    "context.is_pregnant", "context.is_breastfeeding",
    "context.allergies", "context.medications",
])
def test_bon_field_an_toan_deu_duoc_dat_hang(path):
    """Bốn field này từng có lift +0.005 / +0.011 / 0.250 / âm — tức là gần như
    không có bằng chứng nào. Bộ mới KHÔNG được bỏ sót chúng."""
    assert path in {c.path for c in CASES}


def test_ca_mang_thai_du_lon_de_ket_luan():
    """Dưới 30 dòng thì khoảng tin cậy rộng tới mức không phân biệt nổi model
    tốt với model tung đồng xu."""
    for name in ("pregnant_true", "breastfeeding_true"):
        assert next(c for c in CASES if c.name == name).quota >= 30


def test_van_giu_do_phu_dinh_tuyen():
    """Định tuyến đang chạy tốt (macro-F1 0.896). Bỏ nó khỏi bộ mới thì mất mốc
    so sánh và không biết thay đổi prompt có phá gì không."""
    intents = {c.expect for c in CASES if c.path == "intent"}
    assert {"knowledge", "reject", "clarify"} <= intents


# ── hai lỗi bắt được ở lượt chạy thử ────────────────────────────────────────

def test_intent_hint_theo_ca_chu_khong_hardcode_advise():
    """Bản đầu hardcode intent_hint='advise' cho MỌI ca, nên reject_rx/clarify/
    greeting nhận prompt bảo 'INTENT BẮT BUỘC: advise' rồi bị chính cổng của
    mình loại. Đo được: 0/1, 0/1, 0/1."""
    for name, expect in (("reject_rx", "reject"), ("greeting", "clarify"),
                         ("knowledge", "knowledge")):
        case = next(c for c in CASES if c.name == name)
        assert spec_of(case).intent_hint == expect
    # Ca không đặt hàng intent thì vẫn là advise.
    assert spec_of(next(c for c in CASES if c.name == "cyst")).intent_hint == "advise"


def test_khong_bom_noi_dung_dat_hang_vao_cue():
    """Cue la hop dong khop NGUYEN VAN, ma `satisfies()` da kiem gia tri bang
    ngu nghia roi. Bom vao ca hai -> kiem hai lan, va lan chuoi luon thua:
    lượt 500 dòng cho cyst 0/30, allergy 0/40, medication 8/35 vì model viết
    "cục to sâu dưới da" chứ không viết đúng chuỗi "mụn nang, cục to sâu dưới da".
    """
    rng = random.Random(0)
    for name in ("scar", "cyst", "chest", "medication", "allergy"):
        case = next(c for c in CASES if c.name == name)
        seed = patch_seed(case, {"required_user_cues": ["ở cằm", "38 tuổi"]}, rng)
        cues = seed["required_user_cues"]
        assert all(c in ("ở cằm", "38 tuổi") for c in cues), (name, cues)


def test_van_go_cue_xung_dot_cua_seed():
    """Seed chỉ biết 6 lesion / 6 distribution. Giữ cue 'mụn đầu đen' khi đang
    đặt hàng 'scar' thì hai bên đánh nhau trong cùng prompt và seed thắng."""
    rng = random.Random(0)
    seed = patch_seed(
        next(c for c in CASES if c.name == "scar"),
        {"required_user_cues": ["mụn đầu đen", "ở cằm"],
         "lesion": "blackhead", "second_lesion": "papule"}, rng)
    assert "mụn đầu đen" not in seed["required_user_cues"]
    assert "ở cằm" in seed["required_user_cues"]      # không xung đột thì giữ
    assert seed["lesion"] == "scar" and "second_lesion" not in seed

    seed = patch_seed(
        next(c for c in CASES if c.name == "chest"),
        {"required_user_cues": ["ở cằm", "mụn đỏ"], "distribution": "chin"}, rng)
    assert "ở cằm" not in seed["required_user_cues"]
    assert "mụn đỏ" in seed["required_user_cues"]
    assert seed["distribution"] == "chest"


def test_thuoc_uong_va_di_ung_di_vao_SEED_khong_vao_cue():
    """SEED được dump nguyên vào prompt nên model vẫn thấy; nhưng không bị ràng
    buộc khớp chuỗi. "bị dị ứng benzoyl peroxide" trượt vì model viết
    "bị dị ứng VỚI benzoyl peroxide"."""
    rng = random.Random(0)
    med = patch_seed(next(c for c in CASES if c.name == "medication"),
                     {"required_user_cues": []}, rng)
    assert med["medication"] and med["required_user_cues"] == []
    alg = patch_seed(next(c for c in CASES if c.name == "allergy"),
                     {"required_user_cues": []}, rng)
    assert alg["allergy"] and alg["required_user_cues"] == []


def test_ca_muc_do_khong_bi_dung_toi():
    """Mức độ đạt quota và phân bố tốt ở lượt 500 dòng — sửa thứ đang chạy được
    là tự chuốc rủi ro."""
    rng = random.Random(0)
    seed = {"required_user_cues": ["19 tuổi"], "lesion": "papule"}
    for name in ("sev_severe", "sev_mild", "sev_none"):
        case = next(c for c in CASES if c.name == name)
        assert patch_seed(case, dict(seed), rng) == seed


def test_thai_ky_va_cho_bu_ep_ve_nu_nhung_khong_bat_viet_chu_nu():
    """Ép nhãn về nữ vì lượt 500 dòng có 25/45 ca mang thai mang nhãn sex=male.
    Nhưng KHÔNG thêm cue "nữ": "đang cho con bú" đã hàm ý nữ, bắt viết thêm chữ
    "nữ" là ép câu thành gượng — lượt sau đó rớt 33 lần đúng vì cue này."""
    rng = random.Random(0)
    for name in ("pregnant_true", "breastfeeding_true"):
        case = next(c for c in CASES if c.name == name)
        seed = patch_seed(case, {"sex": "male",
                                 "required_user_cues": ["31 tuổi", "nam"]}, rng)
        assert seed["sex"] == "female"
        assert seed["required_user_cues"] == ["31 tuổi"]    # gỡ "nam", không thêm gì


def test_moc_thoi_gian_thai_ky_da_dang_va_di_vao_SEED():
    """37/45 câu ra đúng '5 tháng' vì behavior nêu ví dụ đó và model chép thẳng.
    Mốc do seed cấp ngẫu nhiên, đi vào SEED chứ không vào cue — "bầu được 3 tháng"
    là đúng nội dung nhưng trượt cue "bầu 3 tháng"."""
    case = next(c for c in CASES if c.name == "pregnant_true")
    assert "5 tháng" not in case.behavior

    rng = random.Random(0)
    moc = {patch_seed(case, {"required_user_cues": []}, rng)["stage"]
           for _ in range(20)}
    assert len(moc) >= 5, "mốc thời gian phải đổi giữa các lần gọi"


def test_ca_pregnant_false_khong_bi_ep_gioi():
    """Nói 'em không có bầu' thì không suy ra được giới tính."""
    rng = random.Random(0)
    case = next(c for c in CASES if c.name == "pregnant_false")
    seed = patch_seed(case, {"sex": "male", "required_user_cues": ["nam"]}, rng)
    assert seed["sex"] == "male"


# ── đường chạy ──────────────────────────────────────────────────────────────

class FakeProvider:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = 0

    async def generate(self, messages):
        self.calls += 1
        return {"i": self.calls,
                "payload": self.payloads[(self.calls - 1) % len(self.payloads)]}


@pytest.fixture
def wired(monkeypatch):
    import evaluation.datasets.make_intake_set as mod

    def fake_to_record(spec, generated, anchor, *, source, seed=None):
        # Generator giả phải tuân ĐÚNG hợp đồng của generator thật: user_turn
        # chứa nguyên văn mọi cue. Không thì `cue_violations` loại sạch và test
        # đo nhầm thứ khác.
        cues = " ".join((seed or {}).get("required_user_cues") or ())
        user = f"câu {generated['i']} {cues}".strip()
        return {"id": f"r{generated['i']}",
                "messages": [{"role": "system", "content": anchor},
                             {"role": "user", "content": user},
                             {"role": "assistant", "content": json.dumps(
                                 generated["payload"], ensure_ascii=False)}],
                "meta": {}}

    monkeypatch.setattr(mod, "to_record", fake_to_record)
    monkeypatch.setattr(mod, "build_gen_prompt", lambda spec, seed: [])
    monkeypatch.setattr(mod, "synthesize_seed", lambda base, rng: {})
    monkeypatch.setattr(mod, "evaluate_record",
                        lambda r, s: type("R", (), {"passed": True, "reasons": []}))
    monkeypatch.setattr(mod.CorpusGateState, "accept", lambda self, r, p: None)
    return mod


def _run(mod, cases, provider, contaminated=frozenset(), concurrency=1):
    return asyncio.run(mod.build(
        ANCHOR, cases, provider=provider, contaminated=set(contaminated),
        seed=0, attempts_factor=3, verbose=False, concurrency=concurrency,
    ))


def test_song_song_khong_lam_vuot_quota(wired):
    """Ban theo lo thi de ban thua. Quota 2, concurrency 8 -> van dung 2 dong,
    va khong goi provider qua 2 lan cho lo dau."""
    provider = FakeProvider([_payload(lesion_types=[{"value": "cyst"}])])
    kept, got, _ = _run(wired, (_case("clinical.lesion_types", "cyst", "cyst", 2),),
                        provider, concurrency=8)
    assert got["cyst"] == 2 and len(kept) == 2
    assert provider.calls == 2, f"ban {provider.calls} request cho quota 2"


def test_song_song_khong_pha_chong_trung(wired, monkeypatch):
    """`state.duplicate_user` la trang thai chia se. Neu xet duyet chay song song
    thi hai dong giong nhau cung lot. Fake tra CUNG mot cau moi lan.

    Dung monkeypatch chu KHONG gan thang vao class: gan thang thi mutation ro
    sang test khac va `datagen/.../test_gates.py` do theo, chi khi chay ca bo.
    """
    def same_record(spec, generated, anchor, *, source, seed=None):
        return {"id": "r", "messages": [
            {"role": "system", "content": ANCHOR},
            {"role": "user", "content": "y hệt nhau"},
            {"role": "assistant", "content": json.dumps(
                _payload(lesion_types=[{"value": "cyst"}]))}], "meta": {}}

    seen: set[str] = set()
    monkeypatch.setattr(wired.CorpusGateState, "duplicate_user",
                        lambda self, t: t in seen)
    monkeypatch.setattr(wired.CorpusGateState, "accept",
                        lambda self, r, p: seen.add(r["messages"][-2]["content"]))
    monkeypatch.setattr(wired, "to_record", same_record)

    kept, _, rejects = _run(
        wired, (_case("clinical.lesion_types", "cyst", "cyst", 3),),
        FakeProvider([_payload(lesion_types=[{"value": "cyst"}])]), concurrency=8)
    assert len(kept) == 1, "trùng nội dung phải bị chặn dù chạy song song"
    assert rejects["cyst:trung_trong_bo"] >= 1


def test_loai_dong_khong_dat_yeu_cau_va_sinh_bu(wired):
    """Provider trả xen kẽ đúng/sai; chỉ dòng ĐÚNG được giữ, và vẫn đủ quota."""
    dung = _payload(is_pregnant={"value": True})
    sai = _payload(is_pregnant={"value": False})
    kept, got, rejects = _run(
        wired, (_case("context.is_pregnant", True, "preg", 2),),
        FakeProvider([dung, sai]))
    # đúng, sai, đúng -> đủ quota ở lượt 3, nên chỉ một lần loại
    assert got["preg"] == 2 and len(kept) == 2
    assert rejects["preg:khong_dat_yeu_cau"] == 1
    for record in kept:
        assert json.loads(record["messages"][-1]["content"])["context"][
            "is_pregnant"]["value"] is True


def test_loai_dong_co_nhan_khong_co_can_cu_trong_cau():
    """`build_gen_prompt` ra lệnh user_turn phải chứa NGUYÊN VĂN từng cue. Bộ cũ
    vi phạm 5,1% ở train / 6,2% ở val — mỗi lần là một nhãn vàng không có căn cứ,
    và model trích đúng (không bịa) lại bị chấm sai."""
    from evaluation.datasets.make_intake_set import cue_violations
    seed = {"required_user_cues": ["22 tuổi", "nữ", "đang dùng adapalene"]}
    assert cue_violations(seed, "Em 22 tuổi, nữ, đang dùng adapalene được 3 tuần") == []
    assert cue_violations(seed, "Em 22 tuổi, nữ, da dầu") == ["đang dùng adapalene"]
    assert cue_violations({}, "bất kỳ câu nào") == []


def test_loai_cau_da_nam_trong_tap_train(wired):
    """`patch_seed` không còn thêm cue nào cho ca này, nên câu giả là "câu 1"."""
    from datagen.intakedata.generator import user_turn_hash
    kept, _, rejects = _run(
        wired, (_case("clinical.lesion_types", "cyst", "cyst", 1),),
        FakeProvider([_payload(lesion_types=[{"value": "cyst"}])]),
        contaminated={user_turn_hash("câu 1")})
    assert all(r["messages"][-2]["content"] != "câu 1" for r in kept)
    assert rejects["cyst:trung_tap_train"] == 1


def test_khong_treo_vo_han_khi_provider_luon_sai(wired):
    provider = FakeProvider([_payload()])
    kept, got, _ = _run(wired, (_case("context.is_pregnant", True, "preg", 5),),
                        provider)
    assert kept == [] and got["preg"] == 0
    assert provider.calls == 5 * 3          # đúng trần attempts_factor


def test_gan_nhan_ca_vao_meta(wired):
    kept, _, _ = _run(wired, (_case("clinical.lesion_types", "cyst", "cyst", 1),),
                      FakeProvider([_payload(lesion_types=[{"value": "cyst"}])]))
    assert kept[0]["meta"]["eval_case"] == "cyst"


def test_seed_duoc_truyen_vao_record_lam_bang_chung_dat_hang(monkeypatch):
    """Không ghi seed thì không ai dựng lại được bộ dữ liệu, và câu hỏi
    'data này từ đâu ra' không có gì để trả lời ngoài 'AI sinh ra'."""
    import evaluation.datasets.make_intake_set as mod
    nhan = {}

    def spy(spec, generated, anchor, *, source, seed=None):
        nhan["seed"] = seed
        nhan["source"] = source
        return {"id": "r1", "messages": [
            {"role": "system", "content": ANCHOR},
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": json.dumps(
                _payload(is_pregnant={"value": True}))}], "meta": {}}

    monkeypatch.setattr(mod, "to_record", spy)
    monkeypatch.setattr(mod, "build_gen_prompt", lambda spec, seed: [])
    monkeypatch.setattr(mod, "evaluate_record",
                        lambda r, s: type("R", (), {"passed": True, "reasons": []}))
    monkeypatch.setattr(mod.CorpusGateState, "accept", lambda self, r, p: None)

    case = next(c for c in CASES if c.name == "pregnant_true")
    _run(mod, (Case(case.name, 1, case.base, case.path, case.expect, case.behavior),),
         FakeProvider([None]))

    assert nhan["source"] == "intake_eval:pregnant_true"
    assert nhan["seed"] is not None and nhan["seed"] != {}
    # Seed phải là seed ĐÃ VÁ, không phải seed thô — nếu không thì bằng chứng
    # ghi lại khác với thứ thật sự gửi đi.
    assert nhan["seed"]["sex"] == "female"


def test_khu_trung_ngu_nghia_chay_o_CUOI_va_giu_ban_dau(monkeypatch):
    """`duplicate_user` chi khop chuoi, nen 500 dong sinh ra van co the na na
    nhau — dung loi da lam bo v2 lot 15 ban trung va lam CI hep gia."""
    import evaluation.datasets.make_eval_set as mes
    import numpy as np

    vecs = {"a": [1.0, 0.0], "a gần giống": [1.0, 0.02], "khác hẳn": [0.0, 1.0]}

    class E:
        def embed_passages(self, texts):
            return np.asarray([vecs[t] for t in texts], dtype=np.float32)

    monkeypatch.setattr(mes, "_embedder", lambda: E())

    recs = [{"messages": [{"role": "u"}, {"role": "user", "content": t},
                          {"role": "assistant", "content": "{}"}]} for t in vecs]
    from evaluation.datasets.make_intake_set import drop_near_duplicates
    kept, dropped = drop_near_duplicates(recs, threshold=0.9)

    assert [r["messages"][-2]["content"] for r in kept] == ["a", "khác hẳn"]
    assert len(dropped) == 1


def test_verify_dem_lai_tu_FILE_khong_tin_bo_dem_luc_sinh():
    """`got` đếm theo ý định của vòng lặp. Nếu write_jsonl khử trùng id hoặc một
    dòng lọt sai chỗ thì chỉ cách đọc lại nội dung mới thấy."""
    from evaluation.datasets.make_intake_set import verify
    cases = (_case("context.is_pregnant", True, "preg", 3),
             _case("clinical.lesion_types", "cyst", "cyst", 1))
    records = [
        {"messages": [{"role": "assistant", "content": json.dumps(
            _payload(is_pregnant={"value": True},
                     lesion_types=[{"value": "cyst"}]))}]},
        {"messages": [{"role": "assistant", "content": json.dumps(_payload())}]},
    ]
    # Dòng đầu thoả CẢ HAI đơn hàng -> tính cho cả hai. Đây là độ phủ THẬT.
    assert verify(records, cases) == [("preg", 1, 3), ("cyst", 1, 1)]


def test_coverage_doc_lai_tu_NOI_DUNG_khong_tin_nhan_meta():
    """Nhãn meta do ta tự gắn nên không chứng minh được gì. Bảng độ phủ phải
    đọc lại JSON thật — đó mới là thứ run_intake sẽ chấm."""
    records = [
        {"messages": [{"role": "assistant", "content": json.dumps(
            _payload(is_pregnant={"value": True},
                     lesion_types=[{"value": "cyst"}, {"value": "scar"}]))}],
         "meta": {"eval_case": "nhãn sai bét"}},
        {"messages": [{"role": "assistant", "content": json.dumps(_payload())}],
         "meta": {"eval_case": "cũng sai"}},
    ]
    cov = coverage(records)
    assert cov["is_pregnant"] == {"True": 1}
    assert cov["lesion_types"] == {"cyst": 1, "scar": 1}
    assert cov["intent"] == {"advise": 2}
    assert cov["medications"] == {}
