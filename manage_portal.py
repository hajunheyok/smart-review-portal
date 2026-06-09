"""
manage_portal.py — Smart Review Version Portal management script.

Usage:
    python manage_portal.py                   # Full update (extract + translate)
    python manage_portal.py --extract-only    # Version extraction only
    python manage_portal.py --translate-only  # Translation only
    python manage_portal.py --html path.html  # Custom HTML path
"""
import sys
import io
if sys.stdout is not None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr is not None:
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import re
import os
import sys
import json
import shutil
import argparse
import subprocess
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
from urllib.request import urlopen, Request
from urllib.error import URLError

# ── Load .env from the script's own directory ─────────────────────────────────
_SCRIPT_DIR = Path(__file__).resolve().parent
_ENV_FILE = _SCRIPT_DIR / ".env"

try:
    from dotenv import load_dotenv
    load_dotenv(_ENV_FILE)
except ImportError:
    # Manually parse .env if python-dotenv is not installed
    if _ENV_FILE.exists():
        with open(_ENV_FILE, encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _, _v = _line.partition("=")
                    os.environ.setdefault(_k.strip(), _v.strip())

try:
    import anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False

# ── Default HTML path ─────────────────────────────────────────────────────────
DEFAULT_HTML = str(_SCRIPT_DIR / "index.html")


# ─────────────────────────────────────────────────────────────────────────────
#  HTML ↔ Python dict helpers
# ─────────────────────────────────────────────────────────────────────────────

def read_portal_data(html_path: str) -> tuple[dict, str]:
    """
    Read index.html and extract PORTAL_DATA as a Python dict.

    Returns (data_dict, full_html_text).
    Raises ValueError if PORTAL_DATA cannot be found or parsed.
    """
    with open(html_path, encoding="utf-8") as f:
        html = f.read()

    # Locate the PORTAL_DATA block. Supports both formats:
    #   var PORTAL_DATA = { ... };
    #   var PORTAL_DATA = window.__PORTAL_DATA || { ... };
    start_marker = "var PORTAL_DATA = {"
    start_idx = html.find(start_marker)
    if start_idx == -1:
        alt_marker = "var PORTAL_DATA = window.__PORTAL_DATA || {"
        start_idx = html.find(alt_marker)
        if start_idx == -1:
            raise ValueError("PORTAL_DATA block not found in HTML.")
        start_marker = alt_marker

    # Walk forward counting braces to find the matching closing brace.
    brace_count = 0
    end_idx = -1
    obj_start = start_idx + len(start_marker) - 1  # points to the opening '{'
    i = obj_start
    while i < len(html):
        ch = html[i]
        if ch == '{':
            brace_count += 1
        elif ch == '}':
            brace_count -= 1
            if brace_count == 0:
                end_idx = i  # index of the closing '}'
                break
        i += 1

    if end_idx == -1:
        raise ValueError("Could not find closing '}' for PORTAL_DATA.")

    # Confirm the ';' follows directly (possibly with whitespace/newline)
    after = html[end_idx + 1:end_idx + 3].strip()
    if not after.startswith(";"):
        raise ValueError("Expected ';' after closing '}' of PORTAL_DATA.")

    js_object = html[obj_start:end_idx + 1]

    data = _js_object_to_dict(js_object)
    return data, html


def _js_object_to_dict(js_text: str) -> dict:
    """
    Convert a JavaScript object literal to a Python dict.

    Extracts string literals into placeholders first, then quotes bare keys,
    then restores strings. This prevents regex from corrupting URLs/values.
    """
    text = js_text
    strings = []
    result = []
    i = 0
    while i < len(text):
        c = text[i]
        if c == '"':
            j = i + 1
            while j < len(text):
                if text[j] == '\\':
                    j += 2
                    continue
                if text[j] == '"':
                    break
                j += 1
            strings.append(text[i:j + 1])
            result.append(f'"__STRPH{len(strings) - 1}__"')
            i = j + 1
            continue
        if c == "'":
            j = i + 1
            while j < len(text):
                if text[j] == '\\':
                    j += 2
                    continue
                if text[j] == "'":
                    break
                j += 1
            strings.append('"' + text[i + 1:j].replace('"', '\\"') + '"')
            result.append(f'"__STRPH{len(strings) - 1}__"')
            i = j + 1
            continue
        if c == '/' and i + 1 < len(text) and text[i + 1] == '/':
            while i < len(text) and text[i] != '\n':
                i += 1
            continue
        result.append(c)
        i += 1

    text = ''.join(result)
    text = re.sub(r'(?<!["\w])(\b[A-Za-z_$][A-Za-z0-9_$]*)\s*:', r'"\1":', text)
    text = re.sub(r',\s*([\]}])', r'\1', text)

    for idx, s in enumerate(strings):
        text = text.replace(f'"__STRPH{idx}__"', s)

    try:
        return json.loads(text, strict=False)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse PORTAL_DATA as JSON: {exc}\n--- Normalised text (first 500 chars) ---\n{text[:500]}") from exc


def _dict_to_js_object(data: dict, indent: int = 2) -> str:
    """
    Convert a Python dict back to a JavaScript object literal.

    Rules:
      - Keys are unquoted (bare identifiers)
      - Values follow JSON rules except keys are bare
      - 2-space indentation to match original file
    """
    return _render_js_value(data, level=0, indent_size=indent)


def _render_js_value(value, level: int, indent_size: int) -> str:
    ind = " " * (indent_size * level)
    child_ind = " " * (indent_size * (level + 1))

    if isinstance(value, dict):
        if not value:
            return "{}"
        lines = ["{"]
        items = list(value.items())
        for idx, (k, v) in enumerate(items):
            comma = "," if idx < len(items) - 1 else ""
            rendered = _render_js_value(v, level + 1, indent_size)
            lines.append(f"{child_ind}{k}: {rendered}{comma}")
        lines.append(f"{ind}}}")
        return "\n".join(lines)

    elif isinstance(value, list):
        if not value:
            return "[]"
        lines = ["["]
        for idx, item in enumerate(value):
            comma = "," if idx < len(value) - 1 else ""
            rendered = _render_js_value(item, level + 1, indent_size)
            lines.append(f"{child_ind}{rendered}{comma}")
        lines.append(f"{ind}]")
        return "\n".join(lines)

    elif isinstance(value, bool):
        return "true" if value else "false"

    elif value is None:
        return "null"

    elif isinstance(value, (int, float)):
        return json.dumps(value)

    else:
        # String — JSON-encode (handles escaping, Unicode)
        return json.dumps(value, ensure_ascii=False)


def write_portal_data(html_path: str, html: str, data: dict) -> None:
    """
    Write updated PORTAL_DATA back into the HTML, replacing only the
    content between 'var PORTAL_DATA = ' and '};'.
    The Korean comment block above is preserved.
    """
    start_marker = "var PORTAL_DATA = {"
    start_idx = html.find(start_marker)
    if start_idx == -1:
        alt_marker = "var PORTAL_DATA = window.__PORTAL_DATA || {"
        start_idx = html.find(alt_marker)
        if start_idx == -1:
            raise ValueError("PORTAL_DATA block not found when writing.")
        start_marker = alt_marker

    # Find end (same brace-counting logic)
    brace_count = 0
    end_idx = -1
    obj_start = start_idx + len(start_marker) - 1
    i = obj_start
    while i < len(html):
        ch = html[i]
        if ch == '{':
            brace_count += 1
        elif ch == '}':
            brace_count -= 1
            if brace_count == 0:
                end_idx = i
                break
        i += 1

    if end_idx == -1:
        raise ValueError("Could not find closing '}' for PORTAL_DATA when writing.")

    # end_idx+1 should be ';'
    semicolon_idx = end_idx + 1

    data_for_html = {k: v for k, v in data.items() if k != "history"}
    new_js = _dict_to_js_object(data_for_html)
    # Preserve original prefix (e.g. "var PORTAL_DATA = window.__PORTAL_DATA || ")
    prefix = html[start_idx:obj_start]
    new_block = f"{prefix}{new_js};"

    updated_html = html[:start_idx] + new_block + html[semicolon_idx + 1:]

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(updated_html)


# ─────────────────────────────────────────────────────────────────────────────
#  Version name extraction
# ─────────────────────────────────────────────────────────────────────────────

_EXT_PATTERN = re.compile(
    r'\.(tar\.gz|tar\.bz2|tar\.xz|exe|msi|zip|7z|rar|dmg|pkg|deb|rpm)$',
    re.IGNORECASE
)


def extract_version_from_link(link: str) -> str | None:
    """
    Try to extract a meaningful filename (without extension) from a URL.

    Strategies tried in order:
      1. Last path segment of the URL path component.
      2. 'filename' query parameter.
      3. 'id' query parameter (OneDrive-style).
    Returns None if nothing useful is found.
    """
    if not link or not link.strip():
        return None

    parsed = urlparse(link)

    # Strategy 1: last path segment
    path_part = parsed.path.rstrip("/")
    if path_part:
        last_seg = unquote(path_part.split("/")[-1])
        cleaned = _EXT_PATTERN.sub("", last_seg)
        if cleaned and cleaned != last_seg and len(cleaned) > 2:
            return cleaned

    # Strategy 2: 'filename' query param
    qs = parse_qs(parsed.query)
    if "filename" in qs:
        fn = unquote(qs["filename"][0])
        cleaned = _EXT_PATTERN.sub("", fn)
        return cleaned if cleaned else None

    # Strategy 3: try the raw path segment even without recognised extension
    if path_part:
        last_seg = unquote(path_part.split("/")[-1])
        # Skip SharePoint-style opaque IDs (base64 blobs starting with IQ/EQ etc.)
        if re.match(r'^[A-Za-z]{2}[A-Za-z0-9_-]{20,}$', last_seg):
            return None
        # Only return if it looks like a real filename (has a dot or underscore)
        if ("." in last_seg or "_" in last_seg) and len(last_seg) > 4:
            cleaned = _EXT_PATTERN.sub("", last_seg)
            return cleaned if cleaned else None

    return None


def run_extract(data: dict) -> int:
    """
    Populate versionName for each software item from its link.
    Returns count of items successfully updated.
    """
    print("\n🔗 버전명 추출 중...")
    updated = 0
    for sw in data.get("software", []):
        name = sw.get("name", sw.get("id", "?"))
        link = sw.get("link", "")

        if not link:
            print(f"  — {name}: 링크 없음 (건너뜀)")
            continue

        version = extract_version_from_link(link)
        if version:
            existing = sw.get("versionName", "")
            if existing and existing == version:
                print(f"  — {name}: 변경 없음 ({version})")
            else:
                sw["versionName"] = version
                print(f"  ✅ {name}: {version}")
                updated += 1
        else:
            print(f"  ⚠️  {name}: 버전명 추출 실패 (불투명 URL, 건너뜀)")

    return updated


# ─────────────────────────────────────────────────────────────────────────────
#  Translation
# ─────────────────────────────────────────────────────────────────────────────

def translate_with_claude(text_ko: str, target_lang: str) -> str:
    """Translate Korean text to target_lang using Claude API."""
    if not text_ko or not text_ko.strip():
        return ""

    lang_names = {
        "en": "English",
        "zh": "Simplified Chinese",
        "ja": "Japanese",
        "es": "Spanish",
        "de": "German",
    }

    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Translate the following Korean text to {lang_names[target_lang]}. "
                    "This is a software changelog/notice for a manufacturing inspection system. "
                    "Keep technical terms (AOIGUI, ONNX, SROCV, SmartGate, etc.) as-is. "
                    "Return ONLY the translated text, nothing else.\n\n"
                    f"{text_ko}"
                ),
            }
        ],
    )
    return message.content[0].text.strip()


