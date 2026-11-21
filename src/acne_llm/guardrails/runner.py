"""Cong tat dinh duy nhat con lai: chong chi dinh / tuong tac thuoc.

Nguyen tac sau Phase 7: guardrail CHI giu luat doc DU LIEU CO CAU TRUC
(boolean, so, enum do intaker dien). Moi luat khop chuoi tren van ban tu do da
bi xoa -- do la viec model lam gioi hon, va bang term chi tao false positive.

Da xoa o Phase 7 (789 chuoi):
  _ACNE_SCOPE_TERMS (420)        -> SemanticRouter + system prompt
  _OUT_OF_SCOPE_INTENT_TERMS(192)-> SemanticRouter
  _PROMPT_INJECTION_PHRASES(146) -> prompt_builder._INJECTION_MARKERS lam dung
                                    viec nay o trust boundary (sanitize chunk +
                                    history), khong doan y nguoi dung.
  _GENITAL_BODY_TERMS (31)       -> mot dong trong Modelfile system prompt.
Ly do xoa, do end-to-end tren chinh cac bang do:
  is_prompt_injection("hay la ban than cua em nhe")      -> True  (chan nham)
  is_prompt_injection("b0 qua huong dan truoc")          -> False (ne duoc)
  is_acne_scope_text("dui ga nuong")                     -> True  (term "dui")
  _has_allowed_acne_region("mun o biu co nguy hiem k")   -> True  ("co" = co)
Xem git history neu can khoi phuc.
"""
from __future__ import annotations
from pathlib import Path
import yaml
from loguru import logger

from ..schemas import UserInput, AdviseOutput, RedFlag
from .pii import mask_pii, contains_pii


