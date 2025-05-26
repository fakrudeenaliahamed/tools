from urllib.parse import urlparse, parse_qs
from time import sleep
import os
import requests
from bs4 import BeautifulSoup

html_file = "html/sample.html"
output_folder = "pdf"
os.makedirs(output_folder, exist_ok=True)

with open(html_file, "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f, "html.parser")

table = soup.find("table", id="result_list")
if not table:
    print("No table with id 'result_list' found.")
    exit(1)

links = table.find_all("a", href=True)

for link in links:
    url = link["href"]
    if url.lower().endswith(".pdf"):
        parsed_url = urlparse(url)
        filename = None
        # BSE: use Pname param
        if "bseindia.com" in parsed_url.netloc:
            pname = parse_qs(parsed_url.query).get("Pname") or parse_qs(
                parsed_url.query
            ).get("pname")
            if pname:
                filename = pname[0]
        # NSE: use last path segment
        if not filename:
            filename = os.path.basename(parsed_url.path)
        filepath = os.path.join(output_folder, filename)
        print(f"Downloading {url} -> {filepath}")
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            with open(filepath, "wb") as f:
                f.write(response.content)
        except Exception as e:
            print(f"Failed to download {url}: {e}")
        sleep(5)  # avoid rate limits