def _needs_translation(text_ko: str, existing_translation: str) -> bool:
    """
    Return True if translation is needed.
    We translate if:
      - text_ko is non-empty AND
      - the existing translation is empty  OR
      - we cannot tell if it matches (conservative: always re-translate when Korean changes).

    Note: We use a simple heuristic — if existing translation is non-empty we
    skip, to avoid unnecessary API calls. If the Korean text was edited the
    user should clear the existing translations to force a re-run.
    """
    if not text_ko or not text_ko.strip():
        return False
    if not existing_translation or not existing_translation.strip():
        return True
    # If Korean text and all translations are present, skip.
    return False


def run_translate(data: dict) -> int:
    """
    Translate notice_ko and each software's changelog_ko.
    Returns total number of translation calls made.
    """
    if not _ANTHROPIC_AVAILABLE:
        print("\n❌ anthropic 패키지가 설치되지 않았습니다.")
        print("   pip install anthropic python-dotenv")
        return 0

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or api_key == "your-api-key-here":
        print("\n❌ ANTHROPIC_API_KEY가 설정되지 않았습니다.")
        print(f"   {_ENV_FILE} 파일에 실제 API 키를 입력하세요.")
        return 0

    print("\n🌐 번역 중 (Claude API)...")
    total_calls = 0
    langs = ["en", "zh", "ja", "es", "de"]

    # ── Notice ────────────────────────────────────────────────────────────────
    notice_ko = data.get("notice_ko", "")
    needs_notice = any(
        _needs_translation(notice_ko, data.get(f"notice_{lang}", ""))
        for lang in langs
    )

    if needs_notice:
        translated_any = False
        for lang in langs:
            if _needs_translation(notice_ko, data.get(f"notice_{lang}", "")):
                data[f"notice_{lang}"] = translate_with_claude(notice_ko, lang)
                total_calls += 1
                translated_any = True
        if translated_any:
            print("  ✅ notice: 번역 완료")
    else:
        if notice_ko:
            print("  — notice: 이미 번역됨 (건너뜀)")
        else:
            print("  — notice: 내용 없음 (건너뜀)")

    # ── Software changelogs ────────────────────────────────────────────────────
    for sw in data.get("software", []):
        name = sw.get("name", sw.get("id", "?"))
        changelog_ko = sw.get("changelog_ko", "")

        if not changelog_ko or not changelog_ko.strip():
            print(f"  — {name}: changelog 없음 (건너뜀)")
            continue

        needs_sw = any(
            _needs_translation(changelog_ko, sw.get(f"changelog_{lang}", ""))
            for lang in langs
        )

        if not needs_sw:
            print(f"  — {name}: 이미 번역됨 (건너뜀)")
            continue

        translated_any = False
        for lang in langs:
            if _needs_translation(changelog_ko, sw.get(f"changelog_{lang}", "")):
                sw[f"changelog_{lang}"] = translate_with_claude(changelog_ko, lang)
                total_calls += 1
                translated_any = True

        if translated_any:
            print(f"  ✅ {name}: 번역 완료")

    return total_calls


