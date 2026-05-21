"""Load rules from YAML and apply pre/post checks to user input / advise output."""
from __future__ import annotations
import re
import yaml
from pathlib import Path
from loguru import logger

from ..schemas import UserInput, AdviseOutput, RedFlag, Recommendation
from .ood_detector import OodDetector, mask_pii, contains_pii
from .drug_checker import DrugChecker, DrugWarning


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


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def is_prompt_injection(text: str) -> bool:
    q = text.lower()
    return any(p in q for p in _PROMPT_INJECTION_PHRASES)


def is_genital_out_of_scope(text: str) -> bool:
    """True khi text mention vùng sinh dục/hậu môn — ngoài phạm vi mụn da."""
    return _contains_any(text, _GENITAL_BODY_TERMS)


class GuardrailRunner:
    def __init__(
        self,
        config_path: str,
        embedder=None,
        ood_threshold: float = 0.25,
        centroid_path: str | None = None,
        enable_ood: bool = True,
        scope_mode: str = "soft",
    ):
        p = Path(config_path)
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                self.cfg = yaml.safe_load(f) or {}
        else:
            logger.warning(f"guardrails.yaml not found at {p}, running with empty rules")
            self.cfg = {"rules": []}
        self.rules: list[dict] = self.cfg.get("rules", [])
        self.scope_mode = self._normalize_scope_mode(scope_mode)

        # OOD detector — lazy: chỉ init khi embedder được truyền vào
        self.enable_ood = enable_ood
        self._ood: OodDetector | None = None
        if enable_ood and embedder is not None:
            _centroid_path = centroid_path or str(
                Path(config_path).parent / "ood_centroid.json"
            )
            self._ood = OodDetector(
                embedder=embedder,
                centroid_path=_centroid_path,
                ood_threshold=ood_threshold,
            )
            logger.info(
                f"[guardrails] OOD detector ready "
                f"(threshold={ood_threshold}, centroid={_centroid_path})"
            )

        # Drug checker -- auto-discover drugs_acne.yaml cung cap voi guardrails.yaml
        _drug_yaml = str(Path(config_path).parent / "drugs_acne.yaml")
        self._drug_checker: DrugChecker | None = None
        if Path(_drug_yaml).exists():
            self._drug_checker = DrugChecker(_drug_yaml)
        else:
            logger.info(f"[guardrails] drugs_acne.yaml not found at {_drug_yaml}, drug checker disabled")

    @staticmethod
    def _normalize_scope_mode(scope_mode: str) -> str:
        mode = (scope_mode or "soft").strip().lower()
        if mode not in {"hard", "soft", "off"}:
            logger.warning(
                f"[guardrails] Invalid scope_mode={scope_mode!r}; falling back to soft"
            )
            return "soft"
        return mode

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

    def _scope_refusal_if_out_of_scope(
        self,
        user: UserInput,
        has_acne_history: bool = False,
    ) -> AdviseOutput | None:
        """Build the old deterministic refusal when text is out of acne scope.

        Kiểm tra 2 tầng:
        1. Keyword-based (nhanh, không cần model): _ACNE_SCOPE_TERMS /
           _OUT_OF_SCOPE_INTENT_TERMS — bắt nhanh câu hỏi rõ ràng in/out.
        2. Embedding-based OOD (chính xác hơn): cosine similarity với
           centroid acne domain — bắt câu hỏi ngắn / biến thể lạ / không
           có keyword nhưng rõ ràng ngoài domain.

        Args:
            has_acne_history: Khi True (session đã có acne turns trước), bỏ
                qua OOD check — follow-up ngắn như "còn gì nữa k" hợp lệ
                trong ngữ cảnh session acne.
        """
        # O2: Session-aware OOD — không check OOD nếu session đã xác nhận acne context.
        # Follow-up ngắn trong session acne ("còn gì nữa k", "sao vậy") không cần OOD.
        if has_acne_history:
            logger.debug("[guardrails] has_acne_history=True — skip OOD check")
            return None

        # Tầng 1: keyword check (instant, no model needed)
        if self.is_acne_scope_text(user.description):
            return None  # clearly in-scope → pass

        # Tầng 2: embedding OOD check (chỉ khi keyword tầng 1 không xác định
        # rõ là in-scope — tức là không có acne keyword rõ ràng)
        if self._ood is not None:
            ood = self._ood.is_out_of_domain(user.description)
            sim = self._ood.similarity(user.description)
            if sim is None:
                logger.debug(
                    "[guardrails] Keyword miss and OOD unavailable; "
                    "using keyword-only scope decision"
                )
            elif not ood:
                # OOD model cho là in-scope dù không có keyword → pass
                logger.debug(
                    f"[guardrails] Keyword miss but OOD sim={sim:.3f} "
                    f"> threshold → pass"
                )
                return None
            else:
                logger.debug(
                    f"[guardrails] OOD confirmed: sim={sim:.3f} "
                    f"< {self._ood.ood_threshold}"
                )
        # Không có OOD model → tin vào keyword: không có acne keyword → refuse
        return AdviseOutput(
            severity="unknown",
            acne_type_primary="unknown",
            causes=["Câu hỏi ngoài phạm vi tư vấn da mụn"],
            recommendations=[],
            red_flags=[],
            used_chunks=[],
            confidence=0.0,
            disclaimer=(
                "Câu hỏi ngoài phạm vi tư vấn da mụn. "
                "Hiện mình chuyên về da mụn nên chưa hỗ trợ tốt chủ đề này. "
                "Nếu bạn muốn, bạn có thể mô tả tình trạng mụn/da cụ thể để mình hỗ trợ ngay."
            ),
            mode=user.mode,
            model_name="",
            latency_ms=0,
        )

    def scope_check(
        self,
        user: UserInput,
        has_acne_history: bool = False,
    ) -> AdviseOutput | None:
        """Return a refusal only when scope_mode is hard.

        soft mode keeps the out-of-scope signal as telemetry and lets the
        fine-tuned LLM decide how to answer/refuse naturally.

        Args:
            has_acne_history: Forward to _scope_refusal_if_out_of_scope to
                skip OOD for short follow-ups in an established acne session.
        """
        if self.scope_mode == "off":
            return None

        refusal = self._scope_refusal_if_out_of_scope(user, has_acne_history=has_acne_history)
        if refusal is None:
            return None

        if self.scope_mode == "soft":
            logger.info(
                "[guardrails] Soft out-of-scope signal; passing to LLM: "
                f"{user.description[:160]}"
            )
            return None

        return refusal

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

    # ─────────── post-check ───────────
    def post_check(self, out: AdviseOutput, user: UserInput) -> AdviseOutput:
        out = self._apply_drug_checker(out, user)   # DrugChecker (YAML + OpenFDA)
        out = self._apply_retinoid_blocks(out, user) # fallback rule (kiem tra phan con lai)
        out = self._apply_severe_doctor(out)
        out = self._apply_age_restriction(out, user)
        out = self._apply_no_popping(out)
        out = self._apply_medication_safety(out)
        out = self._apply_medication_allergy_redflag(out, user)
        out = self._ensure_disclaimer(out)
        return out

    def _apply_drug_checker(self, out: AdviseOutput, user: UserInput) -> AdviseOutput:
        if self._drug_checker is None:
            return out
        medications = list(user.context.medications or [])
        medications += list(user.context.current_products or [])
        if not medications:
            return out
        try:
            warnings = self._drug_checker.check(medications, user.context)
            for w in warnings:
                if w.is_critical:
                    out.red_flags.append(RedFlag(
                        flag=f"Canh bao thuoc: {w.matched_drug} ({w.pregnancy_category})",
                        severity="urgent",
                        reason=w.warning_vi[:200] if w.warning_vi else "Chong chi dinh y khoa",
                    ))
                elif w.severity == "moderate" and w.warning_vi:
                    out.red_flags.append(RedFlag(
                        flag=f"Luu y thuoc: {w.matched_drug}",
                        severity="warning",
                        reason=w.warning_vi[:200],
                    ))
        except Exception as e:
            logger.warning(f"[DrugChecker] post_check error: {e}")
        return out

    def _apply_retinoid_blocks(self, out: AdviseOutput, user: UserInput) -> AdviseOutput:
        if not (user.context.is_pregnant or user.context.is_breastfeeding):
            return out
        banned = self._find_rule_keywords(
            "pregnancy_retinoid_block" if user.context.is_pregnant
            else "breastfeeding_retinoid_block"
        )
        banned = list(banned or [])
        banned.extend([
            "isotretinoin", "tretinoin", "adapalene", "retinoid", "retinol",
            "tazarotene", "doxycycline", "minocycline", "tetracycline",
            "vitamin a liều cao", "dẫn xuất vitamin a",
        ])
        new_recs: list[Recommendation] = []
        rewritten = False
        for r in out.recommendations:
            txt = (r.action + " " + (r.rationale or "")).lower()
            if any(k.lower() in txt for k in banned):
                rewritten = True
                r = r.model_copy(update={
                    "action": (
                        "Tránh các thành phần retinoid/isotretinoin và vitamin A liều cao. "
                        "Tham khảo bác sĩ da liễu để chọn giải pháp an toàn."
                    ),
                    "rationale": "Chống chỉ định retinoid trong thai kỳ và thời gian cho con bú.",
                    "category": "medication",
                })
            new_recs.append(r)
        out.recommendations = new_recs
        if rewritten:
            out.red_flags.append(RedFlag(
                flag="Tránh retinoid khi mang thai / cho con bú",
                severity="urgent",
                reason="Chống chỉ định y khoa — có thể gây dị tật thai nhi hoặc ảnh hưởng trẻ sơ sinh",
            ))
        return out

    def _apply_severe_doctor(self, out: AdviseOutput) -> AdviseOutput:
        if out.severity != "severe":
            return out
        # Mở rộng từ khóa để bắt nhiều cách diễn đạt gặp bác sĩ hơn
        doctor_keywords = (
            "bác sĩ", "chuyên khoa da liễu", "cơ sở y tế",
            "khám da liễu", "đi khám", "bệnh viện", "phòng khám",
            "da liễu", "bác sĩ da liễu", "bác sĩ nhi khoa",
        )
        joined = " ".join([r.action + " " + (r.rationale or "") for r in out.recommendations]).lower()
        if any(k in joined for k in doctor_keywords):
            return out
        next_step = (max((r.step for r in out.recommendations), default=0)) + 1
        out.recommendations.append(Recommendation(
            step=next_step,
            action="Đi khám bác sĩ chuyên khoa da liễu càng sớm càng tốt.",
            rationale="Mụn mức độ nặng có nguy cơ sẹo vĩnh viễn và cần phác đồ y khoa chuyên sâu.",
            category="see_doctor",
        ))
        out.red_flags.append(RedFlag(
            flag="Mụn mức độ nặng — cần thăm khám bác sĩ da liễu",
            severity="urgent",
            reason="Nguy cơ sẹo vĩnh viễn và biến chứng nếu không điều trị đúng cách",
        ))
        return out

    def _apply_age_restriction(self, out: AdviseOutput, user: UserInput) -> AdviseOutput:
        age = user.context.age
        if age is None or age >= 12:
            return out
        # Nếu đã có khuyến nghị gặp bác sĩ nhi/da liễu nhi thì không thêm nữa
        doctor_keywords = (
            "bác sĩ nhi khoa", "da liễu nhi", "bác sĩ da liễu",
            "khám da liễu", "bệnh viện nhi",
        )
        joined = " ".join([r.action + " " + (r.rationale or "") for r in out.recommendations]).lower()
        if any(k in joined for k in doctor_keywords):
            return out
        next_step = (max((r.step for r in out.recommendations), default=0)) + 1
        out.recommendations.append(Recommendation(
            step=next_step,
            action="Đưa trẻ đi khám bác sĩ da liễu nhi hoặc bác sĩ nhi khoa để được đánh giá chuyên sâu.",
            rationale="Da trẻ em mỏng và nhạy cảm, cần chẩn đoán chuyên khoa trước khi dùng bất kỳ sản phẩm điều trị mụn.",
            category="see_doctor",
        ))
        out.red_flags.append(RedFlag(
            flag="Trẻ em dưới 12 tuổi — cần thăm khám bác sĩ chuyên khoa nhi",
            severity="urgent",
            reason="Nguy cơ kích ứng và biến chứng nếu tự ý điều trị tại nhà cho trẻ nhỏ",
        ))
        return out

    def _apply_no_popping(self, out: AdviseOutput) -> AdviseOutput:
        bad = (
            "tự nặn", "tự cạy", "tự lấy nhân", "tự chích", "nặn mụn tại nhà",
            "nặn trứng cá", "chích mụn", "lăn kim tại nhà",
            "bôi thuốc tự chế", "đắp mặt nạ tự pha",
            "tự điều trị bằng", "tự dùng thuốc không kê đơn",
            "tự mua thuốc uống", "nặn mụn bằng tay",
            "tự peel", "peel da tại nhà", "chemical peel tại nhà",
            "tự lăn kim", "laser tại nhà", "tự chiếu laser",
        )
        out.recommendations = [
            r for r in out.recommendations
            if not any(b in (r.action + " " + (r.rationale or "")).lower() for b in bad)
        ]
        for i, r in enumerate(out.recommendations, 1):
            r.step = i
        return out

    def _apply_medication_safety(self, out: AdviseOutput) -> AdviseOutput:
        rx_terms = (
            "isotretinoin", "tretinoin", "adapalene", "tazarotene",
            "doxycycline", "minocycline", "tetracycline", "lymecycline",
            "clindamycin", "erythromycin", "spironolactone", "corticoid",
            "prednisone", "prednisolone",
        )
        antibiotic_terms = (
            "kháng sinh", "antibiotic", "doxycycline", "minocycline",
            "tetracycline", "lymecycline", "clindamycin", "erythromycin",
        )
        combination_terms = (
            "benzoyl peroxide", "bpo", "retinoid", "bác sĩ", "da liễu",
            "đi khám", "kê đơn", "theo dõi",
        )
        dose_re = re.compile(
            r"(?:isotretinoin|tretinoin|adapalene|tazarotene|doxycycline|"
            r"minocycline|tetracycline|lymecycline|clindamycin|erythromycin|"
            r"spironolactone|corticoid|prednisone|prednisolone)"
            r"[^\n]{0,90}\d+(?:[.,]\d+)?\s*(?:mg/kg|mg|mcg|%|viên|lần/ngày|ngày|tuần)",
            re.IGNORECASE | re.UNICODE,
        )
        self_use_re = re.compile(
            r"(?:tự\s*(?:mua|dùng|uống|bôi)|mua\s+về\s+dùng)[^\n]{0,80}"
            r"(?:isotretinoin|kháng\s*sinh|antibiotic|doxycycline|minocycline|"
            r"tetracycline|clindamycin|erythromycin)",
            re.IGNORECASE | re.UNICODE,
        )

        rewritten = False
        new_recs: list[Recommendation] = []
        for r in out.recommendations:
            text = f"{r.action} {r.rationale or ''}".lower()
            has_rx = any(term in text for term in rx_terms)
            has_antibiotic = any(term in text for term in antibiotic_terms)
            unsafe = bool(dose_re.search(text) or self_use_re.search(text))
            antibiotic_monotherapy = (
                has_antibiotic
                and not any(term in text for term in combination_terms)
            )

            if unsafe or antibiotic_monotherapy:
                rewritten = True
                r = r.model_copy(update={
                    "action": (
                        "Không tự dùng thuốc kê đơn hoặc kháng sinh trị mụn. "
                        "Hãy khám bác sĩ da liễu để được chọn phác đồ phù hợp."
                    ),
                    "rationale": (
                        "Thuốc kê đơn, kháng sinh và isotretinoin cần chỉ định, "
                        "theo dõi tác dụng phụ và tránh dùng sai cách."
                    ),
                    "category": "see_doctor",
                })
            elif has_rx and r.category != "see_doctor" and not any(term in text for term in combination_terms):
                rewritten = True
                r = r.model_copy(update={
                    "action": (
                        "Chỉ trao đổi về thuốc kê đơn với bác sĩ da liễu; "
                        "không tự bắt đầu thuốc tại nhà."
                    ),
                    "rationale": "Cần đánh giá trực tiếp và theo dõi an toàn khi dùng thuốc kê đơn.",
                    "category": "see_doctor",
                })
            new_recs.append(r)

        out.recommendations = new_recs
        if rewritten:
            existing = " ".join(f.flag.lower() for f in out.red_flags)
            if "thuốc kê đơn" not in existing:
                out.red_flags.append(RedFlag(
                    flag="Không tự dùng thuốc kê đơn/kháng sinh/isotretinoin",
                    severity="warn",
                    reason="Nguy cơ tác dụng phụ, kháng thuốc hoặc chống chỉ định nếu dùng sai.",
                ))
        return out

    def _apply_medication_allergy_redflag(
        self, out: AdviseOutput, user: UserInput
    ) -> AdviseOutput:
        has_meds = bool(user.context.medications)
        has_allergies = bool(user.context.allergies)
        if not (has_meds or has_allergies):
            return out
        has_medication_rec = any(r.category == "medication" for r in out.recommendations)
        if not has_medication_rec:
            return out
        existing = [f.flag.lower() for f in out.red_flags]
        new_flag_text = (
                        "Đang dùng thuốc / có tiền sử dị ứng — "
            "cần tham khảo ý kiến bác sĩ trước khi dùng thêm thuốc điều trị mụn"
        )
        if any(new_flag_text.lower() in e for e in existing):
            return out
        out.red_flags.append(RedFlag(
            flag=new_flag_text,
            severity="warn",
            reason="Nguy cơ tương tác thuốc hoặc dị ứng chéo chưa được loại trừ",
        ))
        return out

    def _ensure_disclaimer(self, out: AdviseOutput) -> AdviseOutput:
        if not out.disclaimer or len(out.disclaimer.strip()) < 10:
            out.disclaimer = (
                "Thông tin mang tính tham khảo, không thay thế chẩn đoán "
                "và điều trị từ bác sĩ chuyên khoa da liễu."
            )
        return out

    def _find_rule_keywords(self, rule_id: str) -> list[str]:
        for r in self.rules:
            if r.get("id") == rule_id:
                return r.get("forbidden_keywords", []) or []
        return []
