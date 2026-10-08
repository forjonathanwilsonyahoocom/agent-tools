import httpx
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import asyncio
from playwright.async_api import async_playwright
import trafilatura

def web_fetch(url: str) -> str:
    """Visits a specific URL found from a web search using a headless browser 
    to extract its main text. Use this tool ONLY after finding a trusted URL 
    from a web search when you need deeper information than the short snippet provided.
    
    Args:
        url: The absolute web address (including http/https).
    """
    # 1. SSRF Guardrails: Prevent local network scanning inside the Docker bridge
    parsed_url = urlparse(url)
    if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
        return "Error: Invalid URL protocol or missing host domain."
    
    if any(ip in parsed_url.netloc for ip in ["localhost", "127.0.0.1", "0.0.0.0"]):
        return "Error: Accessing internal container network addresses is prohibited."

    # Define an internal async function to cleanly wrap Playwright's async API
    async def _fetch():
        async with async_playwright() as p:
            # Launch Chromium with system sandboxing optimizations for Docker
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled", # Evade automated tracking flags
                    "--no-sandbox",                                 # Required for root execution inside Docker
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",                      # Use disk swap to avoid shared evidence engine crashes
                    "--disable-infobars"
                ]
            )
            
            # Establish baseline organic Windows Chrome fingerprint profile
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720},
                locale="en-US"
            )
            
            page = await context.new_page()
            
            # Inline JS variable injection to hide automation signatures
            await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            # Execute the request with search engine referer masking
            response = await page.goto(
                url, 
                timeout=15000, 
                wait_until="domcontentloaded",
                referer="https://google.com"
            )
            
            if not response:
                await browser.close()
                return "Error: Headless browser failed to establish a network connection."
                
            if response.status == 403:
                await browser.close()
                return "Error 403: Forbidden. The website blocked automated access, even via browser emulation."
            elif response.status == 404:
                await browser.close()
                return "Error 404: Webpage not found."

            # Brief delay to allow background cryptographic script challenges to clear (e.g. Cloudflare)
            await page.wait_for_timeout(3000)
            
            html_content = await page.content()
            await browser.close()
            return html_content

    try:
        html_content = trafilatura.fetch_url(url)
        text = trafilatura.extract(
                html_content,
                output_format="markdown",
                include_tables=True,
                include_links=False,
            )
            
        if text and len(text.strip()) >= 200:
            return text.strip()
            
    except Exception as e:
        print(e)
        print("phase 1 trafilatura fetch fails")
        
    try:
          
        html_content = asyncio.run(_fetch())
                
        text = trafilatura.extract(
                html_content,
                output_format="markdown",
                include_tables=True,
                include_links=False,
            )

        if text and len(text.strip()) >= 200:
            return text.strip()

        soup = BeautifulSoup(html_content, "html.parser")
        for node in soup(["script", "style", "noscript", "svg", "nav", "footer", "form"]):
            node.decompose()

        return " ".join(soup.stripped_strings)
        

    except Exception as e:
        return f"Error: Web fetch exception encountered during execution: {str(e)}"
        


print(web_fetch("https://pydantic.dev/docs/validation/latest/concepts/validators/"))
