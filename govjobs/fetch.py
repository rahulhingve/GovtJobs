import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Tuple
from urllib.parse import urlparse
import urllib.robotparser

import httpx
from playwright.async_api import async_playwright

from govjobs.config import get_config

logger = logging.getLogger("govjobs.fetch")

IST = timezone(timedelta(hours=5, minutes=30))

class FetchResult:
    def __init__(
        self,
        url: str,
        status_code: int,
        content: str,
        from_cache: bool = False,
        used_playwright: bool = False,
        error: Optional[str] = None
    ):
        self.url = url
        self.status_code = status_code
        self.content = content
        self.from_cache = from_cache
        self.used_playwright = used_playwright
        self.error = error

    @property
    def ok(self) -> bool:
        return self.status_code == 200 and not self.error

class PoliteFetcher:
    def __init__(
        self,
        cache_dir: Optional[str] = None,
        user_agent: Optional[str] = None,
        domain_delay: Optional[float] = None,
        timeout: Optional[float] = None,
    ):
        cfg = get_config()
        self.cache_dir = Path(cache_dir or cfg.data_dir / "cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.user_agent = user_agent or cfg.user_agent
        self.domain_delay = domain_delay if domain_delay is not None else cfg.request_delay_seconds
        self.timeout = timeout if timeout is not None else cfg.request_timeout_seconds
        self.last_domain_request: Dict[str, float] = {}
        self.robots_cache: Dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}

    def _get_cache_path(self, url: str) -> Path:
        today_str = datetime.now(IST).strftime("%Y-%m-%d")
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
        return self.cache_dir / f"{today_str}_{url_hash}.json"

    def _wait_for_domain(self, domain: str):
        now = time.time()
        if domain in self.last_domain_request:
            elapsed = now - self.last_domain_request[domain]
            if elapsed < self.domain_delay:
                time.sleep(self.domain_delay - elapsed)
        self.last_domain_request[domain] = time.time()

    def check_robots(self, url: str, verify_ssl: bool = True) -> bool:
        """Check if robots.txt permits crawling this URL. Permissive if robots.txt unreachable."""
        parsed = urlparse(url)
        domain = parsed.netloc
        if domain not in self.robots_cache:
            rp = urllib.robotparser.RobotFileParser()
            robots_url = f"{parsed.scheme}://{domain}/robots.txt"
            try:
                with httpx.Client(timeout=10.0, verify=verify_ssl, headers={"User-Agent": self.user_agent}) as client:
                    resp = client.get(robots_url)
                    if resp.status_code == 200:
                        rp.parse(resp.text.splitlines())
                        self.robots_cache[domain] = rp
                    else:
                        self.robots_cache[domain] = None
            except Exception:
                self.robots_cache[domain] = None

        rp = self.robots_cache[domain]
        if rp:
            allowed = rp.can_fetch(self.user_agent, url)
            if not allowed:
                logger.warning(f"Robots.txt disallows fetching {url}")
                return False
        return True

    def fetch(
        self,
        url: str,
        verify_ssl: bool = True,
        use_cache: bool = True,
        force_playwright: bool = False,
    ) -> FetchResult:
        cache_file = self._get_cache_path(url)
        if use_cache and cache_file.exists():
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                return FetchResult(
                    url=data["url"],
                    status_code=data["status_code"],
                    content=data["content"],
                    from_cache=True,
                    used_playwright=data.get("used_playwright", False),
                    error=data.get("error")
                )
            except Exception as e:
                logger.debug(f"Failed to read cache for {url}: {e}")

        # Check robots
        if not self.check_robots(url, verify_ssl=verify_ssl):
            return FetchResult(url=url, status_code=403, content="", error="Disallowed by robots.txt")

        parsed = urlparse(url)
        domain = parsed.netloc
        self._wait_for_domain(domain)

        if not verify_ssl:
            logger.warning(f"[SSL WARNING] verify_ssl is disabled for {url}")

        if force_playwright:
            return self._fetch_playwright(url, verify_ssl=verify_ssl, cache_file=cache_file)

        # Try plain HTTP first
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        retries = 2
        for attempt in range(retries + 1):
            try:
                with httpx.Client(
                    timeout=self.timeout,
                    verify=verify_ssl,
                    follow_redirects=True,
                    headers=headers
                ) as client:
                    resp = client.get(url)
                    content = resp.text
                    
                    # If empty body and status 200, it might be an SPA shell -> fall back to Playwright
                    if resp.status_code == 200 and len(content.strip()) < 500:
                        logger.info(f"Page body is small/empty for {url}, falling back to Playwright")
                        return self._fetch_playwright(url, verify_ssl=verify_ssl, cache_file=cache_file)

                    res = FetchResult(
                        url=str(resp.url),
                        status_code=resp.status_code,
                        content=content,
                        from_cache=False,
                        used_playwright=False
                    )
                    self._save_cache(cache_file, res)
                    return res
            except httpx.ConnectError as e:
                if attempt == retries:
                    err = f"ConnectError: {e}"
                    logger.error(f"Fetch failed for {url}: {err}")
                    return FetchResult(url=url, status_code=0, content="", error=err)
            except httpx.TimeoutException as e:
                if attempt == retries:
                    err = f"Timeout ({self.timeout}s): {e}"
                    logger.error(f"Fetch timed out for {url}: {err}")
                    return FetchResult(url=url, status_code=0, content="", error=err)
            except Exception as e:
                if attempt == retries:
                    err = f"{type(e).__name__}: {e}"
                    logger.error(f"Fetch error for {url}: {err}")
                    return FetchResult(url=url, status_code=0, content="", error=err)
            time.sleep(1.0 * (attempt + 1))

        return FetchResult(url=url, status_code=0, content="", error="Unknown fetch failure")

    def _fetch_playwright(self, url: str, verify_ssl: bool, cache_file: Path) -> FetchResult:
        async def _run():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent=self.user_agent,
                    ignore_https_errors=not verify_ssl
                )
                page = await context.new_page()
                resp = await page.goto(url, wait_until="networkidle", timeout=int(self.timeout * 1000))
                status = resp.status if resp else 200
                content = await page.content()
                await browser.close()
                return status, content

        try:
            status, content = asyncio.run(_run())
            res = FetchResult(
                url=url,
                status_code=status,
                content=content,
                from_cache=False,
                used_playwright=True
            )
            self._save_cache(cache_file, res)
            return res
        except Exception as e:
            err = f"Playwright error: {e}"
            logger.error(f"Playwright fetch failed for {url}: {err}")
            return FetchResult(url=url, status_code=0, content="", used_playwright=True, error=err)

    def fetch_pdf_text(self, url: str, verify_ssl: bool = True, use_cache: bool = True) -> Optional[str]:
        """
        Download PDF into memory and extract text using smart page selection.
        Respects robots.txt, domain delay, retries, and caches extracted text.
        Never saves the raw PDF to disk.
        """
        from govjobs.scrapers.pdf_notice import extract_smart_pdf_text_from_bytes

        pdf_cache_dir = self.cache_dir / "pdf"
        pdf_cache_dir.mkdir(parents=True, exist_ok=True)
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
        cache_file = pdf_cache_dir / f"{url_hash}.txt"

        if use_cache and cache_file.exists():
            try:
                return cache_file.read_text(encoding="utf-8")
            except Exception:
                pass

        if not self.check_robots(url, verify_ssl=verify_ssl):
            logger.warning(f"Robots.txt disallows fetching PDF {url}")
            return None

        parsed = urlparse(url)
        self._wait_for_domain(parsed.netloc)

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/pdf,*/*;q=0.8",
        }

        for attempt in range(3):
            try:
                with httpx.Client(timeout=self.timeout, verify=verify_ssl, follow_redirects=True, headers=headers) as client:
                    resp = client.get(url)
                    if resp.status_code == 200 and resp.content:
                        text = extract_smart_pdf_text_from_bytes(resp.content)
                        if text:
                            try:
                                cache_file.write_text(text, encoding="utf-8")
                            except Exception:
                                pass
                        return text
                    else:
                        logger.warning(f"Failed to fetch PDF {url}: status {resp.status_code}")
                        return None
            except Exception as e:
                if attempt == 2:
                    logger.error(f"Error fetching PDF {url}: {e}")
                    return None
                time.sleep(1.0 * (attempt + 1))

        return None

    def _save_cache(self, cache_file: Path, result: FetchResult):
        try:
            data = {
                "url": result.url,
                "status_code": result.status_code,
                "content": result.content,
                "used_playwright": result.used_playwright,
                "error": result.error,
                "cached_at": datetime.now(timezone.utc).isoformat()
            }
            cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.debug(f"Failed to write cache to {cache_file}: {e}")