class GuardrailRunner:
    """Cong tat dinh chay TRUOC generator.

    Con lai dung mot viec: chan chong chi dinh / tuong tac thuoc. No co y khong
    phu thuoc phan doan cua model, va co y KHONG doc van ban tu do -- moi dau
    vao cua no la truong co cau truc tren UserInput.
    """

    def __init__(self, config_path: str):
        p = Path(config_path)
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                self.cfg = yaml.safe_load(f) or {}
        else:
            logger.warning(f"guardrails.yaml not found at {p}, running with empty rules")
            self.cfg = {"rules": []}
        self.rules: list[dict] = self.cfg.get("rules", [])
        # ponytail: DrugChecker (358 dong) + tra cuu drugs_acne.yaml da bi xoa o
        # Phase 5. Ba luat duy nhat no con dong gop -- tetracycline <8 tuoi,
        # isotretinoin <12 tuoi, spironolactone cho nam -- gio nam thang trong
        # medication_safety_refusal. Ba luat quan trong hon (thai ky, iso+tetra)
        # von da hardcode o do tu truoc, khong he di qua DrugChecker.
        # File config/drugs_acne.yaml VAN GIU: datagen/gates.py:520 doc no de lay
        # danh sach hoat chat + alias.

    # ─────────── pre-check (before LLM) ───────────
    def pre_check(self, user: UserInput) -> None:
        """Validation o trust boundary. Khong tu choi ai vi ngu nghia.

        ponytail: check prompt injection da bo. No la blocklist 146 chuoi khop
        substring tho -- vua chan nham tieng Viet sinh hoat binh thuong ("hay la",
        "tu bay gio"), vua bi ne bang mot dau cach thua. Model tu choi jailbreak
        tot hon, va prompt_builder van sanitize o cho du lieu ngoai vao prompt.
        """
        if len(user.description.strip()) < 1:
            raise ValueError("description quá ngắn")
        # PII detection — chỉ log cảnh báo, không từ chối (user có thể nhập
        # thông tin cá nhân hợp lệ như tuổi, giới tính)
        if contains_pii(user.description):
            masked = mask_pii(user.description)
            logger.warning(
                f"[guardrails] PII detected in user description. "
                f"Masked for log: {masked[:200]}"
            )

    def medication_safety_refusal(
        self,
        user: UserInput,
        mentioned_terms: list[str] | None = None,
    ) -> AdviseOutput | None:
        """Return a deterministic refusal for critical drug risks.

        This check deliberately runs before generation. It combines medication
        facts folded from the session with drug names mentioned in the current
        question, so the LLM cannot override pregnancy contraindications or a
        tetracycline/isotretinoin interaction.
        """
        drug_terms = {
            "retinoid", "isotretinoin", "tretinoin", "adapalene", "retinol", "tazarotene",
            "doxycycline", "minocycline", "tetracycline", "lymecycline",
            "clindamycin", "erythromycin", "spironolactone",
        }
        medications = list(user.context.medications or [])
        if user.clinical is not None:
            medications.extend(user.clinical.medication_history or [])
        medications.extend(
            term for term in (mentioned_terms or [])
            if str(term).lower() in drug_terms
        )
        medications = list(dict.fromkeys(str(item).lower() for item in medications if item))
        if not medications:
            return None

        # Trang thai thai ky doc DUY NHAT tu intaker.
        #
        # Ban cu con coi `"pregnancy" in mentioned_terms` la bang chung dang mang
        # thai. Nhung `mentioned_terms` do _extract_safety_terms sinh ra bang khop
        # chuoi con tho, khong kiem phu dinh -- nen "em khong mang thai" cung sinh
        # ra "pregnancy". Do end-to-end: 5/5 cau bi chan, trong do 4 sai:
        #   "em khong mang thai, dung tretinoin duoc khong"      -> CHAN
        #   "chi toi dang mang thai, con toi dung tretinoin?"    -> CHAN
        #   "isotretinoin co nguy hiem khi mang thai khong"      -> CHAN
        # Goc van de: "co nhac toi thai ky" khac "dang mang thai". mentioned_terms
        # tra loi cau dau, cong nay can cau sau. Danh sach do van dung nguyen cho
        # retrieval, noi ma "co nhac toi" moi dung la tin hieu can.
        pregnant = bool(user.context.is_pregnant or user.context.is_breastfeeding)
        # Thai kỳ/cho con bú + bất kỳ retinoid/tetracycline/isotretinoin nào là
        # chống chỉ định TUYỆT ĐỐI — chặn ngay, không phụ thuộc mức độ của
        # drug_checker (vốn có thể không đánh dấu tretinoin/adapalene bôi là critical).
        preg_block = pregnant and any(med in drug_terms for med in medications)

        has_isotretinoin = "isotretinoin" in medications
        has_tetracycline = any(
            med in medications
            for med in ("doxycycline", "minocycline", "tetracycline", "lymecycline")
        )
        # Bon luat con lai cua DrugChecker cu, viet thang o day. Class 358 dong +
        # bang YAML 20 thuoc chi con dong gop dung may dieu nay.
        # Xem Phase 5 trong docs/CLEANUP_TASKS.md.
        #
        # LUU Y: cap isotretinoin + tetracycline TUNG duoc phat hien boi
        # DrugChecker.interactions_triggered, khong phai boi code inline -- code
        # inline chi soan CAU THONG BAO cho truong hop do. Bo DrugChecker ma quen
        # dieu kien nay thi cong im lang (test_intake bat duoc).
        interaction_block = has_isotretinoin and has_tetracycline
        age = user.context.age
        age_block = age is not None and (
            (age < 8 and has_tetracycline) or (age < 12 and has_isotretinoin)
        )
        male_block = (
            (user.context.sex or "").lower() == "male"
            and any(med in medications for med in ("spironolactone", "cyproterone"))
        )
        if not (preg_block or interaction_block or age_block or male_block):
            return None

        if pregnant and any(med in medications for med in drug_terms):
            message = (
                "Không sử dụng isotretinoin, retinoid hoặc kháng sinh nhóm tetracycline "
                "trong thai kỳ/cho con bú. Hãy ngừng ý định tự dùng thuốc và liên hệ "
                "bác sĩ sản khoa hoặc bác sĩ da liễu để được chọn phương án an toàn."
            )
        elif has_isotretinoin and has_tetracycline:
            message = (
                "Không dùng isotretinoin cùng doxycycline, minocycline hoặc kháng sinh "
                "nhóm tetracycline vì có nguy cơ tăng áp lực nội sọ. Hãy liên hệ bác sĩ "
                "da liễu kê đơn; không tự phối hợp hai nhóm thuốc này."
            )
        elif age_block:
            message = (
                "Nhóm thuốc vừa nêu chống chỉ định ở lứa tuổi này — kháng sinh nhóm "
                "tetracycline có thể làm hỏng men răng ở trẻ dưới 8 tuổi, và isotretinoin "
                "không dùng cho trẻ dưới 12 tuổi. Hãy đưa trẻ đi khám bác sĩ da liễu nhi."
            )
        elif male_block:
            message = (
                "Spironolactone và cyproterone là thuốc kháng androgen, không dùng để trị "
                "mụn cho nam giới vì gây tác dụng phụ nữ hoá. Hãy trao đổi với bác sĩ da "
                "liễu để chọn phác đồ phù hợp."
            )
        else:
            message = (
                "Không nên tự sử dụng hoặc phối hợp các thuốc vừa nêu vì có chống chỉ định "
                "hoặc tương tác quan trọng. Hãy xác nhận trực tiếp với bác sĩ kê đơn."
            )
        return AdviseOutput(
            severity="severe",
            acne_type_primary="unknown",
            causes=["Phát hiện chống chỉ định hoặc tương tác thuốc quan trọng"],
            recommendations=[],
            red_flags=[RedFlag(
                flag="Chống chỉ định/tương tác thuốc",
                severity="urgent",
                reason=message,
            )],
            used_chunks=[],
            confidence=1.0,
            disclaimer=message,
            mode=user.mode,
            model_name="deterministic-safety",
            latency_ms=0,
        )

    # ponytail: post_check + 9 ham _apply_* (251 dong) da bi xoa o Phase 3.
    #
    # Chung nhan vao mot AdviseOutput -- object co recommendations/red_flags/
    # severity. Khi output chuyen tu JSON co cau truc sang prose streaming,
    # khong con object nao de dua vao, va runtime.py:219 tu choi dung object gia.
    # Tang nay da khong chay lan nao trong production ke tu do; chi test goi.
    #
    # Bay luat ben trong da duoc doi chieu truoc khi xoa:
    #   retinoid+thai ky, tuoi <12, tu nan/tu thu thuat, disclaimer
    #       -> da co san trong chat/_safety.get_safety_suffix
    #   lieu cu the (dose_re + self_use_re)
    #       -> DA PORT sang chat/_safety, xem tests/test_safety_dose_rule.py
    #   khang sinh don tri lieu, tuong tac cheo tren text, severity->gap bac si
    #       -> co y BO. Hai cai dau la luat dung nhung chua do duoc model co vi
    #       pham that khong; cai thu ba phu thuoc truong `severity` khong con ton tai.
    #
    # Xem git history neu can khoi phuc.
