"""Khử trùng bộ đề bằng ngữ nghĩa + luật nhãn theo spec.

Bộ v2 lọt 15 bản trùng; một câu lặp 5 lần dưới 5 id khác nhau. Bootstrap CI giả
định mẫu độc lập nên trùng nội dung làm khoảng tin cậy hẹp hơn thực tế. Test này
giữ cho cơ chế khử trùng không âm thầm hỏng lại.

Không nạp embedder — tiêm vector giả để kiểm ĐÚNG phần logic.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

from evaluation.datasets import make_eval_set as mes


@pytest.fixture
def fake_embedder(monkeypatch):
    """Vector giả: câu giống nhau -> vector giống nhau."""
    def make(vectors):
        class E:
            def embed_passages(self, texts):
                return np.asarray([vectors[t] for t in texts], dtype=np.float32)
        monkeypatch.setattr(mes, "_embedder", lambda: E())
    return make


def test_bat_ban_trung_giu_ban_DAU_TIEN(fake_embedder):
    fake_embedder({
        "gốc":  [1.0, 0.0],
        "trùng": [1.0, 0.02],      # cosine ~1
        "khác":  [0.0, 1.0],
    })
    keep, dropped = mes.semantic_dedup(["gốc", "trùng", "khác"])
    assert keep == [0, 2]                      # giữ bản xuất hiện trước
    assert len(dropped) == 1
    cos, i, j = dropped[0]
    assert (i, j) == (1, 0) and cos > mes.NEAR_DUP_COSINE


def test_khong_du_2_cau_thi_khong_lam_gi(fake_embedder):
    fake_embedder({"a": [1.0, 0.0]})
    assert mes.semantic_dedup([]) == ([], [])
    assert mes.semantic_dedup(["a"]) == ([0], [])


def test_embedder_hong_thi_KHONG_giet_viec_ghi_file(monkeypatch, capsys):
    """Nhưng phải KÊU TO. Im lặng bỏ qua khử trùng chính là cách v2 lọt 15 bản."""
    def boom():
        raise ModuleNotFoundError("no sentence_transformers")
    monkeypatch.setattr(mes, "_embedder", boom)
    keep, dropped = mes.semantic_dedup(["a", "b"])
    assert keep == [0, 1] and dropped == []
    assert "KHÔNG khử trùng được" in capsys.readouterr().out


def test_write_jsonl_khu_ca_trung_id_lan_trung_y(tmp_path, fake_embedder):
    fake_embedder({"x": [1.0, 0.0], "y": [1.0, 0.01], "z": [0.0, 1.0]})
    path = tmp_path / "out.jsonl"
    mes.write_jsonl(path, [
        {"sample_id": "a", "user_query": "x"},
        {"sample_id": "a", "user_query": "z"},   # trùng id -> bản sau thắng
        {"sample_id": "b", "user_query": "y"},   # trùng ý với "x"… nhưng "x" đã bị id đè
    ])
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == 2
    assert {r["sample_id"] for r in rows} == {"a", "b"}


def test_moi_loai_reject_deu_thuoc_dung_3_loai_cua_spec():
    """Modelfile intaker: reject CHỈ là jailbreak / ngoài chủ đề / đòi kê đơn.
    Bộ v2 tự nghĩ ra 6 loại và gán sai 15 ca."""
    reject_tags = {tag for intent, tag in mes.SPEC_CASES if intent == "reject"}
    assert reject_tags == {"jailbreak", "ngoài chủ đề", "đòi kê đơn/liều"}


def test_dòi_chan_doan_la_ADVISE_khong_phai_reject():
    """Generator có luật 'Không chẩn đoán xác định', nhưng đó là RÀNG BUỘC KHI
    TRẢ LỜI chứ không phải lệnh từ chối."""
    advise_tags = {tag for intent, tag in mes.SPEC_CASES if intent == "advise"}
    assert "không_chẩn_đoán" in advise_tags
    assert "không_hướng_dẫn_thủ_thuật" in advise_tags
    assert all(tag in mes.CONSTRAINT_TEXT for tag in advise_tags)


def test_style_jitter_doi_phong_cach_moi_lan_goi():
    import random
    rng = random.Random(0)
    hints = {mes.style_hint(rng) for _ in range(10)}
    assert len(hints) >= 8          # gần như mỗi lần một kiểu
    assert all("PHONG CÁCH GÕ" in h for h in hints)