# ─────────────────────────────────────────────────────────────────────────────
#  Change detection & history
# ─────────────────────────────────────────────────────────────────────────────

def detect_changes(old_data: dict, new_data: dict) -> list[dict]:
    """Compare two PORTAL_DATA dicts and return a list of change objects."""
    if not old_data:
        return []

    changes = []

    if old_data.get("notice_ko", "") != new_data.get("notice_ko", ""):
        changes.append({
            "name": "공지사항",
            "type": "notice",
            "old": old_data.get("notice_ko", ""),
            "new": new_data.get("notice_ko", ""),
        })

    old_sw = {sw["id"]: sw for sw in old_data.get("software", [])}
    new_sw = {sw["id"]: sw for sw in new_data.get("software", [])}

    for sw_id, nsw in new_sw.items():
        osw = old_sw.get(sw_id)
        if osw is None:
            changes.append({"name": nsw["name"], "type": "new", "old": "", "new": nsw.get("versionName", "")})
            continue
        if nsw.get("versionName", "") != osw.get("versionName", ""):
            changes.append({"name": nsw["name"], "type": "version",
                            "old": osw.get("versionName", ""), "new": nsw.get("versionName", "")})
        elif nsw.get("link", "") != osw.get("link", ""):
            changes.append({"name": nsw["name"], "type": "link", "old": "", "new": ""})
        elif nsw.get("changelog_ko", "") != osw.get("changelog_ko", ""):
            changes.append({"name": nsw["name"], "type": "changelog",
                            "old": osw.get("changelog_ko", ""), "new": nsw.get("changelog_ko", "")})

    for sw_id in old_sw:
        if sw_id not in new_sw:
            changes.append({"name": old_sw[sw_id]["name"], "type": "removed", "old": "", "new": ""})

    return changes


