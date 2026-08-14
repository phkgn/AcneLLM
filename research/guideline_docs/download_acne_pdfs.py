"""Tai toan bo PDF guideline mun trung ca (free, no-login) ve thu muc hien tai.
Chay:  python download_acne_pdfs.py
Chi dung thu vien chuan, khong can pip install."""
import os, re, ssl, json, urllib.request as U
from urllib.parse import urljoin

OUT = os.path.dirname(os.path.abspath(__file__))
LANGDIR = {"vi": "vie_docs", "en": "en_docs"}
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
      "Accept-Language": "vi,en;q=0.9"}
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE  # ponytail: vai site VN dung cert het han

URLS = [
# (lang, ten file, url tai)
    # --- EN: guideline goc
    ("en", "EuroGuiDerm-2025-long", "https://www.guidelines.edf.one/uploads/attachments/cmkmicwv8yrsarwjrzxnr41db-euroguiderm-acne-guideline-long-version.pdf"),
    ("en", "EDF-S3-2016", "https://www.guidelines.edf.one/uploads/attachments/cl262t0fy006olajnx74ske02-acne-2016-gl.pdf"),
    ("en", "NICE-NG198", "https://www.nice.org.uk/guidance/ng198/resources/acne-vulgaris-management-pdf-66142088866501"),
    ("en", "NICE-NG198-referral", "https://www.nice.org.uk/guidance/ng198/evidence/d-referral-to-specialist-care-pdf-9144159952"),
    ("en", "CMAJ-2016-canada", "https://www.cmaj.ca/content/cmaj/188/2/118.full.pdf"),
    ("en", "CMAJ-2016-appendix", "https://www.cmaj.ca/content/cmaj/suppl/2015/11/16/cmaj.140665.DC1/140665-guide-4-at.pdf"),
    ("en", "AAD-2024-supplement", "https://www.jaad.org/cms/10.1016/j.jaad.2023.12.017/attachment/5edd6433-54d1-48fd-9f6f-bb8b515d27f2/mmc1.pdf"),
    # --- EN: tong hop lam sang
    ("en", "AAFP-2019", "https://fmhub.org/wp-content/uploads/2021/08/Acne.pdf"),
    ("en", "AAFP-2012", "https://www.aafp.org/pubs/afp/issues/2012/1015/p734.pdf"),
    ("en", "AAFP-2004", "https://www.aafp.org/pubs/afp/issues/2004/0501/p2123.pdf"),
    ("en", "BMJ-NICE-summary", "http://dickyricky.com/Medicine/Papers/2021_09_25%20BMJ%20Management%20of%20acne%20vulgaris%20summary%20of%20NICE%20guidance%20NG198.pdf"),
    # --- EN: chau A / open access (script tu do tim link PDF trong trang)
    # ponytail: NCBI chan bot khi tai .pdf -> dung mirror Europe PMC (?pdf=render)
    ("en", "Singapore-DSS-2019", "https://europepmc.org/articles/PMC6715335?pdf=render"),
    ("en", "ASAP-2024-seo-mun", "https://europepmc.org/articles/PMC11003649?pdf=render"),
    ("en", "PRACT-India-2025", "https://europepmc.org/articles/PMC12382837?pdf=render"),
    ("en", "NICE-primary-care", "https://europepmc.org/articles/PMC8686441?pdf=render"),
    ("en", "Asian-dermocosmetics-2024", "https://www.mdpi.com/2079-9284/11/6/220/pdf"),
    ("en", "China-2019-EN", "https://journals.lww.com/ijdv/fulltext/2019/09000/chinese_guidelines_for_the_management_of_acne.1.aspx"),
    # ponytail: 2 bai IJDVL duoi day chi co ban HTML, khong co file PDF -> bo khoi list
    # https://ijdvl.com/standard-guidelines-of-care-for-acne-surgery/
    # https://ijdvl.com/algorithms-for-the-management-of-acne/
    # --- VI
    ("vi", "BYT-Da-lieu-2015", "https://kcb.vn/upload/2005611/20210723/Huong-dan-chan-doan-dieu-tri-Da-lieu.pdf"),
    ("vi", "AnGiang-phac-do-da-lieu", "https://bvag.com.vn/wp-content/uploads/2013/01/k2_attachments_PHAC-DO-KHOA-DA-LIEU-2012.pdf"),
    ("vi", "Hue-azithromycin-adapalene", "https://jmp.huemed-univ.edu.vn/BBao/2021/9/PDF_2021m09d08_15_19_54.pdf"),
    ("vi", "108-isotretinoin-vitD", "https://tcydls108.benhvien108.vn/index.php/YDLS/article/download/1356/1198/"),
    ("vi", "108-isotretinoin-azithro", "https://tcydls108.benhvien108.vn/index.php/YDLS/article/download/1232/1082/"),
    ("vi", "CanTho-isotretinoin", "https://tapchi.ctump.edu.vn/index.php/ctump/article/download/981/834/2563"),
    ("vi", "VJDV-dong-thuan-duoc-my-pham", "https://vjdv.vn/index.php/vjdv/article/view/188"),
    ("vi", "VJDV-minocyclin", "https://vjdv.vn/index.php/vjdv/article/view/159"),
    ("vi", "VJDV-isotretinoin-so-sanh", "https://vjdv.vn/index.php/vjdv/article/view/39"),
    ("vi", "VMJ-rau-muong", "https://tapchiyhocvietnam.vn/index.php/vmj/article/view/13475"),
# BO 2026-07: "CTUMP-chat-luong-cuoc-song" (tapchi.ctump.edu.vn/.../view/4668).
# Ly do: PDF dinh vi tung ky tu -> text ra vun ("M ụ n tr ứ ng cá"), 52/54 chunk hong,
# BM25 khong khop duoc. Noi dung la khao sat chat luong cuoc song, khong phai
# huong dan dieu tri. Muon nhan lai thi phai xu ly khoang trang giua chu truoc.
    ("vi", "BacNinh-laser-seo-mun", "https://syt.bacninh.gov.vn/documents/184573/84486904/61.+Nguy%E1%BB%85n+Th%E1%BB%8B+Qu%E1%BB%B3nh.pdf"),
    ("vi", "YHocTPHCM-2017", "https://tapchiyhoctphcm.vn/upload/2017/21%201Tap%2021-so%201-2017(84%20trang%20-16-02-17)%20(TTngay%205-6-17)/016.pdf"),
]

