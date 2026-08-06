"""Neo cho `clinical.inflammation_level` — nhẹ / vừa / nặng nghĩa là gì.

Vì sao file này tồn tại: Modelfile liệt kê bốn giá trị enum mà KHÔNG định nghĩa
bậc nào là bậc nào. Người gán nhãn đoán một kiểu, model đoán một kiểu, rồi
`clinical.inflammation_level` accuracy 0.9105 được đem đi báo cáo mà không ai
nói được nó đo cái gì. (Thêm nữa: 85,5% nhãn trong tập val là None/unknown, nên
con số đó chủ yếu đo "biết im lặng khi người dùng không khai mức độ".)

═══ CHỌN THANG NÀO, VÀ VÌ SAO ═══

[1] AAD, "Guidelines of care for the management of acne vulgaris", JAAD 2024.
    https://www.jaad.org/article/S0190-9622(23)03389-3/pdf
    AAD khuyến nghị dùng IGA (Investigator's Global Assessment) hoặc công cụ
    tương đương: 5 bậc thứ tự 0-4 — 0 sạch · 1 gần sạch · 2 nhẹ · 3 vừa · 4 nặng.
    AAD KHÔNG đưa ra thang đếm số tổn thương.

[2] Các thang ĐẾM tổn thương — GAGS (mild 1-18, moderate 19-30, severe 31-38),
    Hayashi (mild 0-5, moderate 6-20, severe 21-50 nốt viêm nửa mặt), BASI
    (mild 1-10, moderate 11-20, severe >20) — là của nhóm tác giả khác.
    https://ijdvl.com/scoring-systems-in-acne-vulgaris/
    KHÔNG dùng được ở đây: đầu vào của ta là câu chat tự do tiếng Việt
    ("em bị mụn nhiều lắm ở hai bên má"), không có con số nào để đếm. Ép model
    suy ra "21-50 nốt" từ chữ "nhiều lắm" là dạy nó bịa.

[3] Nodule định nghĩa là tổn thương viêm, chắc, >5 mm (có tài liệu lấy mốc
    10 mm) — theo chunk `clinical_textbook` trong chính KB của dự án.
    Đây là ranh giới khách quan duy nhất ta có, nên nó là chốt của bậc `severe`.

=> Ta dùng IGA, thu về đúng 4 giá trị enum sẵn có. Neo bằng LOẠI tổn thương và
   MỨC LAN, không bằng số đếm.

═══ ĐIỀU KHUNG NÀY CỐ Ý KHÔNG LÀM ═══

IGA gốc là thang của bác sĩ NHÌN da. Ta suy ra từ lời người dùng TỰ KHAI, nên
đây là "IGA suy đoán từ mô tả", không phải IGA thật. Khác biệt đó có thật và
phải ghi trong khóa luận: nhãn của ta đo mức độ mà lời kể GỢI RA, không đo mức
độ lâm sàng. Không có ảnh thì không đóng được khoảng cách này.

Hệ quả bắt buộc: mô tả không đủ tín hiệu -> `unknown`, KHÔNG đoán. Đoán bừa ở
đây nguy hiểm thật sự — hạ một ca nặng xuống `mild` là bỏ lỡ chỉ định đi khám.
"""
from __future__ import annotations

