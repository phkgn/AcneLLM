"""Load rules from YAML and apply pre/post checks to user input / advise output."""
from __future__ import annotations
from functools import lru_cache
import re
import yaml
from pathlib import Path
from loguru import logger

from ..schemas import UserInput, AdviseOutput, RedFlag
from .pii import mask_pii, contains_pii


# ─────────── Scope detection terms ───────────
# Mở rộng đáng kể để bao phủ thuật ngữ da mụn tiếng Việt, teencode, không dấu,
# cùng các thuật ngữ y khoa liên quan.
_ACNE_SCOPE_TERMS = (
    # ── Loại mụn & tổn thương (có dấu + không dấu + teencode) ──
    "mụn", "mun", "trứng cá", "trung ca", "nhân mụn", "nhan mun",
    "mụn bọc", "mun boc", "mụn nang", "mun nang", "mụn u nang", "mun u nang",
    "mụn đầu đen", "mun dau den", "đầu đen", "dau den",
    "mụn đầu trắng", "mun dau trang", "đầu trắng", "dau trang",
    "mụn mủ", "mun mu", "mụn mủ viêm", "mụn mủ đỏ",
    "mụn viêm", "mun viem", "mụn đỏ", "mun do", "mụn sưng", "mun sung",
    "mụn cám", "mun cam", "mụn ẩn", "mun an", "mụn li ti", "mun li ti",
    "mụn dưới da", "mun duoi da", "mụn cứng", "mụn to", "mụn đau",
    "mụn mãn tính", "mụn tái phát", "mụn hoài", "mụn mãi không hết",
    "nổi mụn", "noi mun", "bị mụn", "bi mun", "da nổi", "nổi cục",
    "nổi hột", "noi hot", "nổi sẩn", "noi san", "nổi đốm đỏ", "đốm đỏ trên da",
    "comedone", "blackhead", "whitehead", "papule", "pustule",
    "nodule", "cyst", "acne vulgaris", "acne", "comedonal acne",
    "cystic acne", "hormonal acne", "fungal acne", "mụn nấm",
    # ── Sẹo & thâm sau mụn ──
    "sẹo mụn", "seo mun", "sẹo rỗ", "seo ro", "sẹo lõm", "seo lom",
    "sẹo lồi", "seo loi", "sẹo keloid", "keloid", "hypertrophic scar",
    "thâm mụn", "tham mun", "vết thâm", "vet tham", "sẹo thâm", "seo tham",
    "tăng sắc tố sau viêm", "tang sac to sau viem", "pih", "post-inflammatory hyperpigmentation",
    "thâm đỏ", "tham do", "thâm nâu", "vết đỏ sau mụn", "đỏ sau mụn",
    "atrophic scar", "icepick scar", "boxcar scar", "rolling scar",
    # ── Loại da & bã nhờn ──
    "da dầu", "da dau", "da nhờn", "da nhon", "da bóng nhờn", "da bong nhon",
    "da khô", "da kho", "da thiếu nước", "da thieu nuoc",
    "da nhạy cảm", "da nhay cam", "da kích ứng", "da kich ung",
    "da hỗn hợp", "da hon hop", "da thường", "da dễ nổi mụn",
    "lỗ chân lông", "lo chan long", "lỗ chân lông to", "lỗ chân lông bít tắc",
    "bít tắc lỗ chân lông", "bit tac lo chan long", "se khít lỗ chân lông",
    "bã nhờn", "ba nhon", "tiết bã nhờn", "tiet ba nhon",
    "sebum", "sebaceous", "keratin", "follicle", "nang lông",
    "tế bào chết", "te bao chet", "bong tróc da", "bong troc da",
    # ── Tình trạng da liên quan ──
    "viêm nang lông", "viem nang long", "folliculitis",
    "viêm da tiết bã", "seborrheic dermatitis",
    "rosacea", "đỏ mặt", "do mat", "giãn mao mạch", "gian mao mach",
    "perioral dermatitis", "viêm quanh miệng",
    "milia", "hạt milia", "hat milia", "hạt kê", "hat ke",
    "dày sừng nang lông", "keratosis pilaris",
    "tắc nghẽn nang lông", "tac nghen nang long",
    # ── Vi khuẩn & miễn dịch ──
    "cutibacterium acnes", "c. acnes", "p.acnes", "p. acnes",
    "vi khuẩn", "vi khuan", "vi khuẩn gây mụn",
    "tlr2", "tlr4", "nlrp3", "inflammasome", "porphyrin", "lipase",
    "biofilm", "il-1β", "il-1b", "il1b", "th17",
    "kháng kháng sinh", "khang khang sinh", "antibiotic resistance",
    # ── Hoạt chất điều trị ──
    "retinoid", "isotretinoin", "tretinoin", "adapalene", "retinol", "tazarotene",
    "benzoyl peroxide", "bp", "bpo",
    "salicylic acid", "sa", "bha salicylic",
    "azelaic acid", "niacinamide", "nicotinamide",
    "clindamycin", "erythromycin", "doxycycline", "minocycline", "tetracycline",
    "lymecycline", "trimethoprim", "sulfamethoxazole",
    "aha", "bha", "pha", "aha/bha", "glycolic acid", "lactic acid", "mandelic acid",
    "zinc", "kẽm", "ken", "tea tree", "tràm trà", "tram tra", "sulfur", "lưu huỳnh",
    "dapsone", "spironolactone", "cyproterone", "flutamide",
    "tranexamic acid", "arbutin", "kojic acid", "vitamin c", "vitamin e",
    "hyaluronic acid", "ceramide", "peptide",
    # ── Thủ thuật & liệu pháp ──
    "peel da", "chemical peel", "peeling", "lăn kim", "lan kim", "microneedling",
    "laser", "laser co2", "laser fractional", "ipl", "ánh sáng xung mạnh",
    "pdt", "liệu pháp ánh sáng", "blue light therapy",
    "lấy nhân mụn", "lay nhan mun", "nặn mụn", "nan mun", "chích mụn", "chich mun",
    "tiêm cortisone", "tiem cortisone", "tiêm tổn thương", "intralesional injection",
    "điều trị mụn", "dieu tri mun", "trị mụn", "tri mun", "chữa mụn", "chua mun",
    "kem trị mụn", "thuốc trị mụn", "thuoc tri mun",
    # ── Sản phẩm & bước skincare ──
    "skincare", "chăm sóc da", "cham soc da", "routine da",
    "sữa rửa mặt", "sua rua mat", "cleanser", "foam rửa mặt", "gel rửa mặt",
    "toner", "nước cân bằng da", "nuoc can bang da",
    "serum", "essence", "ampoule",
    "moisturizer", "kem dưỡng ẩm", "kem duong am", "lotion",
    "kem chống nắng", "kem chong nang", "sunscreen", "spf",
    "tẩy tế bào chết", "tay te bao chet", "exfoliant", "scrub",
    "mặt nạ", "mat na", "sheet mask", "clay mask",
    "micellar water", "dầu tẩy trang", "dau tay trang",
    "non-comedogenic", "không gây bít tắc", "oil-free",
    # ── Nội tiết & nguyên nhân ──
    "nội tiết", "noi tiet", "androgen", "testosterone", "dhea", "dheas",
    "hormone", "hormon", "chu kỳ kinh nguyệt", "chu ky kinh nguyet",
    "rụng trứng", "rung trung", "mụn kinh nguyệt", "mụn nội tiết",
    "mụn tuổi dậy thì", "mun tuoi day thi", "mụn stress", "mun stress",
    "cortisol", "tuyến thượng thận", "insulin", "igf-1",
    "pcos", "buồng trứng đa nang", "buong trung da nang",
    "tuyến bã nhờn", "tuyen ba nhon", "sebaceous gland",
    "chế độ ăn", "che do an", "đường", "duong", "sữa", "sua", "whey",
    "chỉ số glycemic", "glycemic index", "gi cao",
    # ── Vùng da cơ thể ──
    "trán", "tran", "mũi", "mui", "cằm", "cam", "má", "ma",
    "thái dương", "thai duong", "vùng chữ t", "vung chu t", "vùng u",
    "lưng", "lung", "ngực", "nguc", "vai", "bả vai",
    "mông", "mong", "đùi", "dui", "cổ", "co", "sau gáy",
    "hairline", "chân tóc", "chan toc",
    # ── Diễn biến / di chuyển tổn thương ──
    "lan xuống", "lan xuong", "lan ra", "lan sang",
    "lan từ mặt", "lan tu mat", "lan lên", "lan len",
    "chuyển xuống", "chuyen xuong", "chuyển sang", "chuyen sang",
    "từ mặt xuống", "tu mat xuong", "từ lưng lên", "tu lung len",
    "bớt ở mặt", "bot o mat", "giảm ở mặt", "giam o mat",
    "hết ở mặt", "het o mat", "hết trên mặt", "het tren mat",
    "lại nổi ở", "lai noi o", "nổi ở vùng khác", "noi o vung khac",
    "mụn di chuyển", "mun di chuyen", "mụn lan", "mun lan",
    "nổi thêm ở", "noi them o", "xuất hiện thêm ở", "xuat hien them o",
    "mụn đã bớt", "mun da bot", "mụn đã giảm", "mun da giam",
    "thay vào đó nổi", "thay vao do noi",
    # ── Da liễu / bác sĩ ──
    "da liễu", "da lieu", "bác sĩ da liễu", "bac si da lieu",
    "khám da liễu", "kham da lieu", "phòng khám da liễu",
    "dermatologist", "dermatology", "dermatitis",
)

