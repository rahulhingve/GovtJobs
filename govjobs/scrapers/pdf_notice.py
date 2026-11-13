import io
import logging
import re
from typing import List, Optional
import httpx
import pdfplumber

logger = logging.getLogger("govjobs.scrapers.pdf_notice")

KEYWORDS = [
    r"\bb\.?tech\b",
    r"\bb\.?e\b",
    r"\bqualification\b",
    r"\beligibility\b",
    r"\bvacancy\b",
    r"\bvacancies\b",
    r"\blast\s+date\b",
    r"\bimportant\s+dates\b",
    r"\bpay\s+level\b",
    r"\bscale\s+of\s+pay\b",
    r"\bessential\s+qualification\b",
]

def extract_smart_pdf_text_from_bytes(pdf_bytes: bytes, max_pages: int = 12) -> str:
    """
    Extract smart pages from PDF bytes:
    - Always keeps pages 1 to 4
    - Plus every page containing key eligibility / dates / vacancy terms
    - Capped at max_pages (default 12)
    """
    selected_pages_text: List[str] = []
    selected_indices = set()

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        total_pages = len(pdf.pages)
        # Always select first 4 pages (or fewer if total_pages < 4)
        for i in range(min(4, total_pages)):
            selected_indices.add(i)

        # Always select the last page (often contains Important Dates and signature)
        if total_pages > 0:
            selected_indices.add(total_pages - 1)

        # Scan remaining pages for keywords
        for i in range(4, total_pages):
            if len(selected_indices) >= max_pages:
                break
            page_text = pdf.pages[i].extract_text() or ""
            page_lower = page_text.lower()
            for kw in KEYWORDS:
                if re.search(kw, page_lower):
                    selected_indices.add(i)
                    break

        sorted_indices = sorted(list(selected_indices))[:max_pages]
        for idx in sorted_indices:
            p = pdf.pages[idx]
            text = p.extract_text() or ""
            if text.strip():
                selected_pages_text.append(f"--- [PAGE {idx + 1}] ---\n{text.strip()}")

    return "\n\n".join(selected_pages_text)

def extract_pdf_from_url(url: str, verify_ssl: bool = True, timeout: float = 30.0) -> Optional[str]:
    """Download PDF in memory and extract smart pages without hosting or saving to disk."""
    try:
        with httpx.Client(timeout=timeout, verify=verify_ssl, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code == 200 and resp.content:
                return extract_smart_pdf_text_from_bytes(resp.content)
            else:
                logger.warning(f"Failed to download PDF {url}: status {resp.status_code}")
                return None
    except (httpx.ConnectError, httpx.RequestError) as e:
        # Fallback with verify=False for Indian Govt/PSU custom cert chains
        try:
            with httpx.Client(timeout=timeout, verify=False, follow_redirects=True) as client:
                resp = client.get(url)
                if resp.status_code == 200 and resp.content:
                    return extract_smart_pdf_text_from_bytes(resp.content)
        except Exception as e2:
            logger.error(f"Error fetching PDF {url} with verify=False: {e2}")
            return None
    except Exception as e:
        logger.error(f"Error fetching PDF {url}: {e}")
        return None
