"""
web_tools.py (Made with Claude)

Four building blocks:

1. duckduckgo_search   -> raw search results (list of dicts), NOT for the LLM.
                          Used internally by web_search / other functions.

2. web_search          -> Markdown search results FOR the LLM. The caller
                          (the model) picks how many results/pages it wants
                          via `max_results`.

3. web_search_url      -> fetch a URL and return readable text, but ONLY if
                          it's an HTML page. If the URL points to something
                          else (image, pdf, zip, ...) it returns an error
                          string telling you what it actually is, instead of
                          trying to parse it as a page.

4. download_web        -> just download a file URL to disk. No content-type
                          checks beyond picking a sane filename/extension.

Plus one convenience wrapper:

5. fetch_url           -> "smart" entry point. Looks at the URL's
                          Content-Type: if it's HTML, behaves like
                          web_search_url(); if it's anything else, downloads
                          it via download_web() and tells you it did so.
"""

import os
import mimetypes
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

if not os.path.isdir(".genus/search_history"):
    os.mkdir(".genus/search_history")


# ---------------------------------------------------------------------------
# 1. Raw search - not for the LLM, used internally / by other functions
# ---------------------------------------------------------------------------
def duckduckgo_search(query: str, max_results: int = 5) -> list:
    """Search DuckDuckGo and return raw results (list of dicts).

    This is the low-level function. It's not meant to be shown to the LLM
    directly -- `web_search` wraps it and formats the output instead.
    """
    try:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))
    except Exception as e:
        return [{"error": str(e)}]


# ---------------------------------------------------------------------------
# 2. web_search - for the LLM. Model chooses how many results ("pages").
# ---------------------------------------------------------------------------
def web_search(query: str, max_results: int = 20) -> str:
    """Search DuckDuckGo and return compact Markdown for the LLM.

    `max_results` is exposed as a normal parameter so the calling model can
    decide how many results ("pages") it wants back -- pass a bigger number
    for broader coverage, a smaller one for a quick single-fact lookup.
    """
    print("SYS: Searching...")
    results = duckduckgo_search(query, max_results=max_results)

    if not results:
        return "No search results."

    if results and "error" in results[0]:
        return f"Search failed: {results[0]['error']}"

    output = [f"# Search Results: {query}\n"]

    for i, item in enumerate(results, 1):
        title = item.get("title", "No title")
        url = item.get("href", "")
        snippet = item.get("body", "")

        output.append(
            f"""## {i}. {title}

**URL:** {url}

{snippet}
"""
        )

    output = "\n---\n".join(output)
    with open(".genus/search_history/"+query+".md","w",encoding="utf-8") as f:
        f.write(output)

    return output


# ---------------------------------------------------------------------------
# helper: figure out what a URL actually is before we commit to parsing it
# ---------------------------------------------------------------------------
def _head_or_get_content_type(url: str, timeout: int) -> tuple:
    """Return (content_type, response). Tries a lightweight HEAD first;
    falls back to GET if the server doesn't support/answer HEAD properly."""
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.head(url, timeout=timeout, headers=headers, allow_redirects=True)
        content_type = resp.headers.get("Content-Type", "")
        if content_type:
            return content_type.split(";")[0].strip().lower(), None
    except Exception:
        pass

    # HEAD failed or gave nothing useful -- do a real GET
    resp = requests.get(url, timeout=timeout, headers=headers, stream=True)
    resp.raise_for_status()
    content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
    return content_type, resp


# ---------------------------------------------------------------------------
# 3. web_search_url - only succeeds for HTML pages
# ---------------------------------------------------------------------------
def web_search_url(url: str, timeout: int = 15) -> str:
    """Fetch a URL and return its readable text content, but only if it's
    an HTML page. If the URL points to a non-HTML resource (image, PDF,
    zip, etc.) this returns an error string describing what it is instead
    of trying to parse it as a page.
    """
    print(f"SYS: Browsing {url}...")
    try:
        content_type, pending_resp = _head_or_get_content_type(url, timeout)
    except Exception as e:
        return f"Error fetching URL: {e}"

    if "text/html" not in content_type:
        return (
            f"Error: URL does not point to a webpage. "
            f"Detected content type: '{content_type or 'unknown'}'. "
            f"Use download_web() instead if you want to download this file."
        )

    try:
        resp = pending_resp if pending_resp is not None else requests.get(
            url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"}
        )
        resp.raise_for_status()
    except Exception as e:
        return f"Error fetching URL: {e}"

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    title = soup.title.string.strip() if (soup.title and soup.title.string) else url

    output = f"# {title}\n\n**URL:** {url}\n\n{text}"
    with open(".genus/search_history/"+url.removeprefix("https://")+".md","w") as f:
        f.write(output)

    return output


# ---------------------------------------------------------------------------
# 4. download_web - just download a file, no content-type gate
# ---------------------------------------------------------------------------
def download_web(url: str, save_dir: str = "downloads", timeout: int = 30) -> str:
    """Download the file at `url` into `save_dir`.

    Returns the saved file path on success, or an error message string.
    """
    print("SYS: Downloading...")
    try:
        resp = requests.get(
            url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"}, stream=True
        )
        resp.raise_for_status()
    except Exception as e:
        return f"Error downloading file: {e}"

    os.makedirs(save_dir, exist_ok=True)

    parsed = urlparse(url)
    filename = os.path.basename(parsed.path)
    if not filename:
        content_type = resp.headers.get("Content-Type", "").split(";")[0].strip()
        ext = mimetypes.guess_extension(content_type) or ""
        filename = "downloaded_file" + ext

    save_path = os.path.join(save_dir, filename)

    with open(save_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    return save_path


# ---------------------------------------------------------------------------
# 5. fetch_url - smart wrapper: page -> text, file -> download
# ---------------------------------------------------------------------------
def fetch_url(url: str, save_dir: str = "downloads", timeout: int = 15) -> str:
    """Look at what `url` points to and do the right thing automatically:

    - HTML page  -> return readable text (like web_search_url)
    - Anything else (image, pdf, zip, ...) -> download it (like
      download_web) and report where it was saved.
    """
    try:
        content_type, _ = _head_or_get_content_type(url, timeout)
    except Exception as e:
        return f"Error checking URL: {e}"

    if "text/html" in content_type:
        return web_search_url(url, timeout=timeout)

    saved_path = download_web(url, save_dir=save_dir, timeout=max(timeout, 30))
    if saved_path.startswith("Error"):
        return saved_path

    return (
        f"URL is not a webpage (content type: '{content_type or 'unknown'}'). "
        f"Downloaded file to: {saved_path}"
    )


if __name__ == "__main__":
    # Example usage
    result = web_search(input("Query: "), max_results=3)
    with open("result.md", "w", encoding="utf-8") as f:
        f.write(result)
    print(result)