"""Chấm chất lượng context bằng judge ngữ nghĩa — KHÔNG đếm từ.

Vì sao không đếm từ: KB là 60% tiếng Việt / 40% tiếng Anh. Mọi phép đo dựa trên
từ vựng đều thưởng cho đoạn CÙNG NGÔN NGỮ với câu hỏi bất kể nội dung, nên nó
đo ngôn ngữ chứ không đo liên quan. Hai metric cũ đã chết vì đúng lý do này:

  - grounding_support: `ROR` 0.16 vs `RRR` 0.48, hoá ra chỉ vì `RRR` chọn chunk
    theo độ trùng từ với câu hỏi nên câu trả lời nhắc lại từ trong câu hỏi là
    ăn điểm. Không so được giữa hai arm khác cách lấy context.
  - forbidden_claims: khớp chuỗi nguyên văn, kích hoạt 0 lần trên 770 dòng.

Cũng KHÔNG chấm bằng cross-encoder hay cosine của embedder: chính chúng đã chọn
ra 5 chunk đó, nhờ chúng chấm lại là tự chấm bài mình.

Bốn metric, một lượt gọi mỗi dòng:

  context_relevance    0-5   trung bình điểm liên quan của các chunk
  context_precision    0-1   tỉ lệ chunk thật sự liên quan (điểm >= 3)
  context_sufficiency  0-5   context có đủ để trả lời trọn câu hỏi không
  ranking_quality      0-1   nDCG trên chính điểm judge — chunk tốt có lên đầu không
  groundedness         0-5   câu trả lời bám vào tài liệu hay tự bịa (nếu truyền answer)

Ranking dùng nDCG nên KHÔNG cần chunk vàng: thứ tự lý tưởng là chính các điểm
judge sắp giảm dần. Đây là chỗ thoát khỏi việc phải biết "đoạn đúng" là đoạn nào.

`groundedness` thay `grounding_support` cũ (thang 0-1, lexical+cosine). Thang
khác nhau nên KHÔNG ghép được với artifact 804 dòng — cố ý, vì số cũ vốn đã
không so được giữa các arm.
"""
from __future__ import annotations

import json
import math
from typing import Any, Mapping, Sequence

from evaluation.judges import rubrics

RELEVANT_THRESHOLD = rubrics.RELEVANT_THRESHOLD   # thang neo ở judges/rubrics.py
MAX_CHUNK_CHARS = 1500       # cắt để prompt không phình; đủ để judge nắm nội dung

FACES = ("context_relevance", "context_precision",
         "context_sufficiency", "ranking_quality", "groundedness")


def build_prompt(question: str, chunks: Sequence[str],
                 expected_points: Sequence[str] = (),
                 answer: str | None = None) -> str:
    blocks = "\n\n".join(
        f"[Đoạn {i}]\n{(c or '')[:MAX_CHUNK_CHARS]}"
        for i, c in enumerate(chunks, 1)
    )
    ground_rule = ground_field = ground_block = ""
    if answer:
        ground_rule = f"\n{rubrics.GROUNDEDNESS}\n"
        ground_field = ', "groundedness": số'
        ground_block = f"\nCâu trả lời hệ thống đã đưa ra:\n{answer}\n"

    return f"""Bạn là trọng tài độc lập đánh giá CHẤT LƯỢNG TÀI LIỆU mà một hệ
thống tìm kiếm đã lấy về cho một câu hỏi về da mụn.

Tài liệu có thể bằng tiếng Việt HOẶC tiếng Anh. Ngôn ngữ không ảnh hưởng điểm —
chỉ chấm nội dung có trả lời được câu hỏi hay không.

{rubrics.CHUNK_RELEVANCE}

{rubrics.SUFFICIENCY}
{ground_rule}
Chỉ trả về JSON:
{{"grades": [số cho từng đoạn theo đúng thứ tự], "sufficiency": số{ground_field}, "reason": chuỗi}}

Câu hỏi: {question}
Các ý người dùng cần biết: {json.dumps(list(expected_points), ensure_ascii=False)}
{ground_block}
{blocks}
"""


def _ndcg(grades: Sequence[float]) -> float | None:
    """Chunk tốt có được xếp lên đầu không. Thứ tự lý tưởng = chính grades giảm dần.

    Không cần chunk vàng — đó là điểm mấu chốt: ta chấm thứ hạng bằng độ liên quan
    do judge gán, chứ không bằng một danh sách đáp án cố định.
    """
    if not grades or max(grades) <= 0:
        return None
    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(grades))
    ideal = sum(g / math.log2(i + 2)
                for i, g in enumerate(sorted(grades, reverse=True)))
    return round(dcg / ideal, 4) if ideal else None


