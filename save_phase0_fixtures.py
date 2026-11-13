import asyncio
import os
from pathlib import Path
import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

FIXTURES_DIR = Path("tests/fixtures")
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

SOURCES = [
    {
        "id": "upsc",
        "name": "Union Public Service Commission (UPSC)",
        "category": "Central exams and boards",
        "level": "central",
        "sector": "civil_and_engineering_services",
        "url": "https://upsc.gov.in/recruitment/recruitment-advertisement",
        "type": "html_list",
        "verify_ssl": True,
        "needs_js": False,
    },
    {
        "id": "ssc",
        "name": "Staff Selection Commission (SSC)",
        "category": "Central exams and boards",
        "level": "central",
        "sector": "staff_selection",
        "url": "https://ssc.gov.in/notices",
        "type": "js_page",
        "verify_ssl": True,
        "needs_js": True,
    },
    {
        "id": "rrb_chennai",
        "name": "Railway Recruitment Board (RRB Chennai)",
        "category": "Central exams and boards",
        "level": "central",
        "sector": "railways",
        "url": "https://www.rrbchennai.gov.in/",
        "type": "html_list",
        "verify_ssl": False, # Official NIC cert chain issue
        "needs_js": False,
    },
    {
        "id": "drdo_rac",
        "name": "DRDO Recruitment & Assessment Centre (RAC)",
        "category": "Central exams and boards",
        "level": "central",
        "sector": "defence_rd",
        "url": "https://rac.gov.in/",
        "type": "html_list",
        "verify_ssl": True,
        "needs_js": False,
    },
    {
        "id": "isro",
        "name": "Indian Space Research Organisation (ISRO)",
        "category": "Central exams and boards",
        "level": "central",
        "sector": "space",
        "url": "https://www.isro.gov.in/Careers.html",
        "type": "html_list",
        "verify_ssl": True,
        "needs_js": False,
    },
    {
        "id": "barc",
        "name": "Bhabha Atomic Research Centre (BARC)",
        "category": "Central exams and boards",
        "level": "central",
        "sector": "atomic_energy",
        "url": "https://recruit.barc.gov.in/barcrecruit/",
        "type": "html_list",
        "verify_ssl": True,
        "needs_js": False,
    },
    {
        "id": "powergrid",
        "name": "Power Grid Corporation of India (POWERGRID)",
        "category": "PSUs and CPSEs",
        "level": "psu",
        "sector": "power",
        "url": "https://www.powergrid.in/job-opportunities",
        "type": "html_list",
        "verify_ssl": True,
        "needs_js": False,
    },
    {
        "id": "ongc",
        "name": "Oil and Natural Gas Corporation (ONGC)",
        "category": "PSUs and CPSEs",
        "level": "psu",
        "sector": "oil_and_gas",
        "url": "https://ongcindia.com/web/eng/career",
        "type": "html_list",
        "verify_ssl": True,
        "needs_js": False,
    },
    {
        "id": "indian_navy",
        "name": "Indian Navy (Nausena Bharti)",
        "category": "Defence and paramilitary",
        "level": "defence",
        "sector": "defence",
        "url": "https://www.joinindiannavy.gov.in/en/page/current-events.html",
        "type": "html_list",
        "verify_ssl": True,
        "needs_js": False,
    },
    {
        "id": "coast_guard",
        "name": "Indian Coast Guard (ICG)",
        "category": "Defence and paramilitary",
        "level": "defence",
        "sector": "maritime_defence",
        "url": "https://joinindiancoastguard.cdac.in/",
        "type": "html_list",
        "verify_ssl": True,
        "needs_js": False,
    },
    {
        "id": "cochin_shipyard",
        "name": "Cochin Shipyard Limited (CSL)",
        "category": "Maritime",
        "level": "psu",
        "sector": "maritime",
        "url": "https://cochinshipyard.in/career",
        "type": "html_list",
        "verify_ssl": True,
        "needs_js": False,
    },
    {
        "id": "aai",
        "name": "Airports Authority of India (AAI)",
        "category": "Aviation",
        "level": "psu",
        "sector": "aviation",
        "url": "https://www.aai.aero/en/careers/recruitment",
        "type": "html_list",
        "verify_ssl": True,
        "needs_js": False,
    },
    {
        "id": "mppsc",
        "name": "Madhya Pradesh Public Service Commission (MPPSC)",
        "category": "State PSCs and selection boards",
        "level": "state",
        "state": "Madhya Pradesh",
        "sector": "state_psc",
        "url": "https://mppsc.mp.gov.in/advertisement",
        "type": "html_list",
        "verify_ssl": True,
        "needs_js": False,
    },
    {
        "id": "pspcl",
        "name": "Punjab State Power Corporation Limited (PSPCL)",
        "category": "State power utilities",
        "level": "state",
        "state": "Punjab",
        "sector": "power",
        "url": "https://pspcl.in/recruitment/",
        "type": "html_list",
        "verify_ssl": True,
        "needs_js": False,
    },
]

async def fetch_source(src):
    url = src["url"]
    name = src["name"]
    source_id = src["id"]
    verify_ssl = src["verify_ssl"]
    needs_js = src["needs_js"]
    fixture_path = FIXTURES_DIR / f"{source_id}.html"

    print(f"Fetching {name} [{source_id}]...")
    if needs_js:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=USER_AGENT, ignore_https_errors=not verify_ssl)
            page = await context.new_page()
            resp = await page.goto(url, wait_until="networkidle", timeout=35000)
            status = resp.status if resp else 200
            content = await page.content()
            await browser.close()
            fixture_path.write_text(content, encoding="utf-8")
            return {
                **src,
                "status": status,
                "length": len(content),
                "fixture": str(fixture_path),
                "mode": "playwright (chromium)",
                "note": "JS-rendered SPA (Angular/Next)",
            }
    else:
        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True, verify=verify_ssl, headers=HEADERS) as client:
            resp = await client.get(url)
            text = resp.text
            fixture_path.write_text(text, encoding="utf-8")
            note = "Plain HTTP (httpx)"
            if not verify_ssl:
                note += " - official NIC cert chain bypass (verify_ssl: false)"
            return {
                **src,
                "status": resp.status_code,
                "length": len(text),
                "fixture": str(fixture_path),
                "mode": "httpx",
                "note": note,
            }

async def main():
    results = []
    for s in SOURCES:
        try:
            res = await fetch_source(s)
            results.append(res)
            print(f"  -> SUCCESS ({res['status']}, {res['length']} bytes, mode: {res['mode']})")
        except Exception as e:
            print(f"  -> ERROR: {e}")
            results.append({
                **s,
                "status": "ERROR",
                "length": 0,
                "fixture": None,
                "mode": "failed",
                "note": str(e),
            })
        await asyncio.sleep(1) # Polite delay

    print("\n\n" + "="*80)
    print("PHASE 0 REALITY CHECK SUMMARY TABLE")
    print("="*80)
    header = f"{'Source ID':<15} | {'Status':<6} | {'Mode':<18} | {'SSL':<6} | {'Bytes':<8} | {'Official URL':<45} | Notes"
    print(header)
    print("-" * len(header))
    for r in results:
        ssl_str = "Strict" if r["verify_ssl"] else "Bypass"
        print(f"{r['id']:<15} | {str(r['status']):<6} | {r['mode']:<18} | {ssl_str:<6} | {r['length']:<8} | {r['url']:<45} | {r['note']}")

if __name__ == "__main__":
    asyncio.run(main())
