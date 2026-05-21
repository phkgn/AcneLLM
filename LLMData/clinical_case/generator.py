"""Generate a clean clinical-case fine-tuning JSONL dataset.

The generated records teach the model to turn free-form acne descriptions into
structured clinical JSON. They are curated templates, not converted chunk_qa
records, so unsafe medication examples can be controlled before validation.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from acne_llm.schemas.clinical import NormalizedAcneCase

from .schema import (
    ClinicalCaseRecommendation,
    ClinicalCaseTrainingOutput,
    GuidelineAlignment,
)
from .validator import validate_file


SYSTEM_PROMPT = (
    "Bạn là AcneLLM clinical structuring model. "
    "Nhiệm vụ: chuẩn hóa mô tả mụn tự do thành JSON đúng schema, phân tầng mức độ "
    "thận trọng, khuyến nghị an toàn bám AAD 2024 và NICE NG198. "
    "Không kê đơn, không đưa liều/nồng độ/tần suất thuốc kê đơn."
)


_BASE_UNKNOWN = {
    "normalized_case": {
        "demographics": {
            "age": None,
            "sex": "unknown",
            "skin_type": "unknown",
            "is_pregnant": False,
            "is_breastfeeding": False,
        },
        "lesion_types": [],
        "distribution": [],
        "inflammation_level": "unknown",
        "scarring_signs": [],
        "medication_history": [],
        "hormonal_factors": [],
        "skincare_products": [],
        "treatment_goals": [],
        "red_flags": [],
        "missing_info": [
            "age",
            "lesion_types",
            "distribution",
            "duration",
            "scarring_signs",
            "pregnancy_or_breastfeeding",
            "medication_history",
        ],
    },
    "severity": "unknown",
    "severity_rationale": (
        "Mô tả chưa đủ dữ kiện về loại tổn thương, phân bố, thời gian và dấu hiệu sẹo; "
        "không nên chẩn đoán chắc hoặc cá thể hóa phác đồ."
    ),
    "recommendations": [
        {
            "category": "safety",
            "action": (
                "Hỏi thêm tuổi, vị trí mụn, loại tổn thương, thời gian kéo dài, "
                "sẹo/thâm, thuốc đã dùng và tình trạng mang thai/cho con bú trước khi tư vấn sâu."
            ),
            "rationale": "AAD 2024 và NICE NG198 đều nhấn mạnh đánh giá đầy đủ trước khi chọn hướng xử trí.",
            "guideline_refs": ["AAD_2024", "NICE_NG198"],
        },
        {
            "category": "skincare",
            "action": (
                "Trong lúc thiếu dữ kiện, chỉ nên chăm sóc da dịu nhẹ, tránh nặn mụn "
                "và tránh phối nhiều hoạt chất mạnh."
            ),
            "rationale": "Gợi ý rủi ro thấp phù hợp khi severity còn unknown.",
            "guideline_refs": ["NICE_NG198"],
        },
    ],
    "red_flags": [],
    "guideline_alignment": {
        "status": "insufficient_info",
        "refs": ["AAD_2024", "NICE_NG198"],
        "notes": "Bám guideline ở mức hỏi thêm thông tin và giới hạn tư vấn an toàn do thiếu dữ kiện.",
    },
    "safety_flags": ["insufficient_information", "no_prescription_or_dose"],
    "confidence": 0.35,
}


CASE_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "mild_comedonal_tzone_teen",
        "user": "Em 17 tuổi, da dầu, trán và mũi nhiều mụn đầu đen với mụn ẩn, ít đỏ, không đau.",
        "normalized_case": {
            "demographics": {"age": 17, "sex": "unknown", "skin_type": "oily"},
            "lesion_types": ["blackhead", "closed_comedone", "comedone"],
            "distribution": ["forehead", "nose", "t_zone"],
            "inflammation_level": "mild",
            "treatment_goals": ["giảm nhân mụn", "giảm bóng dầu"],
            "missing_info": ["duration", "medication_history", "scarring_signs"],
        },
        "severity": "mild",
        "severity_rationale": "Chủ yếu là nhân mụn không viêm ở vùng chữ T, ít viêm và không có dấu hiệu nốt sâu hoặc sẹo.",
        "recommendations": [
            {
                "category": "skincare",
                "action": "Duy trì rửa mặt dịu nhẹ, dưỡng ẩm không gây bít tắc, chống nắng và tránh nặn mụn.",
                "rationale": "Mụn nhẹ có thể bắt đầu bằng chăm sóc da nền và theo dõi đáp ứng.",
                "guideline_refs": ["NICE_NG198"],
            },
            {
                "category": "otc_info",
                "action": "Có thể tìm hiểu hoạt chất không kê đơn như benzoyl peroxide hoặc salicylic acid ở mức thông tin chung.",
                "rationale": "AAD 2024 nhắc đến các lựa chọn bôi tại chỗ, nhưng chatbot không cá thể hóa liều/nồng độ.",
                "guideline_refs": ["AAD_2024"],
            },
        ],
        "guideline_alignment": {"status": "aligned", "notes": "Khuyến nghị mức thấp, không kê đơn và phù hợp mụn nhẹ."},
        "safety_flags": ["no_prescription_or_dose"],
        "confidence": 0.78,
    },
    {
        "id": "moderate_papulopustular_face",
        "user": "Mặt em nổi nhiều mụn đỏ và mụn mủ hai bên má gần 4 tháng, dùng sữa rửa mặt trị mụn nhưng không đỡ.",
        "normalized_case": {
            "lesion_types": ["papule", "pustule"],
            "distribution": ["cheeks"],
            "inflammation_level": "moderate",
            "medication_history": ["sữa rửa mặt trị mụn"],
            "treatment_goals": ["giảm viêm", "kiểm soát mụn kéo dài"],
            "missing_info": ["age", "pregnancy_or_breastfeeding", "scarring_signs"],
        },
        "severity": "moderate",
        "severity_rationale": "Nhiều tổn thương viêm dạng sẩn và mụn mủ, kéo dài nhiều tháng nhưng chưa ghi nhận nodule/cyst hoặc sẹo.",
        "recommendations": [
            {
                "category": "see_doctor",
                "action": "Nên khám bác sĩ da liễu nếu mụn viêm nhiều, kéo dài hoặc không đáp ứng chăm sóc ban đầu.",
                "rationale": "Mụn viêm vừa có thể cần đánh giá trực tiếp để chọn phác đồ phù hợp và giảm nguy cơ sẹo.",
                "guideline_refs": ["AAD_2024", "NICE_NG198"],
            },
            {
                "category": "safety",
                "action": "Không tự mua kháng sinh hoặc thuốc kê đơn để trị mụn.",
                "rationale": "Guideline nhấn mạnh antimicrobial stewardship và tránh tự dùng thuốc.",
                "guideline_refs": ["AAD_2024", "NICE_NG198"],
            },
        ],
        "guideline_alignment": {"status": "aligned", "notes": "Phân tầng vừa và khuyên khám khi mụn viêm kéo dài, không kê thuốc."},
        "safety_flags": ["antibiotic_stewardship", "no_prescription_or_dose"],
        "confidence": 0.76,
    },
    {
        "id": "severe_nodules_scarring",
        "user": "Tôi có mụn bọc đau ở cằm và quai hàm, vài nốt to dưới da, có sẹo lõm mới xuất hiện.",
        "normalized_case": {
            "lesion_types": ["nodule", "cyst", "scar"],
            "distribution": ["chin", "jawline"],
            "inflammation_level": "severe",
            "scarring_signs": ["sẹo lõm mới"],
            "red_flags": ["painful_deep_lesions", "scarring_risk"],
            "treatment_goals": ["giảm đau", "ngừa sẹo"],
            "missing_info": ["age", "duration", "medication_history", "pregnancy_or_breastfeeding"],
        },
        "severity": "severe",
        "severity_rationale": "Có nốt sâu đau, mụn bọc/nang và sẹo mới, đây là nhóm nguy cơ sẹo vĩnh viễn nên phân tầng nặng.",
        "recommendations": [
            {
                "category": "see_doctor",
                "action": "Nên gặp bác sĩ da liễu sớm để đánh giá trực tiếp và kiểm soát nguy cơ sẹo.",
                "rationale": "AAD 2024 và NICE NG198 đều coi mụn nặng, nốt sâu hoặc sẹo là lý do cần đánh giá y khoa.",
                "guideline_refs": ["AAD_2024", "NICE_NG198"],
            },
            {
                "category": "safety",
                "action": "Không tự nặn mụn bọc, không tự peel/lăn kim tại nhà và không tự dùng thuốc kê đơn.",
                "rationale": "Tự can thiệp có thể làm viêm nặng hơn và tăng nguy cơ sẹo.",
                "guideline_refs": ["NICE_NG198"],
            },
        ],
        "red_flags": ["painful_deep_lesions", "scarring_risk"],
        "guideline_alignment": {"status": "aligned", "notes": "Bám referral trigger cho mụn nặng và sẹo."},
        "safety_flags": ["urgent_dermatology_referral", "no_self_procedure", "no_prescription_or_dose"],
        "confidence": 0.88,
    },
    {
        "id": "pregnancy_acne_safety",
        "user": "Em đang mang thai 10 tuần, nổi mụn viêm quanh cằm, muốn dùng thuốc trị mụn cho nhanh hết.",
        "normalized_case": {
            "demographics": {"sex": "female", "is_pregnant": True},
            "lesion_types": ["papule"],
            "distribution": ["chin", "around_mouth"],
            "inflammation_level": "moderate",
            "hormonal_factors": ["pregnancy"],
            "treatment_goals": ["điều trị an toàn khi mang thai"],
            "red_flags": ["pregnancy"],
            "missing_info": ["age", "duration", "current_medications", "scarring_signs"],
        },
        "severity": "moderate",
        "severity_rationale": "Có mụn viêm mức vừa theo mô tả, đồng thời mang thai là yếu tố an toàn cần ưu tiên.",
        "recommendations": [
            {
                "category": "see_doctor",
                "action": "Nên hỏi bác sĩ da liễu hoặc bác sĩ sản khoa trước khi dùng bất kỳ thuốc trị mụn nào.",
                "rationale": "Thai kỳ cần đánh giá cá nhân hóa để tránh thuốc không phù hợp.",
                "guideline_refs": ["AAD_2024", "NICE_NG198"],
            },
            {
                "category": "skincare",
                "action": "Có thể giữ chăm sóc da dịu nhẹ, dưỡng ẩm, chống nắng và tránh nặn mụn trong lúc chờ tư vấn y khoa.",
                "rationale": "Đây là hướng rủi ro thấp, không thay thế đánh giá của bác sĩ.",
                "guideline_refs": ["NICE_NG198"],
            },
        ],
        "red_flags": ["pregnancy"],
        "guideline_alignment": {"status": "aligned", "notes": "Ưu tiên an toàn thai kỳ và không nêu thuốc/liều cụ thể."},
        "safety_flags": ["pregnancy_safety", "no_prescription_or_dose"],
        "confidence": 0.82,
    },
    {
        "id": "breastfeeding_sensitive_skin",
        "user": "Mình đang cho bé bú, da nhạy cảm, gần đây có mụn đỏ lấm tấm hai má và hơi rát sau khi dùng serum acid.",
        "normalized_case": {
            "demographics": {"sex": "female", "skin_type": "sensitive", "is_breastfeeding": True},
            "lesion_types": ["papule"],
            "distribution": ["cheeks"],
            "inflammation_level": "mild",
            "skincare_products": ["serum acid"],
            "red_flags": ["breastfeeding", "irritation"],
            "missing_info": ["age", "duration", "exact_product", "scarring_signs"],
        },
        "severity": "mild",
        "severity_rationale": "Tổn thương viêm nhẹ nhưng có kích ứng và đang cho con bú, nên tư vấn bảo thủ.",
        "recommendations": [
            {
                "category": "safety",
                "action": "Tạm ngưng sản phẩm gây rát, phục hồi hàng rào da và trao đổi với bác sĩ nếu cần dùng thuốc trị mụn.",
                "rationale": "Kích ứng sau hoạt chất chăm sóc da nên giảm phơi nhiễm trước, đặc biệt khi cho con bú.",
                "guideline_refs": ["NICE_NG198"],
            },
            {
                "category": "skincare",
                "action": "Ưu tiên sữa rửa mặt dịu nhẹ, dưỡng ẩm không gây bít tắc và chống nắng phù hợp.",
                "rationale": "Chăm sóc da nền giúp giảm kích ứng và là hướng an toàn chung.",
                "guideline_refs": ["NICE_NG198"],
            },
        ],
        "red_flags": ["breastfeeding", "irritation"],
        "guideline_alignment": {"status": "aligned", "notes": "Không cá thể hóa thuốc trong bối cảnh cho con bú."},
        "safety_flags": ["breastfeeding_safety", "irritation_risk", "no_prescription_or_dose"],
        "confidence": 0.74,
    },
    {
        "id": "unknown_short_question",
        "user": "Mặt em nổi mụn quá, giờ xử lý sao?",
        **_BASE_UNKNOWN,
    },
    {
        "id": "self_antibiotic_request",
        "user": "Em muốn mua kháng sinh uống trị mụn viêm, nên mua loại nào?",
        "normalized_case": {
            "lesion_types": ["papule", "pustule"],
            "inflammation_level": "moderate",
            "treatment_goals": ["xin tên thuốc kháng sinh"],
            "red_flags": ["requests_antibiotic_self_use"],
            "missing_info": ["age", "distribution", "duration", "pregnancy_or_breastfeeding", "scarring_signs"],
        },
        "severity": "unknown",
        "severity_rationale": "Có mô tả mụn viêm nhưng thiếu phân bố, số lượng, thời gian và dấu hiệu sẹo; trọng tâm là yêu cầu tự dùng thuốc.",
        "recommendations": [
            {
                "category": "prescription_boundary",
                "action": "Không nên tự mua kháng sinh trị mụn; cần bác sĩ da liễu đánh giá nếu mụn viêm nhiều hoặc kéo dài.",
                "rationale": "AAD 2024 và NICE NG198 nhấn mạnh tránh tự dùng kháng sinh và tránh dùng không phù hợp.",
                "guideline_refs": ["AAD_2024", "NICE_NG198"],
            },
            {
                "category": "safety",
                "action": "Cần cung cấp thêm tuổi, vị trí mụn, mức độ đau, sẹo và thuốc đã dùng để phân tầng an toàn.",
                "rationale": "Thiếu dữ kiện nên không cá thể hóa điều trị.",
                "guideline_refs": ["NICE_NG198"],
            },
        ],
        "red_flags": ["requests_antibiotic_self_use"],
        "guideline_alignment": {"status": "aligned", "notes": "Từ chối tự dùng thuốc và chuyển sang đánh giá an toàn."},
        "safety_flags": ["antibiotic_stewardship", "no_prescription_or_dose"],
        "confidence": 0.72,
    },
    {
        "id": "isotretinoin_request",
        "user": "Mụn bọc của em nặng, em nghe isotretinoin hết nhanh, có nên tự uống không?",
        "normalized_case": {
            "lesion_types": ["nodule", "cyst"],
            "inflammation_level": "severe",
            "red_flags": ["severe_acne", "requests_isotretinoin_self_use"],
            "treatment_goals": ["hỏi tự dùng thuốc kê đơn"],
            "missing_info": ["age", "distribution", "scarring_signs", "pregnancy_or_breastfeeding", "medication_history"],
        },
        "severity": "severe",
        "severity_rationale": "Người dùng mô tả mụn bọc nặng và hỏi tự dùng thuốc kê đơn, cần xử trí an toàn như mụn nặng.",
        "recommendations": [
            {
                "category": "see_doctor",
                "action": "Không tự uống isotretinoin; nên khám bác sĩ da liễu để đánh giá mụn nặng và nguy cơ sẹo.",
                "rationale": "Đây là thuốc kê đơn cần theo dõi y khoa, không phù hợp để tự bắt đầu qua chatbot.",
                "guideline_refs": ["AAD_2024", "NICE_NG198"],
            },
            {
                "category": "safety",
                "action": "Không tự chỉnh thuốc, không mua thuốc theo lời truyền miệng và báo bác sĩ các thuốc/sản phẩm đang dùng.",
                "rationale": "Giảm nguy cơ tác dụng phụ và tương tác không được đánh giá.",
                "guideline_refs": ["AAD_2024"],
            },
        ],
        "red_flags": ["severe_acne", "requests_isotretinoin_self_use"],
        "guideline_alignment": {"status": "aligned", "notes": "Đúng boundary với thuốc kê đơn và referral cho mụn nặng."},
        "safety_flags": ["urgent_dermatology_referral", "no_prescription_or_dose"],
        "confidence": 0.84,
    },
    {
        "id": "hormonal_jawline_adult_female",
        "user": "Mình 28 tuổi, nữ, cứ gần kỳ kinh là nổi mụn viêm quanh cằm và quai hàm, vài tháng nay tái đi tái lại.",
        "normalized_case": {
            "demographics": {"age": 28, "sex": "female"},
            "lesion_types": ["papule", "pustule"],
            "distribution": ["chin", "jawline"],
            "inflammation_level": "moderate",
            "hormonal_factors": ["menstrual_flare", "adult_female_acne_pattern"],
            "treatment_goals": ["giảm tái phát theo chu kỳ"],
            "missing_info": ["pregnancy_or_breastfeeding", "medication_history", "scarring_signs"],
        },
        "severity": "moderate",
        "severity_rationale": "Mụn viêm tái phát theo chu kỳ ở cằm/quai hàm gợi ý yếu tố nội tiết, mức vừa theo mô tả.",
        "recommendations": [
            {
                "category": "see_doctor",
                "action": "Nên khám bác sĩ da liễu nếu mụn tái phát nhiều tháng hoặc nghi liên quan nội tiết.",
                "rationale": "Cần đánh giá tiền sử, chống chỉ định và mục tiêu điều trị trước khi cân nhắc thuốc.",
                "guideline_refs": ["AAD_2024"],
            },
            {
                "category": "safety",
                "action": "Trước khi dùng thuốc, cần làm rõ khả năng mang thai, thuốc đang dùng và bệnh nền.",
                "rationale": "Các lựa chọn điều trị nội tiết cần đánh giá cá nhân hóa.",
                "guideline_refs": ["AAD_2024", "NICE_NG198"],
            },
        ],
        "guideline_alignment": {"status": "aligned", "notes": "Nhận diện yếu tố nội tiết nhưng không kê thuốc."},
        "safety_flags": ["hormonal_factor_present", "no_prescription_or_dose"],
        "confidence": 0.78,
    },
    {
        "id": "back_chest_inflammatory",
        "user": "Lưng và ngực mình nhiều mụn đỏ, có mụn mủ, mặc áo là đau rát, kéo dài hơn nửa năm.",
        "normalized_case": {
            "lesion_types": ["papule", "pustule"],
            "distribution": ["back", "chest"],
            "inflammation_level": "moderate",
            "red_flags": ["pain", "persistent_acne"],
            "treatment_goals": ["giảm đau rát", "giảm mụn thân mình"],
            "missing_info": ["age", "scarring_signs", "medication_history", "pregnancy_or_breastfeeding"],
        },
        "severity": "moderate",
        "severity_rationale": "Mụn viêm ở thân mình, kéo dài và đau rát, nhưng chưa mô tả nodule/cyst hay sẹo rõ.",
        "recommendations": [
            {
                "category": "see_doctor",
                "action": "Nên khám bác sĩ da liễu vì mụn viêm thân mình kéo dài và gây đau.",
                "rationale": "Mụn ở lưng/ngực có thể khó kiểm soát bằng chăm sóc đơn giản và có nguy cơ sẹo.",
                "guideline_refs": ["NICE_NG198", "AAD_2024"],
            },
            {
                "category": "skincare",
                "action": "Tránh ma sát mạnh, thay áo ẩm mồ hôi sớm và không cạy nặn tổn thương.",
                "rationale": "Giảm kích thích cơ học và nguy cơ viêm thêm.",
                "guideline_refs": ["NICE_NG198"],
            },
        ],
        "red_flags": ["pain", "persistent_acne"],
        "guideline_alignment": {"status": "aligned", "notes": "Khuyến nghị khám do kéo dài, đau và lan thân mình."},
        "safety_flags": ["no_prescription_or_dose"],
        "confidence": 0.77,
    },
    {
        "id": "skin_barrier_irritation",
        "user": "Em dùng BHA, retinol và benzoyl peroxide cùng lúc, giờ da bong tróc rát và mụn đỏ hơn.",
        "normalized_case": {
            "lesion_types": ["papule"],
            "inflammation_level": "moderate",
            "skincare_products": ["BHA", "retinol", "benzoyl peroxide"],
            "red_flags": ["irritation", "overuse_actives"],
            "treatment_goals": ["giảm rát", "phục hồi da"],
            "missing_info": ["age", "distribution", "pregnancy_or_breastfeeding", "duration"],
        },
        "severity": "unknown",
        "severity_rationale": "Mô tả nổi bật là kích ứng do phối nhiều hoạt chất; chưa đủ dữ kiện để phân tầng mụn chính xác.",
        "recommendations": [
            {
                "category": "safety",
                "action": "Tạm dừng các sản phẩm gây rát, tối giản routine và ưu tiên phục hồi hàng rào da.",
                "rationale": "Kích ứng có thể làm đỏ rát và khiến mụn nhìn nặng hơn.",
                "guideline_refs": ["NICE_NG198"],
            },
            {
                "category": "see_doctor",
                "action": "Gặp bác sĩ nếu rát nhiều, sưng đau, chảy dịch hoặc mụn viêm lan nhanh.",
                "rationale": "Các dấu hiệu này cần đánh giá trực tiếp.",
                "guideline_refs": ["NICE_NG198"],
            },
        ],
        "red_flags": ["irritation", "overuse_actives"],
        "guideline_alignment": {"status": "partial", "notes": "Ưu tiên an toàn kích ứng; cần thêm dữ kiện để phân tầng acne."},
        "safety_flags": ["irritation_risk", "no_prescription_or_dose"],
        "confidence": 0.64,
    },
    {
        "id": "post_inflammatory_hyperpigmentation",
        "user": "Mụn em đã bớt nhưng còn nhiều vết thâm nâu sau mụn ở má, thỉnh thoảng còn vài mụn đầu trắng.",
        "normalized_case": {
            "lesion_types": ["post_inflammatory_hyperpigmentation", "whitehead"],
            "distribution": ["cheeks"],
            "inflammation_level": "mild",
            "scarring_signs": ["thâm sau viêm"],
            "treatment_goals": ["giảm thâm", "ngừa mụn tái phát"],
            "missing_info": ["age", "skin_type", "medication_history", "pregnancy_or_breastfeeding"],
        },
        "severity": "mild",
        "severity_rationale": "Mụn hoạt động ít, chủ yếu là thâm sau viêm và vài nhân mụn trắng.",
        "recommendations": [
            {
                "category": "skincare",
                "action": "Ưu tiên chống nắng đều, tránh nặn/cạy và duy trì chăm sóc da dịu nhẹ.",
                "rationale": "Chống nắng và giảm viêm tái diễn giúp hạn chế thâm kéo dài.",
                "guideline_refs": ["NICE_NG198"],
            },
            {
                "category": "otc_info",
                "action": "Có thể tìm hiểu các lựa chọn hỗ trợ thâm ở mức thông tin chung, nhưng tránh phối quá nhiều hoạt chất gây kích ứng.",
                "rationale": "Cần giữ boundary vì chưa biết loại da, thai kỳ và sản phẩm đang dùng.",
                "guideline_refs": ["AAD_2024"],
            },
        ],
        "guideline_alignment": {"status": "aligned", "notes": "Tập trung chăm sóc nền và phòng tái phát, không kê phác đồ."},
        "safety_flags": ["no_prescription_or_dose"],
        "confidence": 0.73,
    },
    {
        "id": "self_extraction_procedure",
        "user": "Em có nhiều mụn ẩn, định tự nặn rồi peel da ở nhà cho sạch nhân được không?",
        "normalized_case": {
            "lesion_types": ["closed_comedone", "comedone"],
            "inflammation_level": "unknown",
            "treatment_goals": ["tự nặn mụn", "tự peel da"],
            "red_flags": ["self_extraction_request", "home_peel_request"],
            "missing_info": ["age", "distribution", "scarring_signs", "skin_sensitivity"],
        },
        "severity": "unknown",
        "severity_rationale": "Có mô tả mụn ẩn nhưng thiếu phân bố/mức độ; câu hỏi chứa ý định tự thủ thuật tại nhà.",
        "recommendations": [
            {
                "category": "safety",
                "action": "Không nên tự nặn mụn hoặc tự peel da tại nhà, đặc biệt khi chưa đánh giá loại da và mức độ viêm.",
                "rationale": "Tự thủ thuật có thể gây kích ứng, nhiễm trùng, thâm và sẹo.",
                "guideline_refs": ["NICE_NG198"],
            },
            {
                "category": "see_doctor",
                "action": "Nếu mụn ẩn nhiều, kéo dài hoặc có sẹo/thâm, nên gặp bác sĩ da liễu để chọn hướng phù hợp.",
                "rationale": "Đánh giá trực tiếp giúp giảm nguy cơ can thiệp sai.",
                "guideline_refs": ["AAD_2024"],
            },
        ],
        "red_flags": ["self_extraction_request", "home_peel_request"],
        "guideline_alignment": {"status": "aligned", "notes": "Chặn unsafe self-procedure và chuyển sang đánh giá y khoa khi cần."},
        "safety_flags": ["no_self_procedure", "no_prescription_or_dose"],
        "confidence": 0.7,
    },
]


def _deep_merge_case(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_case(merged[key], value)
        else:
            merged[key] = value
    return merged


def _output_from_template(template: dict[str, Any]) -> ClinicalCaseTrainingOutput:
    base_case = NormalizedAcneCase().model_dump()
    case_updates = template.get("normalized_case", {})
    normalized_case = NormalizedAcneCase.model_validate(_deep_merge_case(base_case, case_updates))

    guideline_payload = {"refs": ["AAD_2024", "NICE_NG198"]}
    guideline_payload.update(template.get("guideline_alignment", {}))

    return ClinicalCaseTrainingOutput(
        normalized_case=normalized_case,
        severity=template["severity"],
        severity_rationale=template["severity_rationale"],
        recommendations=[
            ClinicalCaseRecommendation.model_validate(rec)
            for rec in template.get("recommendations", [])
        ],
        red_flags=template.get("red_flags", []),
        guideline_alignment=GuidelineAlignment.model_validate(guideline_payload),
        safety_flags=template.get("safety_flags", ["no_prescription_or_dose"]),
        confidence=template.get("confidence", 0.5),
    )


def record_from_template(template: dict[str, Any]) -> dict[str, Any]:
    output = _output_from_template(template)
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": template["user"]},
            {"role": "assistant", "content": output.model_dump_json()},
        ]
    }


def generate_records() -> list[dict[str, Any]]:
    return [record_from_template(template) for template in CASE_TEMPLATES]


def write_dataset(output_path: str | Path, *, validate: bool = True) -> int:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    records = generate_records()
    with out.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    if validate:
        stats = validate_file(out)
        if stats.rejected:
            raise RuntimeError(
                "Generated dataset failed validation: "
                f"total={stats.total} kept={stats.kept} rejected={stats.rejected} reasons={stats.reasons}"
            )
    return len(records)