_GENITAL_BODY_TERMS = (
    # Vùng sinh dục / hậu môn — rõ ràng ngoài phạm vi tư vấn mụn da
    "bìu", "biu", "dương vật", "duong vat", "sinh dục", "sinh duc",
    "âm đạo", "am dao", "âm hộ", "am ho", "âm vật", "am vat",
    "hậu môn", "hau mon", "trực tràng", "truc trang",
    "mụn sinh dục", "mun sinh duc", "mụn ở bìu", "mun o biu",
    "mụn ở dương vật", "mụn ở hậu môn", "mụn ở âm đạo",
    "mụn vùng kín", "mun vung kin", "vùng kín", "vung kin",
    "mụn dưới đáy chậu", "mụn ở bộ phận sinh dục",
    "mụn ở vùng nhạy cảm", "mun o vung nhay cam",
)

_OUT_OF_SCOPE_INTENT_TERMS = (
    # ── Lập trình & công nghệ ──
    "viết code", "viet code", "viết script", "viet script",
    "python script", "http request", "api server",
    "javascript", "typescript", "sql query", "regex pattern",
    "debug code", "fix bug", "lỗi code", "loi code",
    "powershell", "bash script", "programming", "coding",
    "lập trình", "lap trinh", "phần mềm", "phan mem",
    "thuật toán", "thuat toan", "machine learning model", "neural network",
    "viết hàm", "viet ham", "viết class", "deploy server",
    # ── Toán học thuần túy ──
    "giải phương trình", "giai phuong trinh",
    "đạo hàm", "dao ham", "tích phân", "tich phan",
    "đại số tuyến tính", "ma trận", "ma tran",
    "hình học", "hinh hoc", "lượng giác", "luong giac",
    "xác suất thống kê", "xac suat thong ke",
    # ── Khoa học không liên quan da ──
    "vật lý", "vat ly", "cơ học", "co hoc", "nhiệt động học",
    "hóa học vô cơ", "hoa hoc vo co", "phản ứng hóa học", "phan ung hoa hoc",
    "lịch sử", "lich su", "địa lý", "dia ly",
    "thiên văn", "thien van", "vũ trụ", "vu tru",
    # ── Tài chính & kinh tế ──
    "chứng khoán", "chung khoan", "cổ phiếu", "co phieu",
    "bitcoin", "crypto", "tiền điện tử", "tien dien tu",
    "ngoại hối", "forex", "trading", "đầu tư tài chính", "dau tu tai chinh",
    "ngân hàng", "ngan hang", "lãi suất", "lai suat",
    "cờ bạc", "co bac", "xổ số", "xo so", "cá cược", "ca cuoc",
    # ── Thể thao & giải trí ──
    "bóng đá", "bong da", "bóng rổ", "bong ro", "tennis", "cầu lông",
    "kết quả trận đấu", "ket qua tran dau", "bảng xếp hạng", "bang xep hang",
    "phim", "xem phim", "game", "trò chơi", "tro choi",
    "ca sĩ", "ca si", "diễn viên", "dien vien", "âm nhạc", "am nhac",
    # ── Chính trị & tôn giáo ──
    "chính trị", "chinh tri", "bầu cử", "bau cu",
    "đảng phái", "dang phai", "chính phủ", "chinh phu",
    "tôn giáo", "ton giao", "phật giáo", "phat giao",
    "thiên chúa giáo", "thien chua giao", "hồi giáo", "hoi giao",
    "cộng sản", "cong san", "tư bản", "tu ban",
    # ── Nấu ăn & ẩm thực không liên quan ──
    "công thức nấu ăn", "cong thuc nau an", "nấu món", "nau mon",
    "nguyên liệu nấu", "nguyen lieu nau", "cách làm bánh", "cach lam banh",
    "món ăn ngon", "mon an ngon", "nhà hàng", "nha hang",
    # ── Du lịch & địa điểm ──
    "du lịch", "du lich", "khách sạn", "khach san",
    "đặt vé máy bay", "dat ve may bay", "visa", "hộ chiếu", "ho chieu",
    "địa điểm du lịch", "dia diem du lich",
    # ── Học thuật & giáo dục ──
    "bài tập về nhà", "bai tap ve nha", "làm bài luận", "lam bai luan",
    "ôn thi", "on thi", "đề thi", "de thi", "đáp án bài thi",
    "kiến thức lịch sử", "kien thuc lich su",
    # ── Bạo lực & nguy hiểm ──
    "tự tử", "tu tu", "tự sát", "tu sat", "giết người", "giet nguoi",
    "chế tạo vũ khí", "che tao vu khi", "chế tạo bom", "che tao bom",
    "ma túy", "ma tuy", "thuốc phiện", "thuoc phien", "cần sa", "can sa",
    # ── Nội dung người lớn ──
    "sex", "tình dục", "tinh duc", "khiêu dâm", "khieu dam",
    "nội dung 18+", "noi dung 18+",
    # ── Dịch thuật & ngôn ngữ học ──
    "dịch thuật", "dich thuat", "phiên dịch", "phien dich",
    "ngữ pháp tiếng anh", "ngu phap tieng anh",
    "học ngoại ngữ", "hoc ngoai ngu",
)

