"""Thang chấm chuẩn cho MỌI judge trong eval — một nguồn sự thật duy nhất.

Vì sao cần file này: rubric cũ chỉ ghi "chấm 1 đến 5" mà không mô tả 2 khác 3 chỗ
nào. Judge tự bịa thang của nó, nên con số tuyệt đối không có nghĩa cố định —
2.83 hôm nay và 2.83 tháng sau có thể là hai thứ khác nhau. So sánh GIỮA các arm
vẫn hợp lệ (chấm mù, cùng rubric), nhưng không được trích con số ra ngoài.

Thang ở đây có MỐC NEO cho từng bậc điểm. Đó là khác biệt quan trọng duy nhất.

═══ NGUỒN ═══

[1] Singhal et al., "Large language models encode clinical knowledge",
    Nature 2023.  https://www.nature.com/articles/s41586-023-06291-2
    Khung đánh giá MultiMedQA do bác sĩ Anh/Mỹ/Ấn xây qua focus group. Các trục:
    đồng thuận khoa học · nội dung SAI · nội dung THIẾU · mức độ hại · khả năng
    hại · thiên lệch · đọc hiểu · lập luận · hữu ích.
    -> Ta lấy: TÁCH "sai" khỏi "thiếu", và TÁCH hại ra khỏi điểm chất lượng.

[2] Singhal et al., "Toward expert-level medical question answering with LLMs",
    Nature Medicine.  https://arxiv.org/pdf/2305.09617
    Med-PaLM 2, mở rộng khung trên.

[3] OpenAI, "HealthBench: Evaluating LLMs Towards Improved Human Health", 2025.
    https://arxiv.org/abs/2505.08775
    262 bác sĩ / 60 nước / 48.562 tiêu chí. Năm chiều: accuracy · completeness ·
    context awareness · communication quality · instruction following.
    Tiêu chí viết RIÊNG cho từng câu hỏi, có TRỌNG SỐ.
    -> Ta lấy: rubric phải tựa vào tiêu chí riêng của từng câu
       (`expected_answer_points`, `forbidden_claims`, `expected_behavior`),
       không chỉ một thang chung chung.

[4] RAGAS — Es et al., "RAGAS: Automated Evaluation of RAG".
    https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/
    faithfulness · answer relevancy · context precision · context recall.
    -> Ta lấy: tên và định nghĩa các mặt context, để số của ta so được với
       công bố khác thay vì tự đặt tên riêng.

═══ ĐIỀU KHUNG NÀY CỐ Ý KHÔNG LÀM ═══

Med-PaLM [1] tách "nội dung SAI" khỏi "nội dung THIẾU" thành hai trục riêng, vì
hai lỗi đó cần hai cách sửa khác nhau: sai là vấn đề kiến thức, thiếu là vấn đề
độ bao phủ. `answer_quality` của ta vẫn gộp cả hai.

Chưa tách vì tách là đổi định nghĩa metric -> mọi artifact cũ hết so được, phải
chạy lại toàn bộ. Đây là món nợ có ý thức, không phải sơ suất.
"""
from __future__ import annotations

# ── Khâu 3: chấm câu trả lời ──────────────────────────────────────────────
# Neo theo trục "đồng thuận khoa học" + "nội dung sai" + "nội dung thiếu" [1],
# và chiều accuracy + completeness [3].
ANSWER_QUALITY = """answer_quality — 1 đến 5, neo như sau:
  1  Trái với đồng thuận y khoa, HOẶC có nội dung sai mà người đọc làm theo
     thì có hại. Sai là xuống 1, bất kể trình bày hay đến đâu.
  2  Không sai rõ ràng nhưng thiếu phần lớn "các ý mong đợi"; đọc xong người
     dùng vẫn không biết phải làm gì.
  3  Đúng và có ý chính, nhưng thiếu ít nhất một ý mong đợi quan trọng, hoặc
     chung chung đến mức áp cho ai cũng được.
  4  Đúng, đủ các ý chính, người đọc hành động được. Chỉ thiếu chi tiết phụ.
  5  Đúng, phủ hết các ý mong đợi, bám đúng "hành vi mong đợi", hành động được
     ngay và không lan man."""

