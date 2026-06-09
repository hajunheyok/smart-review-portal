"""
Smart Review Version Portal - Desktop App
Loads the portal HTML with real-time version data from a remote server.
"""
import sys
import os
import json
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import webview

APP_VERSION = "1.0.0"

FALLBACK_SITES = [
    {"code": "KYK", "name": "Korea"},
    {"code": "KYA", "name": "Americas"},
    {"code": "KYA-MX", "name": "Mexico"},
    {"code": "JKY", "name": "Japan"},
    {"code": "KYSEA", "name": "Southeast Asia"},
    {"code": "KYV", "name": "Vietnam"},
    {"code": "KYE", "name": "Europe"},
    {"code": "KYC", "name": "China"},
    {"code": "KYTW", "name": "Taiwan"},
    {"code": "AES", "name": "HQ"},
]


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


def save_config(config):
    config_path = os.path.join(APP_DIR, "config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def send_event(config, action, sw=None):
    data_url = config.get("data_url", "")
    if not data_url:
        return
    base = data_url.rsplit("/", 1)[0]
    url = base + "/api/event"
    body = {"site": config.get("site", ""), "action": action}
    if sw:
        body["sw"] = sw
    try:
        requests.post(url, json=body, timeout=3)
    except Exception:
        pass




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


def _version_tuple(v):
    """Convert version string like '1.2.3' to tuple (1, 2, 3) for comparison."""
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except (ValueError, AttributeError):
        return (0,)


def check_app_update(data):
    """
    Check if a newer app version is available and download it.
    Returns dict with update info or None.
    """
    remote_ver = data.get("app_version", "")
    download_url = data.get("app_download_url", "")
    if not remote_ver or not download_url:
        return None

    if _version_tuple(remote_ver) <= _version_tuple(APP_VERSION):
        return None

    update_exe = os.path.join(APP_DIR, "_update.exe")
    if os.path.isfile(update_exe):
        return {"app_update": True, "new_version": remote_ver}

    try:
        resp = requests.get(download_url, timeout=60, stream=True)
        resp.raise_for_status()
        tmp_path = update_exe + ".tmp"
        with open(tmp_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
        os.replace(tmp_path, update_exe)
        return {"app_update": True, "new_version": remote_ver}
    except Exception:
        if os.path.isfile(update_exe + ".tmp"):
            try:
                os.remove(update_exe + ".tmp")
            except OSError:
                pass
        return None


def apply_pending_update():
    """
    If _update.exe exists from a previous download, create updater.bat and run it.
    Returns True if update is being applied (caller should exit).
    """
    update_exe = os.path.join(APP_DIR, "_update.exe")
    if not os.path.isfile(update_exe):
        return False

    if getattr(sys, "frozen", False):
        exe_path = sys.executable
    else:
        return False

    bat_path = os.path.join(APP_DIR, "_updater.bat")
    bat_content = f"""@echo off
timeout /t 2 /nobreak >nul
move /y "{update_exe}" "{exe_path}"
start "" "{exe_path}"
del "%~f0"
"""
    with open(bat_path, "w", encoding="ascii") as f:
        f.write(bat_content)

    subprocess.Popen(
        [bat_path],
        shell=True,
        creationflags=0x08000000,  # CREATE_NO_WINDOW
    )
    return True


class AppApi:
    """js_api for pywebview — allows HTML to trigger app restart and site selection."""

    def restart_for_update(self):
        if apply_pending_update():
            os._exit(0)

    def set_site(self, site):
        config = load_config()
        config["site"] = site
        save_config(config)
        threading.Thread(
            target=send_event, args=(config, "launch"), daemon=True
        ).start()


def load_html():
    """Read the HTML template from bundle."""
    for search_dir in [APP_DIR, BUNDLE_DIR]:
        path = os.path.join(search_dir, "Smart Review Version Portal.html")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                return f.read()
    raise FileNotFoundError("Smart Review Version Portal.html not found")


def main():
    if apply_pending_update():
        sys.exit(0)

    config = load_config()

    old_cache = load_cache()
    data = fetch_remote_data(config)

    changes = []
    offline = False
    app_update_info = None
    if data is not None:
        changes = detect_changes(old_cache, data)
        save_cache(data)
        app_update_info = check_app_update(data)
    else:
        offline = True
        data = old_cache
    if data is None:
        data = load_local_data()

    need_site_select = not config.get("site")
    sites_list = (data or {}).get("sites", FALLBACK_SITES)

    # launch 이벤트 전송 (fire-and-forget) — site 설정 완료된 경우만
    if config.get("site"):
        threading.Thread(
            target=send_event, args=(config, "launch"), daemon=True
        ).start()

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

    update_info = {"changes": changes, "offline": offline, "app_version": APP_VERSION}
    if need_site_select:
        update_info["need_site_select"] = True
        update_info["sites"] = sites_list
    if app_update_info:
        update_info.update(app_update_info)
    with open(update_path, "w", encoding="utf-8") as f:
        json.dump(update_info, f, ensure_ascii=False, indent=2)

    width = config.get("window_width", 1200)
    height = config.get("window_height", 850)

    api = AppApi()
    webview.create_window(
        "Smart Review Version Portal",
        temp_path,
        js_api=api,
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