_PROMPT_INJECTION_PHRASES = (
    # ── Lệnh override / reset trực tiếp (EN) ──
    "ignore previous", "ignore all previous", "ignore prior",
    "disregard previous", "disregard all", "forget prior", "forget all instructions",
    "override instructions", "override your instructions", "override your rules",
    "new instructions", "updated instructions", "your new task",
    "system override", "system prompt override", "admin override",
    "from now on", "starting now", "henceforth",
    # ── Thay đổi danh tính / nhân cách (EN) ──
    "you are no longer", "you are now a", "act only as",
    "you are an ai that", "pretend you are", "pretend to be",
    "act as if you are", "act as though", "roleplay as",
    "simulate being", "imagine you are", "your true self",
    "without restrictions", "without any restrictions", "no restrictions",
    "unrestricted mode", "developer mode", "dan mode", "jailbreak",
    "unlock yourself", "unrestricted ai",
    # ── Lệnh bỏ qua giới hạn (EN) ──
    "bypass", "circumvent", "loophole",
    "do anything now", "anything now", "no longer bound",
    "rules don't apply", "rules do not apply",
    "ignore your training", "disregard your training",
    "ignore safety", "ignore your safety", "disable safety",
    "output without filter", "unfiltered response",
    # ── Ký tự / token đặc biệt thường dùng trong jailbreak ──
    "[system]", "[/system]", "[inst]", "[/inst]",
    "<|system|>", "<|user|>", "<|assistant|>",
    "###instruction", "### instruction",
    "[ignore]", "[override]",
    # ── Lệnh override / reset trực tiếp (VI có dấu) ──
    "bỏ qua hướng dẫn", "bỏ qua tất cả hướng dẫn",
    "bỏ tất cả policy", "bỏ tất cả chính sách", "bỏ qua chính sách",
    "xóa hướng dẫn", "xóa tất cả hướng dẫn trước",
    "quên tất cả", "quên hướng dẫn", "quên đi nhiệm vụ",
    "ghi đè hướng dẫn", "ghi đè lệnh", "cập nhật hướng dẫn mới",
    "lệnh mới", "nhiệm vụ mới", "hướng dẫn mới",
    "từ bây giờ", "từ lúc này", "kể từ bây giờ",
    # ── Thay đổi danh tính / nhân cách (VI có dấu) ──
    "không còn là", "bây giờ bạn là", "từ nay bạn là",
    "bây giờ là ai", "giả vờ là", "đóng vai", "đóng giả",
    "thay đổi vai trò", "thay đổi nhân cách", "thay đổi nhiệm vụ",
    "hãy là", "hãy trở thành", "hãy đóng vai",
    "bạn là một ai đó khác", "hãy giả vờ",
    "không có giới hạn", "không bị giới hạn", "không có quy tắc",
    "chế độ không kiểm duyệt", "chế độ nhà phát triển",
    "mở khóa chính mình", "phiên bản không bị hạn chế",
    # ── Lệnh bỏ qua giới hạn (VI có dấu) ──
    "bỏ qua an toàn", "vô hiệu hóa an toàn", "bỏ qua bộ lọc",
    "phản hồi không lọc", "không cần lọc nội dung",
    "bỏ qua kiểm duyệt", "không cần kiểm duyệt",
    "làm ơn bỏ qua", "hãy bỏ qua", "vui lòng bỏ qua",
    # ── Tiếng Việt không dấu / teencode ──
    "bo qua huong dan", "bo tat ca policy", "bo tat ca chinh sach",
    "xoa huong dan", "quen tat ca", "quen huong dan",
    "ghi de lenh", "lenh moi", "nhiem vu moi",
    "tu bay gio", "ke tu bay gio",
    "khong con la", "bay gio ban la", "tu nay ban la",
    "gia vo la", "dong vai", "dong gia", "hay la", "hay tro thanh",
    "khong co gioi han", "khong bi gioi han", "khong co quy tac",
    "che do khong kiem duyet", "mo khoa chinh minh",
    "bo qua an toan", "vo hieu hoa an toan",
    "lam on bo qua", "hay bo qua", "vui long bo qua",
)


