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


def test_patch_seed_thay_cue_xung_dot_chu_khong_chi_them():
    """`synthesize_seed` chỉ biết 6 lesion / 6 distribution. Nếu chỉ THÊM cue
    'sẹo rỗ' mà giữ 'mụn đầu đen' thì hai cue đánh nhau và seed thắng — đúng
    hiện tượng ở lượt thử: lesion_types ra đúng 6 giá trị của seed."""
    rng = random.Random(0)
    case = next(c for c in CASES if c.name == "scar")
    seed = patch_seed(case, {"required_user_cues": ["mụn đầu đen", "ở cằm"],
                             "lesion": "blackhead", "second_lesion": "papule"}, rng)
    cues = seed["required_user_cues"]
    assert CUE["scar"] in cues
    assert "mụn đầu đen" not in cues          # cue xung đột bị gỡ
    assert "ở cằm" in cues                    # cue KHÔNG xung đột thì giữ
    assert seed["lesion"] == "scar" and "second_lesion" not in seed


def test_patch_seed_vi_tri_go_dung_cue_vi_tri():
    rng = random.Random(0)
    case = next(c for c in CASES if c.name == "chest")
    seed = patch_seed(case, {"required_user_cues": ["ở cằm", "mụn đỏ"],
                             "distribution": "chin"}, rng)
    cues = seed["required_user_cues"]
    assert CUE["chest"] in cues and "ở cằm" not in cues
    assert "mụn đỏ" in cues                   # tổn thương không liên quan, giữ
    assert seed["distribution"] == "chest"


def test_medications_dat_hang_thuoc_UONG_khong_phai_kem_boi():
    """Lượt thử: medications nhận về 'benzoyl peroxide', 'adapalene' — đó là kem
    bôi, thuộc current_products. Seed chỉ có sản phẩm bôi nên phải tự cấp thuốc uống."""
    rng = random.Random(0)
    case = next(c for c in CASES if c.name == "medication")
    cues = patch_seed(case, {"required_user_cues": []}, rng)["required_user_cues"]
    assert any(c.startswith("đang uống ") for c in cues)
    assert not any("benzoyl peroxide" in c for c in cues)


def test_patch_seed_khong_dung_vao_ca_dang_chay_duoc():
    """Thai kỳ, cho bú, mức độ đều đạt quota ở lượt thử. Sửa thứ đang chạy được
    là tự chuốc rủi ro."""
    rng = random.Random(0)
    seed = {"required_user_cues": ["19 tuổi"], "lesion": "papule"}
    for name in ("pregnant_true", "breastfeeding_true", "sev_severe"):
        case = next(c for c in CASES if c.name == name)
        assert patch_seed(case, dict(seed), rng) == seed


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
        user = f"câu {generated['i']}"
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


def _run(mod, cases, provider, contaminated=frozenset()):
    return asyncio.run(mod.build(
        ANCHOR, cases, provider=provider, contaminated=set(contaminated),
        seed=0, attempts_factor=3, verbose=False,
    ))


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


def test_loai_cau_da_nam_trong_tap_train(wired):
    from datagen.intakedata.generator import user_turn_hash
    kept, _, rejects = _run(
        wired, (_case("context.is_pregnant", True, "preg", 1),),
        FakeProvider([_payload(is_pregnant={"value": True})]),
        contaminated={user_turn_hash("câu 1")})
    assert all(r["messages"][-2]["content"] != "câu 1" for r in kept)
    assert rejects["preg:trung_tap_train"] == 1


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
