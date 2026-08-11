"""Dựng bản ghi giả cho test, đi qua ĐÚNG `to_record` thật.

Không tự bịa `messages` bằng tay: nếu test dựng messages riêng thì nó sẽ không
bắt được lỗi "tài liệu không lọt vào messages" — chính là lỗi mà v2 sinh ra để sửa.
"""
from __future__ import annotations

from typing import Any

from ..generator import CaseSpec, load_taxonomy, to_record
from ..config import Config

ANCHOR = "ANCHOR-v3-test"

CONTEXT = [
    {
        "label": "Nguồn 1",
        "source_id": "chunk-test-1",
        "source_name": "Tài liệu mụn kiểm thử",
        "text": (
            "Benzoyl peroxide là hoạt chất không kê đơn thường dùng cho mụn viêm nhẹ "
            "đến trung bình, có tác dụng diệt khuẩn và giảm bít tắc lỗ chân lông."
        ),
    }
]


def case_by_id(case_id: str) -> CaseSpec:
    cfg = Config(api_key="offline-test")
    for case in load_taxonomy(cfg):
        if case.id == case_id:
            return case
    raise KeyError(case_id)


def make_record(
    case_id: str,
    answer: str,
    *,
    user: str = "Da mình bị mụn ở cằm, mình nên làm gì?",
    context: list[dict[str, str]] | None = None,
    points: list[str] | None = None,
    turns: list[dict[str, str]] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    case = case_by_id(case_id)
    return to_record(
        case,
        user,
        answer,
        ANCHOR,
        {
            "record_id": f"roledatav2-{case_id}-000001",
            "input_style": "standard",
            "turns": turns,
            "synthetic_context": context,
            "synthetic_context_sources": ["chunk-test-1"] if context else [],
            "generation_meta": meta or {},
            "gen_model": "test-model",
            "points": points or [],
            "len_target": sum(case.len_chars) // 2,
        },
    )


# Câu độn phải KHÁC NHAU: gate `phrase_frequency` của v1 chặn 14-gram lặp quá 8
# lần, nên văn bản độn lặp một câu sẽ bị loại và test hoá ra đo nhầm thứ khác.
_FILLERS = (
    "Bạn nên giữ thói quen rửa mặt dịu nhẹ hai lần mỗi ngày.",
    "Tránh chà xát mạnh vì dễ làm tổn thương hàng rào bảo vệ da.",
    "Chọn sản phẩm ghi rõ không gây bít tắc lỗ chân lông.",
    "Che chắn kỹ khi ra nắng để hạn chế vết thâm sau viêm.",
    "Ghi lại phản ứng của da trong vài tuần để theo dõi tiến triển.",
    "Nếu tình trạng nặng hơn hoặc lan rộng, hãy gặp bác sĩ da liễu.",
    "Không tự ý nặn vì nguy cơ nhiễm trùng và để lại sẹo rỗ.",
    "Giữ tóc và khăn mặt sạch để giảm ma sát lên vùng đang bị mụn.",
    "Uống đủ nước và ngủ đủ giấc cũng hỗ trợ quá trình phục hồi.",
    "Thay đổi sản phẩm từng bước một để biết thứ nào phù hợp.",
)


def answer_of_length(target: int, *, bullets: int = 0, salt: str = "") -> str:
    """Sinh câu trả lời tiếng Việt hợp lệ, dài xấp xỉ `target`, không lặp cụm dài."""
    head = f"Mình hiểu bạn đang lo về tình trạng da này{salt}. "
    if bullets:
        lines = [
            f"- Ý số {index}: {_FILLERS[index % len(_FILLERS)]}"
            for index in range(1, bullets + 1)
        ]
        head += "\n" + "\n".join(lines) + "\n"
    index = 0
    while len(head) < target:
        head += f"{_FILLERS[index % len(_FILLERS)]} Lưu ý thứ {index + 1}. "
        index += 1
    return head[:target]


def points_for(bullets: int) -> list[str]:
    """`points` khớp đúng các bullet mà `answer_of_length` sinh ra.

    Suy ra từ cùng nguồn thay vì chép tay: đổi văn bản độn mà quên sửa points thì
    test sẽ đỏ vì lý do sai (points_covered) chứ không phải vì thứ đang đo.
    """
    return [f"Ý số {index}: {_FILLERS[index % len(_FILLERS)]}" for index in range(1, bullets + 1)]