@lru_cache(maxsize=32)
def _boundary_regex(terms: tuple[str, ...]) -> re.Pattern[str] | None:
    """Mot regex duy nhat, moi term deu co ranh gioi tu, compile mot lan.

    BUG FIX: ban cu chi ap ranh gioi cho 6 alias ngan; 414 term con lai dung
    `term in lowered`. Bang _ACNE_SCOPE_TERMS co cac term hai ky tu khong dau
    ("co" = co, "ma" = ma, "cam" = cam, "vai", "dui", "sua"), nen
    is_acne_scope_text("con cho nha toi bi om") tra True vi "co" nam trong "con".
    Hau qua that: _has_established_case gan nhu luon True -> ban va
    _intent_patch (clarify -> advise) kich hoat rong hon pham vi no tuyen bo.

    Gop thanh mot alternation cung nhanh hon 420 lan `in`/`re.search`.
    """
    cleaned = tuple(dict.fromkeys(t.strip().lower() for t in terms if t and t.strip()))
    if not cleaned:
        return None
    body = "|".join(re.escape(t) for t in sorted(cleaned, key=len, reverse=True))
    return re.compile(rf"(?<!\w)(?:{body})(?!\w)")


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    regex = _boundary_regex(tuple(terms))
    return bool(regex and regex.search(text.lower()))


