# Phân tích Logic Crawl & Hướng dẫn Cấu hình cho Các Trang Mới

Dựa trên việc dùng browser tự động để phân tích 5 website được yêu cầu, dưới đây là logic crawl chi tiết bao gồm cách lấy link bài viết, cơ chế pagination, bộ chọn nội dung, khả năng yêu cầu JS, cũng như cách thêm chúng vào cấu hình `seed_sources.yaml` của crawler.

---

## 1. VITA Clinic
**Chủ đề:** Trị mụn
**URL phân tích:** `https://vitaclinic.vn/vi/blog/category/tri-mun`

- **Link Selector:** `h3 > a` hoặc `a.btn-view-more` (Bộ chọn dùng để lấy các link trỏ đến bài viết chi tiết).
- **Pagination Logic:** Sử dụng URL param, định dạng `?page=X`. (Ví dụ: `?page=2`).
- **Content Selector:** `div.content-blog` (Bao gồm toàn bộ nội dung bài viết).
- **Yêu cầu JS (Render):** Không bắt buộc. Trang có thể lấy SSR HTML bình thường.

### Cấu hình `seed_sources.yaml`
```yaml
- name: VitaClinic
  domain: vitaclinic.vn
  trust_level: medium
  language: vi
  js_render: false
  discovery:
    type: category
    start_urls:
    - https://vitaclinic.vn/vi/blog/category/tri-mun
    pagination_selector: a[href*='?page=']
    link_selector: h3 > a, a.btn-view-more
    filter_path_contains:
    - /vi/blog/
  content_selectors:
  - .content-blog
  max_pages: 500
  categories:
  - acne
  - treatment
  tags:
  - clinic
  - vietnamese
```

---

## 2. Báo Sức Khỏe Đời Sống
**Chủ đề:** Tìm kiếm với từ khóa "mụn"
**URL phân tích:** `https://suckhoedoisong.vn/tim-kiem.htm?keywords=m%E1%BB%A5n`

- **Link Selector:** `a.box-category-link-title`
- **Pagination Logic:** Sử dụng nút "Hiển thị thêm bài" (Load More) load ajax hoặc có thể dùng fallback tham số `?page=X`.
- **Content Selector:** `div.detail-content` (Nội dung bài viết) và `h1.detail-title` (Tiêu đề).
- **Yêu cầu JS (Render):** Có. Vì đây là trang tìm kiếm load động bài viết, cần bật js_render cho bước discovery.

### Cấu hình `seed_sources.yaml`
```yaml
- name: SucKhoeDoiSong
  domain: suckhoedoisong.vn
  trust_level: high
  language: vi
  js_render: true
  js_wait_until: networkidle
  discovery:
    type: category
    start_urls:
    - https://suckhoedoisong.vn/tim-kiem.htm?keywords=m%E1%BB%A5n
    # Hoặc có thể dùng type: search nếu crawler hỗ trợ
    pagination_selector: .load-more, a[href*='?page=']
    link_selector: a.box-category-link-title
    filter_path_contains:
    - /
  content_selectors:
  - .detail-content
  max_pages: 800
  categories:
  - news
  - health
  tags:
  - authoritative
  - vietnamese
```

---

## 3. Bệnh Viện Da Liễu Hà Nội
**Chủ đề:** Chuyên mục Mụn
**URL phân tích:** `https://dalieuhanoi.vn/mun`

- **Link Selector:** `a.plain`
- **Pagination Logic:** Nối trực tiếp URL path `/page/X` (Ví dụ: `https://dalieuhanoi.vn/mun/page/2`).
- **Content Selector:** `div.entry-content` (Nội dung) và `h1.entry-title` (Tiêu đề).
- **Yêu cầu JS (Render):** Không bắt buộc. Có thể crawl tĩnh.

### Cấu hình `seed_sources.yaml`
```yaml
- name: DaLieuHaNoi
  domain: dalieuhanoi.vn
  trust_level: high
  language: vi
  js_render: false
  discovery:
    type: category
    start_urls:
    - https://dalieuhanoi.vn/mun
    pagination_selector: a.next.page-numbers
    link_selector: a.plain
    filter_path_contains:
    - /
  content_selectors:
  - .entry-content
  max_pages: 500
  categories:
  - dermatology
  - acne
  tags:
  - hospital
  - authoritative
  - vietnamese
```

---

## 4. Bệnh Viện Đa Khoa Phương Đông
**Chủ đề:** Tin tức Da Liễu
**URL phân tích:** `https://benhvienphuongdong.vn/tin-tuc/da-lieu/?page=2`

- **Link Selector:** `a.smooth.hv-main-sp`
- **Pagination Logic:** Tham số URL `?page=X`.
- **Content Selector:** `div.content-detail` (Nội dung chính).
- **Yêu cầu JS (Render):** Không bắt buộc, HTML tĩnh.

### Cấu hình `seed_sources.yaml`
```yaml
- name: PhuongDongHospital
  domain: benhvienphuongdong.vn
  trust_level: medium
  language: vi
  js_render: false
  discovery:
    type: category
    start_urls:
    - https://benhvienphuongdong.vn/tin-tuc/da-lieu/
    pagination_selector: a[href*='?page=']
    link_selector: a.smooth.hv-main-sp
    filter_path_contains:
    - /tin-tuc/
  content_selectors:
  - .content-detail
  max_pages: 500
  categories:
  - dermatology
  - health
  tags:
  - hospital
  - vietnamese
```

---

## 5. MSD Manuals (Phiên bản chuyên gia)
**Chủ đề:** Tìm kiếm chuyên khoa về "mụn"
**URL phân tích:** `https://www.msdmanuals.com/vi/professional/searchresults?query=m%E1%BB%A5n&page=3&type=topic`

- **Link Selector:** `h3 > a` hoặc `a:has(h3)`
- **Pagination Logic:** Tham số URL `?page=X` trên URL hoặc nút Next có selector là `span[role="link"]`.
- **Content Selector:** `.Topic_topicContent` (Nội dung chính yếu).
- **Yêu cầu JS (Render):** Cực kỳ quan trọng (Có). Trang sử dụng CSR (ReactJS) để render ra kết quả tìm kiếm, cần phải đợi `networkidle`.

### Cấu hình `seed_sources.yaml`
```yaml
- name: MSDManuals-VI
  domain: msdmanuals.com
  trust_level: high
  language: vi
  js_render: true
  js_wait_until: networkidle
  js_timeout_ms: 60000
  discovery:
    type: category
    start_urls:
    - https://www.msdmanuals.com/vi/professional/searchresults?query=m%E1%BB%A5n&type=topic
    pagination_selector: span[role="link"][aria-label*="Next"], a[href*='page=']
    link_selector: h3 > a, a:has(h3)
    filter_path_contains:
    - /vi/professional/
  content_selectors:
  - .Topic_topicContent
  max_pages: 100
  categories:
  - dermatology
  - reference
  tags:
  - clinical
  - authoritative
  - vietnamese
```

---

## Hướng dẫn bổ sung vào Knowledge Base Pipeline
1. Sao chép các block YAML ở trên dán vào mảng `sources:` trong file `data/seed_sources.yaml`.
2. Kiểm tra lại thụt lề (indentation) sao cho khớp hoàn toàn với các sources đã có (thường thụt lề 2 spaces).
3. Đảm bảo crawler đã hỗ trợ `js_render: true` với `playwright` cho các site cần JS như *Sức khỏe đời sống* và *MSD Manuals*.
4. Lần chạy tiếp theo, các site này sẽ tự động được thu thập qua `discovery.type: category` và index vào vector db.
