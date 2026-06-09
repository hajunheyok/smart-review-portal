"""
Smart Review Version Portal - Desktop App
Loads the portal HTML with real-time version data from a remote server.
"""
import sys
import os
import json
import tempfile

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


def fetch_remote_data(config):
    """
    Fetch portal-data.json from the configured server URL.
    Returns parsed dict or None on failure.
    """
    data_url = config.get("data_url", "")

    if not data_url:
        return None

    try:
        resp = requests.get(data_url, timeout=10, allow_redirects=True)
        resp.raise_for_status()
        data = resp.json()
        save_cache(data)
        return data
    except Exception:
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

    # Priority: remote → cache → local file
    data = fetch_remote_data(config)
    if data is None:
        data = load_cache()
    if data is None:
        data = load_local_data()

    html = load_html()

    # Write HTML + JSON as separate files (injection breaks pywebview)
    os.makedirs(CACHE_DIR, exist_ok=True)
    temp_path = os.path.join(CACHE_DIR, "portal.html")
    json_path = os.path.join(CACHE_DIR, "portal-data.json")

    with open(temp_path, "w", encoding="utf-8") as f:
        f.write(html)

    if data:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

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