def is_prompt_injection(text: str) -> bool:
    q = text.lower()
    return any(p in q for p in _PROMPT_INJECTION_PHRASES)


def is_genital_out_of_scope(text: str) -> bool:
    """True khi text mention vùng sinh dục/hậu môn — ngoài phạm vi mụn da."""
    return _contains_any(text, _GENITAL_BODY_TERMS)


class GuardrailRunner:
    """Cong tat dinh chay TRUOC generator.

    Con lai dung ba viec, va ca ba deu co y khong phu thuoc phan doan cua model:
    chan prompt injection, chan vung sinh duc, chan chong chi dinh thuoc.

    Tang "scope mem" (cau hoi co ngoai pham vi khong) da chuyen han sang intaker
    /SemanticRouter -- xem Phase 4 trong docs/CLEANUP_TASKS.md.
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
        if len(user.description.strip()) < 1:
            raise ValueError("description quá ngắn")
        if is_prompt_injection(user.description):
            raise ValueError("Phát hiện prompt injection trong description")
        # PII detection — chỉ log cảnh báo, không từ chối (user có thể nhập
        # thông tin cá nhân hợp lệ như tuổi, giới tính)
        if contains_pii(user.description):
            masked = mask_pii(user.description)
            logger.warning(
                f"[guardrails] PII detected in user description. "
                f"Masked for log: {masked[:200]}"
            )

    # ponytail: scope_check + _scope_refusal_if_out_of_scope da bi xoa (Phase 4).
    # Viec quyet mot cau co ngoai pham vi hay khong gio do intaker (INTAKE_MODE=
    # unified) va SemanticRouter lam -- di.py:229 da ghi 'Soft OOS moved to
    # SemanticRouter' tu truoc, hai ham nay chi con test goi.
    # Tang 2 (OOD embedding) ben trong chung chua tung chay: di.py truyen
    # enable_ood=False nen self._ood luon None.
    # Khong luat y khoa nao mat: intake.py tu dung ban tu choi rieng cho
    # genital scope va pre_check.

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

    @staticmethod
    def is_acne_scope_text(text: str) -> bool:
        lowered = text.lower().replace("acnellm", "")
        if _contains_any(lowered, _OUT_OF_SCOPE_INTENT_TERMS):
            return False
        return _contains_any(lowered, _ACNE_SCOPE_TERMS)

    @staticmethod
    def is_genital_scope(text: str) -> bool:
        """True khi text mention vùng sinh dục/hậu môn."""
        return is_genital_out_of_scope(text)

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
