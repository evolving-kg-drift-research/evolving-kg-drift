import re
import requests

URLS = [
    "https://tuoitre.vn/robots.txt",
    "https://tuoitre.vn/sitemaps/index.rss",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/128 Safari/537.36"
    )
}

for url in URLS:
    print("\n" + "=" * 80)
    print("URL:", url)

    try:
        r = requests.get(
            url,
            headers=HEADERS,
            timeout=30,
        )

        print("STATUS:", r.status_code)

        text = r.text

        links = sorted(
            set(
                re.findall(
                    r"https?://[^\s<>\"]+",
                    text,
                )
            )
        )

        print("FOUND LINKS:", len(links))

        for link in links:
            if (
                "sitemap" in link.lower()
                or ".xml" in link.lower()
                or ".rss" in link.lower()
            ):
                print(link)

    except Exception as exc:
        print(
            "ERROR:",
            type(exc).__name__,
            str(exc),
        )