"""Judge context + thang neo. Không gọi mạng — judge giả.

Phần code này viết trong ngày và chưa có test nào ngoài `demo()`, mà nó quyết
định toàn bộ điểm khâu 2 và 5 mặt context của khâu 3.
"""
from __future__ import annotations

import pytest

from evaluation.judges import context as cj
from evaluation.judges import rubrics


class FakeJudge:
    def __init__(self, payload):
        self.payload = payload
        self.prompts: list[str] = []

    def judge(self, prompt: str, **_):
        self.prompts.append(prompt)
        return self.payload


def test_moi_bac_diem_deu_co_moc_neo():
    """Lý do rubrics.py tồn tại: thang không neo thì con số không có nghĩa."""
    for text, bins in ((rubrics.ANSWER_QUALITY, "12345"),
                       (rubrics.ROLE_TONE, "12345"),
                       (rubrics.CHUNK_RELEVANCE, "012345"),
                       (rubrics.SUFFICIENCY, "012345"),
                       (rubrics.GROUNDEDNESS, "012345")):
        for b in bins:
            assert f"\n  {b}  " in text


def test_prompt_mang_theo_thang_neo():
    judge = FakeJudge({"grades": [3, 3], "sufficiency": 3})
    cj.score(judge, "mụn ở cằm?", ["a", "b"])
    for b in "012345":
        assert f"\n  {b}  " in judge.prompts[0]


def test_khong_co_chunk_thi_ra_None_khong_ra_0():
    """Arm tắt RAG: 'không có tài liệu' KHÁC 'tài liệu tệ'. Gộp thành 0 thì
    trung bình của arm có RAG bị kéo xuống vô cớ."""
    out = cj.score(FakeJudge({}), "q", [])
    assert all(out[face] is None for face in cj.FACES)
    assert out["details"]["n_chunks"] == 0


def test_precision_dem_theo_nguong_dung_duoc():
    out = cj.score(FakeJudge({"grades": [5, 3, 2, 0], "sufficiency": 4}),
                   "q", list("abcd"))
    assert out["context_precision"] == 0.5          # 5 và 3 đạt, 2 và 0 không
    assert out["context_relevance"] == 2.5
    assert out["context_sufficiency"] == 4.0
    assert rubrics.RELEVANT_THRESHOLD == 3.0


def test_ranking_quality_khong_can_chunk_vang():
    """nDCG lấy thứ tự lý tưởng từ CHÍNH điểm judge — đó là chỗ thoát khỏi
    việc phải biết trước đoạn nào là đoạn đúng."""
    xuoi = cj.score(FakeJudge({"grades": [5, 3, 1], "sufficiency": 3}), "q", list("abc"))
    nguoc = cj.score(FakeJudge({"grades": [1, 3, 5], "sufficiency": 3}), "q", list("abc"))
    assert xuoi["ranking_quality"] == 1.0
    assert nguoc["ranking_quality"] < xuoi["ranking_quality"]

    khong_lien_quan = cj.score(FakeJudge({"grades": [0, 0], "sufficiency": 0}), "q", ["a", "b"])
    assert khong_lien_quan["ranking_quality"] is None


def test_groundedness_chi_cham_khi_co_cau_tra_loi():
    payload = {"grades": [4], "sufficiency": 4, "groundedness": 2}
    khong = cj.score(FakeJudge(payload), "q", ["a"])
    assert khong["groundedness"] is None

    judge = FakeJudge(payload)
    co = cj.score(judge, "q", ["a"], answer="câu trả lời")
    assert co["groundedness"] == 2.0
    assert "BÁM TÀI LIỆU" in judge.prompts[0]


@pytest.mark.parametrize("payload", [
    {"grades": [1, 2], "sufficiency": 3},           # thiếu grade so với số chunk
    {"grades": [1, 2, 3, 4], "sufficiency": 3},     # thừa grade
    {"grades": [1, 2, 9], "sufficiency": 3},        # ngoài thang 0-5
    {"grades": [1, 2, 3], "sufficiency": None},     # thiếu sufficiency
    {"grades": "không phải list", "sufficiency": 3},
])
def test_judge_tra_ve_di_dang_thi_raise_chu_khong_am_tham_sai(payload):
    """Im lặng nuốt lỗi ở đây nghĩa là điểm sai mà không ai biết."""
    with pytest.raises(RuntimeError):
        cj.score(FakeJudge(payload), "q", list("abc"))