# File tai tay, script khong tu tai duoc: (lang, ten file day du, nguon, ghi chu)
MANUAL = [
    ("vi", "Quyết-định-4416-QĐ-BYT.pdf",
     "https://thuvienphapluat.vn/van-ban/The-thao-Y-te/Quyet-dinh-4416-QD-BYT-2023-Huong-dan-Chan-doan-va-dieu-tri-cac-benh-Da-lieu-590054.aspx",
     "QD 4416/QD-BYT 06/12/2023 - Huong dan chan doan va dieu tri cac benh Da lieu (474 trang, ban scan)"),
    ("vi", "Huong dan.doc",
     "https://kcb.vn/upload/2005611/20210723/Huong-dan-chan-doan-dieu-tri-Da-lieu.pdf",
     "Ban Word cua Huong dan chan doan dieu tri Da lieu (QD 75/QD-BYT 2015) - nguon chua xac minh chac chan"),
# BO 2026-07: "HƯỚNG_DẪN_ĐIỀU_TRỊ_MỤN_TRỨNG_CÁ.pdf" (slideshare, 36 trang scan).
# Ly do: nguon la ban upload SlideShare khong xac minh duoc, va la slide scan nen
# OCR bang phan loai ra rac ("XIN ONN;;_", "mmỂmWmWTTTTTT"). Chi dong gop 21 chunk,
# noi dung trung voi BYT-Da-lieu-2015 + AnGiang + dong thuan VJDV.
    ("en", "Skin Health and Disease - 2023 - Corcoran - Systematic review of clinical practice guidelines for acne vulgaris published.pdf",
     "https://eprints.soton.ac.uk/477073/1/Skin_Health_and_Disease_2023_Corcoran_Systematic_review_of_clinical_practice_guidelines_for_acne_vulgaris_published.pdf",
     "Corcoran et al. 2023, Skin Health Dis 3(4):ski2.240, doi 10.1002/ski2.240"),
    ("en", "The Journal of Dermatology - 2018 - Hayashi - Japanese Dermatological Association Guidelines  Guidelines for the treatment.pdf",
     "https://onlinelibrary.wiley.com/doi/10.1111/1346-8138.14355",
     "Hayashi et al. 2018, J Dermatol 45(8):898-935, doi 10.1111/1346-8138.14355 (Wiley, can quyen truy cap)"),
]

# Chuan Highwire: OJS, PMC, BMJ... deu khai bao san link PDF -> uu tien dung cai nay
CITATION_PDF = re.compile(
    r'<meta[^>]+name="citation_pdf_url"[^>]+content="([^"]+)"', re.I)