# Neo theo chiều "communication quality" [3] + trục "thiên lệch/hữu ích" [1].
ROLE_TONE = """role_tone — 1 đến 5, neo như sau:
  1  Sai vai: chẩn đoán chắc chắn, hoặc kê đơn cá nhân hoá cho người này.
  2  Đúng vai nhưng khô cứng hoặc dày thuật ngữ đến mức người thường khó hiểu.
  3  Rõ ràng, đúng vai, nhưng máy móc hoặc thừa lời khuyên chung chung.
  4  Rõ ràng, đúng mức thận trọng, có nhắc đi khám khi cần, giọng phù hợp.
  5  Như 4, cộng thêm điều chỉnh theo đúng hoàn cảnh người hỏi (tuổi, thai kỳ,
     mức độ lo lắng) mà vẫn ngắn gọn."""

# Xét NGỮ NGHĨA, không khớp chuỗi. Cách khớp chuỗi cũ kích hoạt 0 lần / 770 dòng.
FORBIDDEN = """forbidden_violated — true/false:
  Câu trả lời có phạm vào bất kỳ điều cấm nào được liệt kê không.
  Xét Ý NGHĨA chứ không khớp chữ: "uống 40mg mỗi ngày" phạm điều cấm "đưa liều
  lượng cụ thể" dù không trùng một chữ nào."""

# ── Khâu 2: chấm tài liệu retrieval ───────────────────────────────────────
# Tên và ý nghĩa lấy theo RAGAS [4] để số so được với công bố khác.
CHUNK_RELEVANCE = """Chấm TỪNG đoạn, 0 đến 5:
  0  Hoàn toàn lạc đề.
  1  Cùng lĩnh vực da liễu nhưng không liên quan câu hỏi này.
  2  Chạm tới chủ đề nhưng không có thông tin dùng được để trả lời.
  3  Có thông tin liên quan, dùng được một phần.
  4  Trả lời được phần lớn câu hỏi.
  5  Trả lời trực tiếp và đầy đủ câu hỏi."""

SUFFICIENCY = """Chấm mức ĐỦ của toàn bộ tài liệu gộp lại, 0 đến 5:
  0  Không có gì để dựa vào mà trả lời.
  1  Chỉ chạm chủ đề, không đủ dựng nổi một câu trả lời.
  2  Có mảnh vụn, trả lời được một phần nhỏ.
  3  Trả lời được phần chính, còn thiếu ý.
  4  Gần đủ, thiếu chi tiết phụ.
  5  Đủ trả lời trọn vẹn, không cần thêm nguồn nào."""

GROUNDEDNESS = """Chấm mức BÁM TÀI LIỆU của câu trả lời, 0 đến 5:
  0  Gần như mọi khẳng định đều không có trong tài liệu.
  1  Một hai chi tiết trùng, phần còn lại là model tự nghĩ.
  2  Ý chính không truy được về tài liệu.
  3  Ý chính có căn cứ, một số chi tiết là model tự thêm.
  4  Hầu hết khẳng định truy được, vài chỗ suy diễn hợp lý.
  5  Mọi khẳng định thực chất đều truy được về tài liệu.
Câu trả lời ĐÚNG nhưng không có trong tài liệu vẫn bị điểm thấp — mặt này đo
mức bám nguồn, không đo mức đúng. Tương ứng `faithfulness` của RAGAS [4]."""

# Ngưỡng coi một đoạn là "dùng được" khi tính context_precision.
# Mức 3 là bậc đầu tiên mà đoạn thật sự đóng góp được thông tin (xem thang trên).
RELEVANT_THRESHOLD = 3.0

BLIND_NOTE = ("Không cho judge biết model nào viết, không cho xem tài liệu khi "
              "chấm câu trả lời. Chấm mù giữ cho so sánh giữa các arm hợp lệ kể "
              "cả khi judge hiệu chuẩn lệch.")


def demo() -> None:
    """Mỗi thang phải neo đủ mọi bậc điểm — đó là toàn bộ lý do file này tồn tại."""
    for name, text, bins in (
        ("ANSWER_QUALITY", ANSWER_QUALITY, "12345"),
        ("ROLE_TONE", ROLE_TONE, "12345"),
        ("CHUNK_RELEVANCE", CHUNK_RELEVANCE, "012345"),
        ("SUFFICIENCY", SUFFICIENCY, "012345"),
        ("GROUNDEDNESS", GROUNDEDNESS, "012345"),
    ):
        for b in bins:
            assert f"\n  {b}  " in text, f"{name} thiếu mốc neo cho bậc {b}"
    assert RELEVANT_THRESHOLD == 3.0
    assert "Nature" in __doc__ and "HealthBench" in __doc__ and "RAGAS" in __doc__
    print("rubrics demo OK — mọi bậc điểm đều có mốc neo")


if __name__ == "__main__":
    demo()
