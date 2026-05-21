# Fix Crawler Strategy for Dermatology/Acne Data

Expert analysis and fixed crawling strategies for the identified 5 Vietnamese websites.

## 1. Pharmacity (pharmacity.vn)

### Root Cause
- **Sitemap 404**: The documented sitemap `https://www.pharmacity.vn/sitemap_index.xml` returns a 404 status.
- **Dynamic Content**: Some listing elements are rendered or updated via JS, but the initial HTML contains the essential article/product links.

### Fixed Strategy
- **Entry Points**:
  - Articles: `https://www.pharmacity.vn/goc-suc-khoe/lam-dep` (Beauty/Skincare category)
  - Products: `https://www.pharmacity.vn/danh-muc-san-pham/cham-soc-ca-nhan/cham-soc-da-mat/kem-tri-mun` (Acne Care products)
- **HTML Selectors**:
  - Article Link: `a.line-clamp-2` or `a[href*="/goc-suc-khoe/"]`
  - Product Link: `a[href*="/san-pham/"]`
- **Pagination**: The site uses a "Xem thêm" (Load more) button. For a simple crawler, you can find the `?page=N` pattern or keep clicking the button in Playwright.

### Sample Code (Requests + BS4)
```python
import requests
from bs4 import BeautifulSoup

def crawl_pharmacity_articles():
    url = "https://www.pharmacity.vn/goc-suc-khoe/lam-dep"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    links = []
    for a in soup.select('a.line-clamp-2'):
        href = a.get('href')
        if href and href.startswith('http') == False:
            href = "https://www.pharmacity.vn" + href
        links.append(href)
    return list(set(links))
```

---

## 2. HelloBacsi (hellobacsi.com)

### Root Cause
- **Strict Selectors**: Crawler likely used generic card selectors. The site uses specific class names for its article cards (e.g., `article-card`).
- **Structure**: Articles are categorized under SEO-friendly paths.

### Fixed Strategy
- **Entry Points**:
  - `https://hellobacsi.com/da-lieu/`
  - `https://hellobacsi.com/da-lieu/tri-mun/`
- **HTML Selectors**:
  - Article Link: `article.article-card a` (specifically looking for the title link, often has classes like `HgbW6-m`).
- **Pagination**: Uses `?page=N` query parameter.

### Sample Code (Requests + BS4)
```python
import requests
from bs4 import BeautifulSoup

def crawl_hellobacsi():
    url = "https://hellobacsi.com/da-lieu/tri-mun/"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    links = []
    # Targeted selector for article cards
    for card in soup.select('article.article-card'):
        a = card.find('a')
        if a:
            links.append(a.get('href'))
    return links
```

---

## 3. Medlatec (medlatec.vn)

### Root Cause
- **Path Complexity**: Articles are organized by specialty IDs (e.g., `s107` for Dermatology). Missing this ID in the URL leads to 0 results.

### Fixed Strategy
- **Entry Point**: `https://medlatec.vn/tin-tuc/da-lieu-s107`
- **HTML Selectors**:
  - Article Link: `a[href*="/tin-tuc/"]` (within listing items, often sibling to `.post-image-container`).
- **Pagination**: Uses `?pagenumber=N`.

### Sample Code (Requests + BS4)
```python
import requests
from bs4 import BeautifulSoup

def crawl_medlatec():
    url = "https://medlatec.vn/tin-tuc/da-lieu-s107"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    links = []
    # Identify links that contain '/tin-tuc/' but are not the category link itself
    for a in soup.select('a[href*="/tin-tuc/"]'):
        href = a.get('href')
        if href and href != "/tin-tuc/da-lieu-s107":
            if href.startswith('/'):
                href = "https://medlatec.vn" + href
            links.append(href)
    return list(set(links))
```

---

## 4. BVDL-HCM (bvdl.org.vn)

### Root Cause
- **Old Structure**: The Ho Chi Minh Dermatology Hospital site uses a semi-legacy structure where news is hidden under multi-level paths.

### Fixed Strategy
- **Entry Point**: `https://bvdl.org.vn/cong-dong/n-4/tin-tuc-va-su-kien`
- **HTML Selectors**:
  - Primary Link: `a.news_infomation-item-title`
  - Banner Link: `a.news_banner_title`
- **Pagination**: Uses `?page=N`.

### Sample Code (Requests + BS4)
```python
import requests
from bs4 import BeautifulSoup

def crawl_bvdl_hcm():
    url = "https://bvdl.org.vn/cong-dong/n-4/tin-tuc-va-su-kien"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    links = []
    for a in soup.select('a.news_infomation-item-title'):
        links.append(a.get('href'))
    return links
```

---

## 5. BenhVienDa-HN (benhvienda.com)

### Root Cause
- **Domain Redirect**: `benhvienda.com` redirects to `benhvienaau.vn`. If the crawler is locked to the original domain, it finds nothing.
- **Lazy Loading**: Requires scrolling or direct access to paginated URLs.

### Fixed Strategy
- **Target Domain**: Use `benhvienaau.vn` directly.
- **Entry Points**:
  - `https://benhvienaau.vn/dieu-tri-da-va-laser/`
  - `https://benhvienaau.vn/kien-thuc-lam-dep/`
- **HTML Selectors**:
  - Article Link: `a.plain` (usually the title links within the `.post-item` blocks).
- **Pagination**: Uses standard WordPress style `/page/N/`.

### Sample Code (Requests + BS4)
```python
import requests
from bs4 import BeautifulSoup

def crawl_benhvienda_hn():
    url = "https://benhvienaau.vn/dieu-tri-da-va-laser/"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    links = []
    # The links are often classes named 'plain' for titles
    for a in soup.select('a.plain'):
        links.append(a.get('href'))
    return list(set(links))
```
