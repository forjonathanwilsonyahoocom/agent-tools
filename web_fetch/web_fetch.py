import httpx
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin, urlsplit
import asyncio
from playwright.async_api import async_playwright
import trafilatura
import ipaddress
import socket

MAX_REDIRECTS = 5
TIMEOUT = httpx.Timeout(15.0, connect=5.0)
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


def validate_public_url(url: str) -> str:
    """Return a normalized HTTP(S) URL, or raise ValueError."""
    try:
        parts = urlsplit(url)
        port = parts.port  # Accessing this also validates malformed ports.
    except ValueError as exc:
        raise ValueError(f"Malformed URL: {exc}") from exc

    if parts.scheme.lower() not in {"http", "https"}:
        raise ValueError("Only http and https URLs are allowed.")
    if not parts.hostname:
        raise ValueError("URL must include a hostname.")
    if parts.username is not None or parts.password is not None:
        raise ValueError("URLs containing credentials are not allowed.")
    if port is not None and not (1 <= port <= 65535):
        raise ValueError("Invalid port.")

    host = parts.hostname.rstrip(".")
    if not host or "%" in host:
        # Reject empty host and scoped IPv6 zone identifiers.
        raise ValueError("Invalid hostname.")

    try:
        # Handles literal IPv4 and IPv6 addresses, including unusual forms
        # accepted by the standard library's IP parser.
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            answers = socket.getaddrinfo(
                host,
                port or (443 if parts.scheme.lower() == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            raise ValueError(f"Hostname did not resolve: {host}") from exc

        addresses = []
        for answer in answers:
            address = ipaddress.ip_address(answer[4][0])
            if address not in addresses:
                addresses.append(address)

    if not addresses:
        raise ValueError("Hostname has no usable IP addresses.")

    # Reject the entire hostname if even one answer is non-public.
    # is_global excludes private, loopback, link-local, reserved, etc.
    if any(not address.is_global for address in addresses):
        raise ValueError(f"Hostname resolves to a non-public IP: {host}")

    return url


def safe_get(url: str) -> httpx.Response:
    current = validate_public_url(url)

    with httpx.Client(
        follow_redirects=False,
        timeout=TIMEOUT,
        headers={"User-Agent": "Mozilla/5.0"},
        trust_env=False,  # Don't silently inherit proxy settings from env.
    ) as client:
        for hop in range(MAX_REDIRECTS + 1):
            # Revalidate on each hop; urljoin handles relative Location values.
            current = validate_public_url(current)
            response = client.get(current)

            if response.status_code not in REDIRECT_STATUSES:
                response.raise_for_status()
                return response

            location = response.headers.get("location")
            if not location:
                return response

            if hop == MAX_REDIRECTS:
                raise ValueError("Too many redirects.")

            current = urljoin(str(response.url), location)

    raise AssertionError("Unreachable")
    
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
        response = safe_get(url)
        html = response.text
        text = trafilatura.extract(
            html,
            output_format="markdown",
            include_tables=True,
            include_links=False,
        )
           
        if text and len(text.strip()) >= 200:
            return text.strip()
    except ValueError as e:
        print(f"phase 1 safe_get exits with {e}")
        return f"phase 1 safe_get exits with {e}"
    except AssertionError as e:
        print(f"phase 1 safe_get exits with {e}")
        return f"phase 1 safe_get exits with {e}"
    except Exception as e:
        print(e)
        print("phase 1 safe_get fails, trying phase 2")
        
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
        print("phase 2 trafilatura fetch fails")
        
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
