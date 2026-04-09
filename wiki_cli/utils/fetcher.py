"""URL fetching and content extraction."""
from pathlib import Path


def fetch_url(url: str) -> tuple[str, str]:
    """Fetch URL and return (title, markdown_content)."""
    try:
        import trafilatura

        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            raise ValueError(f"Failed to download: {url}")

        result = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=True,
            output_format="markdown",
        )
        if not result:
            raise ValueError(f"Failed to extract content from: {url}")

        # Try to get title
        metadata = trafilatura.extract_metadata(downloaded)
        title = metadata.title if metadata and metadata.title else url

        return title, result

    except ImportError:
        raise ImportError(
            "trafilatura is required for URL fetching. "
            "Install it with: pip install trafilatura"
        )


def url_to_filename(url: str) -> str:
    """Convert a URL to a safe filename."""
    import re
    from urllib.parse import urlparse

    parsed = urlparse(url)
    # Use domain + path, sanitized
    name = f"{parsed.netloc}{parsed.path}".rstrip("/")
    name = re.sub(r"[^\w\-]", "-", name)
    name = re.sub(r"-+", "-", name).strip("-")
    return f"{name[:80]}.md"