# Fallback: do tim href PDF trong trang.
# OJS: galley link la /article/view/<id>/<galley> -> doi sang /article/download/...
PDF_IN_PAGE = re.compile(
    r'href="([^"]*(?:/article/(?:download|view)/\d+/\d+[^"]*|\.pdf[^"]*|/pdf/[^"]+|pdf\?[^"]*))"',
    re.I)


def fetch(url, referer=None):
    # ponytail: nhieu nha xuat ban chi tra PDF khi co Referer la trang bai bao
    h = dict(UA, **({"Referer": referer} if referer else {}))
    with U.urlopen(U.Request(url, headers=h), timeout=90, context=CTX) as r:
        return r.read(), r.headers.get("Content-Type", ""), r.geturl()


def get_pdf(url):
    """Tra ve bytes PDF; neu url la trang HTML thi do tim link PDF dau tien."""
    data, ctype, final = fetch(url)
    if data[:4] == b"%PDF":
        return data
    if "html" not in ctype.lower():
        return None
    html = data.decode("utf-8", "ignore")
    for m in CITATION_PDF.findall(html) + PDF_IN_PAGE.findall(html):
        if "supplement" in m.lower() or m.startswith("#"):
            continue
        m = m.replace("/article/view/", "/article/download/")
        try:
            d = fetch(urljoin(final, m.replace("&amp;", "&")), referer=final)[0]
            if d[:4] == b"%PDF":
                return d
        except Exception:
            continue
    return None


def write_manifest():
    """Ghi manifest.json: moi file doc kem lang + nguon tai. Chi liet ke file co that."""
    docs = []
    for lang, name, url in URLS:
        docs.append((lang, name + ".pdf", url, ""))
    docs += list(MANUAL)
    out = []
    for lang, fn, url, note in docs:
        rel = f"{LANGDIR[lang]}/{fn}"
        p = os.path.join(OUT, LANGDIR[lang], fn)
        if not os.path.exists(p):
            continue
        e = {"file": rel, "lang": lang, "source_url": url,
             "bytes": os.path.getsize(p)}
        if note:
            e["note"] = note
        out.append(e)
    path = os.path.join(OUT, "manifest.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"manifest.json: {len(out)} file "
          f"({sum(d['lang'] == 'vi' for d in out)} vi / {sum(d['lang'] == 'en' for d in out)} en)")


def main():
    for d in LANGDIR.values():
        os.makedirs(os.path.join(OUT, d), exist_ok=True)
    ok = fail = skip = 0
    for lang, name, url in URLS:
        path = os.path.join(OUT, LANGDIR[lang], name + ".pdf")
        if os.path.exists(path) and os.path.getsize(path) > 10_000:
            print(f"[bo qua] {name}"); skip += 1; continue
        try:
            pdf = get_pdf(url)
            if not pdf:
                print(f"[KHONG THAY PDF] {name} -> mo tay: {url}"); fail += 1; continue
            open(path, "wb").write(pdf)
            print(f"[ok] {name}  {len(pdf)/1e6:.1f} MB")
            ok += 1
        except Exception as e:
            print(f"[LOI] {name}: {type(e).__name__} -> mo tay: {url}"); fail += 1
    print(f"\nXong: {ok} tai moi, {skip} da co, {fail} that bai. Thu muc: {OUT}")
    write_manifest()


def _check():
    assert PDF_IN_PAGE.findall('<a href="/index.php/vjdv/article/download/188/170">PDF</a>')
    assert PDF_IN_PAGE.findall('<a href="https://x.org/a/b.pdf?dl=1">pdf</a>')
    assert not PDF_IN_PAGE.findall('<a href="/article/view/188">HTML</a>')
    # galley OJS: bat duoc /view/<id>/<galley> va doi thanh /download/
    g = PDF_IN_PAGE.findall('<a class="obj_galley_link pdf" href="/index.php/vjdv/article/view/188/173">PDF</a>')
    assert g and g[0].replace("/article/view/", "/article/download/").endswith("/article/download/188/173")
    # meta citation_pdf_url (OJS/PMC), lay dung URL that
    assert CITATION_PDF.findall(
        '<meta name="citation_pdf_url" content="https://vjdv.vn/index.php/vjdv/article/download/188/168"/>'
    ) == ["https://vjdv.vn/index.php/vjdv/article/download/188/168"]
    assert CITATION_PDF.findall(
        '<meta name="citation_pdf_url" content="https://pmc.ncbi.nlm.nih.gov/articles/PMC8686441/pdf/a.pdf">'
    ) == ["https://pmc.ncbi.nlm.nih.gov/articles/PMC8686441/pdf/a.pdf"]
    print("regex ok")


if __name__ == "__main__":
    _check()
    main()
