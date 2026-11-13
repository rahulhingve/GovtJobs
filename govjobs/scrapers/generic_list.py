import re
from typing import List, Optional, Dict
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from govjobs.scrapers.base import BaseScraper, NoticeItem

class GenericListScraper(BaseScraper):
    def __init__(self, selectors: Optional[Dict[str, str]] = None):
        self.selectors = selectors or {}

    def parse_list(self, html_content: str, base_url: str) -> List[NoticeItem]:
        soup = BeautifulSoup(html_content, "html.parser")
        items: List[NoticeItem] = []

        # 1. If explicit selectors configured
        row_sel = self.selectors.get("row")
        if row_sel:
            rows = soup.select(row_sel)
            if rows:
                for r in rows:
                    item = self._parse_row(r, base_url)
                    if item:
                        items.append(item)
                if items:
                    return items

        # 2. Intelligent Table Detection fallback
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            if len(rows) > 1:
                # Inspect rows
                for r in rows[1:]:
                    cells = r.find_all(["td", "th"])
                    if not cells:
                        continue
                    text_all = r.get_text(" ", strip=True)
                    if len(text_all) < 10:
                        continue

                    # Find links
                    links = r.find_all("a", href=True)
                    if not links:
                        continue

                    # Best title link
                    title = ""
                    url = base_url
                    pdf_url = None
                    for a in links:
                        href = a.get("href", "").strip()
                        abs_url = urljoin(base_url, href)
                        link_text = a.get_text(strip=True)
                        if href.lower().endswith(".pdf") or "pdf" in href.lower():
                            if not pdf_url:
                                pdf_url = abs_url
                        if len(link_text) > len(title):
                            title = link_text
                            url = abs_url

                    if not title:
                        title = cells[0].get_text(strip=True)

                    if title and len(title) > 3:
                        items.append(NoticeItem(
                            title=title,
                            url=url,
                            pdf_url=pdf_url,
                            raw_text=text_all
                        ))
                if items:
                    return items

        # 3. Fallback to anchor tags pointing to notices / PDFs
        for a in soup.find_all("a", href=True):
            href = a.get("href", "").strip()
            text = a.get_text(strip=True)
            if not text or len(text) < 5:
                continue
            abs_url = urljoin(base_url, href)
            is_pdf = href.lower().endswith(".pdf")
            if is_pdf or any(k in text.lower() for k in ["recruitment", "advertisement", "engineer", "advt", "notice"]):
                items.append(NoticeItem(
                    title=text,
                    url=abs_url,
                    pdf_url=abs_url if is_pdf else None,
                    raw_text=text
                ))

        return items

    def _parse_row(self, row, base_url: str) -> Optional[NoticeItem]:
        text_all = row.get_text(" ", strip=True)
        if len(text_all) < 5:
            return None

        title_sel = self.selectors.get("title")
        link_sel = self.selectors.get("link")
        pdf_sel = self.selectors.get("pdf")

        title = ""
        if title_sel:
            el = row.select_one(title_sel)
            if el:
                title = el.get_text(strip=True)

        url = base_url
        if link_sel:
            el = row.select_one(link_sel)
            if el and el.get("href"):
                url = urljoin(base_url, el.get("href"))

        pdf_url = None
        if pdf_sel:
            el = row.select_one(pdf_sel)
            if el and el.get("href"):
                pdf_url = urljoin(base_url, el.get("href"))

        # Fallback to inspecting any <a> in row
        generic_words = ["updated on", "click here", "download", "view", "pdf", "read more", "apply online", "details"]
        if not title or any(title.strip().lower().startswith(w) for w in generic_words):
            # Check if cells[0] or cells[1] has a much better descriptive post title
            cells = row.find_all(["td", "th"])
            if cells:
                for c in cells[:2]:
                    c_text = c.get_text(" ", strip=True)
                    if len(c_text) > 10 and not any(c_text.lower().startswith(w) for w in generic_words):
                        title = c_text
                        break

        if not title or url == base_url:
            if row.name == "a" and row.get("href"):
                url = urljoin(base_url, row.get("href"))
                if not title:
                    title = row.get_text(strip=True)
            else:
                links = row.find_all("a", href=True)
                for a in links:
                    href = a.get("href", "").strip()
                    abs_url = urljoin(base_url, href)
                    lt = a.get_text(strip=True)
                    if abs_url.lower().endswith(".pdf"):
                        pdf_url = abs_url
                    if len(lt) > len(title) and not any(lt.lower().startswith(w) for w in generic_words):
                        title = lt
                    if url == base_url:
                        url = abs_url

        if not title:
            title = text_all[:120]

        return NoticeItem(
            title=title,
            url=url,
            pdf_url=pdf_url,
            raw_text=text_all
        )
