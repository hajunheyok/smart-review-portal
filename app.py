"""
Smart Review Version Portal - Desktop App
Loads the portal HTML with real-time version data from a remote server.
"""
import sys
import os
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import webview


def get_bundle_dir():
    """Return the directory where bundled resources live (inside exe or script dir)."""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def get_app_dir():
    """Return the directory where the exe (or script) actually lives."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BUNDLE_DIR = get_bundle_dir()
APP_DIR = get_app_dir()
CACHE_DIR = os.path.join(tempfile.gettempdir(), "SmartReviewPortal")


def load_config():
    """Load config.json from the app directory (external, editable)."""
    config_path = os.path.join(APP_DIR, "config.json")
    if os.path.isfile(config_path):
        with open(config_path, encoding="utf-8") as f:
            return json.load(f)
    return {}


GITHUB_DATA_URL = "https://hajunheyok.github.io/smart-review-portal/portal-data.json"


def _fetch_url(url):
    """Fetch a single URL and return parsed JSON."""
    resp = requests.get(url, timeout=5, allow_redirects=True)
    resp.raise_for_status()
    return resp.json()


def detect_changes(old_data, new_data):
    """Compare old cache with new data and return list of changes."""
    if old_data is None:
        return []

    changes = []
    old_sw = {sw["id"]: sw for sw in old_data.get("software", [])}
    new_sw = {sw["id"]: sw for sw in new_data.get("software", [])}

    for sw_id, nsw in new_sw.items():
        osw = old_sw.get(sw_id)
        if osw is None:
            changes.append({"name": nsw["name"], "type": "new", "version": nsw.get("versionName", "")})
            continue
        if nsw.get("versionName", "") != osw.get("versionName", ""):
            changes.append({
                "name": nsw["name"], "type": "version",
                "old": osw.get("versionName", ""), "new": nsw.get("versionName", "")
            })
        elif nsw.get("link", "") != osw.get("link", ""):
            changes.append({"name": nsw["name"], "type": "link", "version": nsw.get("versionName", "")})
        elif nsw.get("changelog_ko", "") != osw.get("changelog_ko", ""):
            changes.append({"name": nsw["name"], "type": "changelog", "version": nsw.get("versionName", "")})

    for sw_id in old_sw:
        if sw_id not in new_sw:
            changes.append({"name": old_sw[sw_id]["name"], "type": "removed"})

    return changes


def fetch_remote_data(config):
    """
    Fetch portal-data.json from internal server and GitHub Pages in parallel.
    Returns whichever responds first successfully.
    """
    urls = [u for u in [config.get("data_url", ""), GITHUB_DATA_URL] if u]
    if not urls:
        return None

    with ThreadPoolExecutor(max_workers=len(urls)) as executor:
        futures = {executor.submit(_fetch_url, url): url for url in urls}
        for future in as_completed(futures):
            try:
                data = future.result()
                return data
            except Exception:
                continue

    return None


def save_cache(data):
    """Save fetched data to local cache for offline use."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, "portal-data-cache.json")
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_cache():
    """Load cached data from previous successful fetch."""
    cache_path = os.path.join(CACHE_DIR, "portal-data-cache.json")
    if os.path.isfile(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f)
    return None


def load_local_data():
    """Load portal-data.json from bundle (fallback)."""
    for search_dir in [APP_DIR, BUNDLE_DIR]:
        path = os.path.join(search_dir, "portal-data.json")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    return None


def load_html():
    """Read the HTML template from bundle."""
    for search_dir in [APP_DIR, BUNDLE_DIR]:
        path = os.path.join(search_dir, "Smart Review Version Portal.html")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                return f.read()
    raise FileNotFoundError("Smart Review Version Portal.html not found")


def main():
    config = load_config()

    old_cache = load_cache()
    data = fetch_remote_data(config)

    changes = []
    offline = False
    if data is not None:
        changes = detect_changes(old_cache, data)
        save_cache(data)
    else:
        offline = True
        data = old_cache
    if data is None:
        data = load_local_data()

    html = load_html()

    os.makedirs(CACHE_DIR, exist_ok=True)
    temp_path = os.path.join(CACHE_DIR, "portal.html")
    json_path = os.path.join(CACHE_DIR, "portal-data.json")
    update_path = os.path.join(CACHE_DIR, "update-info.json")

    with open(temp_path, "w", encoding="utf-8") as f:
        f.write(html)

    if data:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    with open(update_path, "w", encoding="utf-8") as f:
        json.dump({"changes": changes, "offline": offline}, f, ensure_ascii=False, indent=2)

    width = config.get("window_width", 1200)
    height = config.get("window_height", 850)

    webview.create_window(
        "Smart Review Version Portal",
        temp_path,
        width=width,
        height=height,
        x=100,
        y=50,
        resizable=True,
        min_size=(800, 600),
    )
    webview.start()


if __name__ == "__main__":
    main()