def save_history(data: dict, changes: list[dict]) -> None:
    """Append a history entry to data['history']. Caps at 30 entries."""
    if not changes:
        return

    from datetime import datetime
    now = datetime.now()

    entry = {
        "date": now.strftime("%Y-%m-%d"),
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "changes": changes,
    }

    history = data.get("history", [])
    history.insert(0, entry)
    data["history"] = history[:30]


# ─────────────────────────────────────────────────────────────────────────────
#  Deploy: Server + GitHub 동시 배포
# ─────────────────────────────────────────────────────────────────────────────

SERVER_URL = "http://10.4.10.140:9090/portal-data.json"
GH_EXE = r"C:\Program Files\GitHub CLI\gh.exe"
REPO_DIR = _SCRIPT_DIR


def deploy_to_server(data: dict) -> bool:
    """POST portal-data.json to the internal server."""
    print("\n📡 서버 배포 중 (10.4.10.140:9090)...")
    try:
        payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        req = Request(SERVER_URL, data=payload, method="POST")
        req.add_header("Content-Type", "application/json; charset=utf-8")
        with urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if result.get("status") == "updated":
                print("  ✅ 서버 업데이트 완료")
                return True
            print(f"  ⚠️  서버 응답: {result}")
            return False
    except URLError as e:
        print(f"  ❌ 서버 연결 실패: {e}")
        return False