def _grade(value: Any, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 5:
        raise RuntimeError(f"context judge {name} không hợp lệ: {value!r}")
    return float(value)


def score(
    judge: Any,
    question: str,
    chunks: Sequence[str],
    expected_points: Sequence[str] = (),
    answer: str | None = None,
) -> dict[str, Any]:
    """Trả các metric + chi tiết. Context rỗng (arm tắt RAG) → toàn None.

    Arm tắt RAG ra None chứ không ra 0: "không có tài liệu" khác "tài liệu tệ",
    gộp hai cái thành 0 thì trung bình của arm RAG bị kéo xuống vô cớ.
    """
    if not chunks:
        return {face: None for face in FACES} | {"details": {"n_chunks": 0}}

    result = judge.judge(build_prompt(question, chunks, expected_points, answer))
    if not isinstance(result, Mapping):
        raise RuntimeError("context judge returned invalid JSON")

    raw = result.get("grades")
    if not isinstance(raw, list) or len(raw) != len(chunks):
        raise RuntimeError(
            f"context judge grades sai độ dài: {len(raw) if isinstance(raw, list) else raw!r}"
            f" != {len(chunks)} chunk"
        )
    grades = [_grade(g, "grade") for g in raw]

    return {
        "context_relevance": round(sum(grades) / len(grades), 4),
        "context_precision": round(
            sum(1 for g in grades if g >= RELEVANT_THRESHOLD) / len(grades), 4),
        "context_sufficiency": _grade(result.get("sufficiency"), "sufficiency"),
        "ranking_quality": _ndcg(grades),
        "groundedness": (_grade(result.get("groundedness"), "groundedness")
                         if answer else None),
        "details": {
            "grades": grades,
            "n_chunks": len(grades),
            "n_relevant": sum(1 for g in grades if g >= RELEVANT_THRESHOLD),
            "reason": str(result.get("reason") or ""),
        },
    }


def demo() -> None:
    assert _ndcg([5, 3, 1]) == 1.0                      # đã xếp đúng
    assert _ndcg([1, 3, 5]) < 1.0                       # xếp ngược thì thấp hơn
    assert _ndcg([0, 0, 0]) is None                     # không có gì liên quan
    assert _ndcg([]) is None

    class FakeJudge:
        seen = ""

        def judge(self, prompt: str) -> dict:
            FakeJudge.seen = prompt
            # Mọi bậc điểm phải có mốc neo — đó là lý do rubrics.py tồn tại.
            assert "Đoạn 1" in prompt
            for bin_ in "012345":
                assert f"\n  {bin_}  " in prompt, f"prompt thiếu neo bậc {bin_}"
            return {"grades": [5, 2, 0], "sufficiency": 4,
                    "groundedness": 3, "reason": "ok"}

    out = score(FakeJudge(), "mụn ở cằm?", ["a", "b", "c"], ["nội tiết"])
    assert out["context_relevance"] == round(7 / 3, 4)
    assert out["context_precision"] == round(1 / 3, 4)
    assert out["context_sufficiency"] == 4.0
    assert out["ranking_quality"] == 1.0                # 5,2,0 vốn đã giảm dần
    assert out["groundedness"] is None                  # không truyền answer
    assert "BÁM TÀI LIỆU" not in FakeJudge.seen         # không hỏi thì không nhắc

    out = score(FakeJudge(), "mụn ở cằm?", ["a", "b", "c"], answer="vì nội tiết")
    assert out["groundedness"] == 3.0
    assert "BÁM TÀI LIỆU" in FakeJudge.seen and "vì nội tiết" in FakeJudge.seen

    assert score(FakeJudge(), "q", [])["context_relevance"] is None

    for bad in ({"grades": [1, 2], "sufficiency": 3},          # sai độ dài
                {"grades": [1, 2, 9], "sufficiency": 3},       # ngoài thang
                {"grades": [1, 2, 3], "sufficiency": None}):   # thiếu
        try:
            score(type("J", (), {"judge": lambda s, p, b=bad: b})(), "q", ["a", "b", "c"])
        except RuntimeError:
            continue
        raise AssertionError(f"phải raise với {bad}")
    print("context judge demo OK")


if __name__ == "__main__":
    demo()