# Bậc -> (neo IGA, dấu hiệu trong lời kể). Thứ tự = thứ tự thang, đừng xáo.
LEVELS: dict[str, str] = {
    "none": (
        "IGA 0-1 (sạch / gần sạch). Không còn tổn thương đang hoạt động; chỉ còn "
        "thâm, sẹo, hoặc lỗ chân lông to. Người hỏi nói kiểu 'hết mụn rồi nhưng "
        "còn thâm'."
    ),
    "mild": (
        "IGA 2. Chủ yếu nhân trứng cá (đầu đen, đầu trắng), lác đác vài sẩn hoặc "
        "mụn mủ nhỏ. Khu trú một vùng. KHÔNG có nốt cục, KHÔNG đau, KHÔNG để lại "
        "sẹo. Người hỏi nói 'thỉnh thoảng vài nốt', 'mụn ẩn ở trán'."
    ),
    "moderate": (
        "IGA 3. Nhiều sẩn và mụn mủ viêm rõ, lan hơn một vùng mặt, hoặc kéo dài "
        "dai dẳng. Có thể vài nốt cục nhưng không phải nét chính. Người hỏi nói "
        "'mụn viêm đỏ khắp hai má', 'mọc liên tục mấy tháng không hết'."
    ),
    "severe": (
        "IGA 4. Có BẤT KỲ dấu hiệu nào sau đây thì lên thẳng severe, không cần "
        "đủ cả: nốt cục hoặc nang (tổn thương chắc, sâu, >5 mm); đau "
        "khi chạm; đang để lại sẹo; lan xuống lưng/ngực/vai; hoặc đã thất bại "
        "với điều trị bôi. Người hỏi nói 'mụn bọc to đau', 'nặn xong thành sẹo "
        "lõm', 'mọc cả lưng'."
    ),
    "unknown": (
        "Lời kể KHÔNG đủ tín hiệu để xếp bậc. Đây là giá trị MẶC ĐỊNH, không "
        "phải giá trị dự phòng cuối cùng — không suy đoán từ tuổi, giới, loại da "
        "hay thời gian bị. Chỉ nói 'em bị mụn' thì là unknown."
    ),
}

# Xuất hiện nguyên văn trong Modelfile của intaker. `test_severity_anchor.py`
# chặn hai bên trôi khỏi nhau — trôi thì nhãn và model chấm theo hai thang khác
# nhau mà không ai biết.
MODELFILE_ANCHOR = (
    "- inflammation_level neo theo IGA (AAD 2024), suy từ LOẠI tổn thương và "
    "MỨC LAN, không đếm số nốt:\n"
    + "\n".join(f"  - {level}: {text}" for level, text in LEVELS.items())
)

# Bậc mà đoán sai gây hại một chiều: hạ xuống là bỏ lỡ chỉ định đi khám.
# Dùng cho báo cáo lỗi có hướng ở run_intake.
CRITICAL_LEVEL = "severe"
ORDER = ("none", "mild", "moderate", "severe")


def is_downgrade(gold: str | None, pred: str | None) -> bool:
    """Đoán NHẸ hơn thực tế — loại sai nguy hiểm, cần đếm riêng.

    `unknown` không nằm trên thang nên không tính là hạ bậc: nói 'tôi không rõ'
    khác hẳn nói 'nhẹ thôi'.
    """
    if gold not in ORDER or pred not in ORDER:
        return False
    return ORDER.index(pred) < ORDER.index(gold)


def demo() -> None:
    assert set(LEVELS) == {"none", "mild", "moderate", "severe", "unknown"}
    # Mọi bậc phải neo vào IGA hoặc nói rõ vì sao không.
    for level, text in LEVELS.items():
        assert "IGA" in text or level == "unknown", f"{level} thiếu neo IGA"
    # Chốt khách quan duy nhất phải còn trong bậc severe.
    assert ">5 mm" in LEVELS["severe"]
    assert ">5 mm" not in LEVELS["moderate"], "mốc nodule chỉ được chốt ở severe"
    # Trích dẫn phải còn — mất trích dẫn là mất khả năng bảo vệ trước hội đồng.
    assert "JAAD 2024" in __doc__ and "GAGS" in __doc__

    assert is_downgrade("severe", "mild") is True
    assert is_downgrade("mild", "severe") is False        # nâng bậc: thừa, không nguy
    assert is_downgrade("severe", "unknown") is False     # 'không rõ' ≠ 'nhẹ'
    assert is_downgrade("severe", "severe") is False
    assert is_downgrade(None, "mild") is False

    assert MODELFILE_ANCHOR.startswith("- inflammation_level neo theo IGA")
    assert all(level in MODELFILE_ANCHOR for level in LEVELS)
    print("severity demo OK — 5 bậc, neo IGA/AAD 2024")


if __name__ == "__main__":
    demo()