def deploy_to_github(data: dict) -> bool:
    """Commit and push portal-data.json + index.html to GitHub."""
    print("\n🌐 GitHub 배포 중...")

    git_exe = shutil.which("git")
    if not git_exe:
        print("  ❌ git이 설치되어 있지 않습니다.")
        return False

    json_path = REPO_DIR / "portal-data.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    index_path = REPO_DIR / "index.html"
    src_html = REPO_DIR / "Smart Review Version Portal.html"
    if src_html.exists():
        shutil.copy2(src_html, index_path)

    def run_git(*args):
        result = subprocess.run(
            [git_exe] + list(args),
            cwd=str(REPO_DIR), capture_output=True, text=True, encoding="utf-8"
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()

    ok, out, _ = run_git("diff", "--quiet", "portal-data.json", "index.html")
    if ok:
        ok2, out2, _ = run_git("diff", "--cached", "--quiet")
        if ok2:
            print("  — 변경사항 없음 (건너뜀)")
            return True

    run_git("add", "portal-data.json", "index.html")
    ok, _, err = run_git("commit", "-m", "[update] portal-data 자동 업데이트")
    if not ok and "nothing to commit" in err:
        print("  — 변경사항 없음 (건너뜀)")
        return True
    if not ok:
        print(f"  ❌ git commit 실패: {err}")
        return False

    ok, _, err = run_git("push")
    if ok:
        print("  ✅ GitHub 배포 완료")
        return True
    else:
        print(f"  ❌ git push 실패: {err}")
        return False


def run_deploy(data: dict) -> None:
    """서버 + GitHub 동시 배포."""
    server_ok = deploy_to_server(data)
    github_ok = deploy_to_github(data)

    print("\n" + "=" * 50)
    print("  배포 결과")
    print("=" * 50)
    print(f"  서버 (10.4.10.140:9090):  {'✅ 성공' if server_ok else '❌ 실패'}")
    print(f"  GitHub Pages:             {'✅ 성공' if github_ok else '❌ 실패'}")
    print("=" * 50)


# ─────────────────────────────────────────────────────────────────────────────
#  CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smart Review Portal management script"
    )
    parser.add_argument(
        "--html",
        default=DEFAULT_HTML,
        help="Path to the HTML file (default: index.html next to this script)",
    )
    parser.add_argument(
        "--extract-only",
        action="store_true",
        help="Only extract version names from links; do not translate",
    )
    parser.add_argument(
        "--translate-only",
        action="store_true",
        help="Only translate Korean text; do not extract versions",
    )
    parser.add_argument(
        "--export-json",
        action="store_true",
        help="Export PORTAL_DATA to portal-data.json (for exe app)",
    )
    parser.add_argument(
        "--no-deploy",
        action="store_true",
        help="Skip auto-deploy to server and GitHub (deploy is ON by default)",
    )
    args = parser.parse_args()

    html_path = os.path.abspath(args.html)
    print(f"📂 HTML 파일: {html_path}")

    if not os.path.isfile(html_path):
        print(f"❌ 파일을 찾을 수 없습니다: {html_path}")
        sys.exit(1)

    # Read
    try:
        data, html = read_portal_data(html_path)
    except ValueError as exc:
        print(f"❌ 파싱 오류: {exc}")
        sys.exit(1)

    if args.export_json:
        json_path = os.path.join(os.path.dirname(html_path), "portal-data.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n✅ portal-data.json 저장 완료: {json_path}")
        print(f"   소프트웨어 {len(data.get('software', []))}개 항목 포함")
        return

    import copy
    old_data = copy.deepcopy(data)

    do_extract = not args.translate_only
    do_translate = not args.extract_only

    if do_extract:
        run_extract(data)

    if do_translate:
        run_translate(data)

    # Detect changes and record history
    changes = detect_changes(old_data, data)
    if changes:
        print(f"\n📋 변경 감지: {len(changes)}건")
        for c in changes:
            if c["type"] == "version":
                print(f"  🔄 {c['name']}: {c['old']} → {c['new']}")
            elif c["type"] == "new":
                print(f"  🆕 {c['name']}: 신규 추가")
            elif c["type"] == "removed":
                print(f"  🗑️  {c['name']}: 제거")
            else:
                print(f"  📝 {c['name']}: {c['type']} 변경")

        # Load existing history from portal-data.json and merge
        json_path = os.path.join(os.path.dirname(html_path), "portal-data.json")
        if os.path.isfile(json_path):
            with open(json_path, encoding="utf-8") as f:
                existing = json.load(f)
            data["history"] = existing.get("history", [])

        save_history(data, changes)
    else:
        print("\n— 변경사항 없음")
        # Preserve existing history
        json_path = os.path.join(os.path.dirname(html_path), "portal-data.json")
        if os.path.isfile(json_path):
            with open(json_path, encoding="utf-8") as f:
                existing = json.load(f)
            data["history"] = existing.get("history", [])

    # Write back (history stripped from HTML, kept in JSON)
    try:
        write_portal_data(html_path, html, data)
    except (ValueError, OSError) as exc:
        print(f"\n❌ 파일 저장 오류: {exc}")
        sys.exit(1)

    print("\n✅ HTML 파일 업데이트 완료!")

    # Deploy to server + GitHub (default ON)
    if not args.no_deploy:
        run_deploy(data)


if __name__ == "__main__":
    main()
