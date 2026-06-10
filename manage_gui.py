"""
Smart Review Version Portal — Management GUI
로컬 HTTP 서버 + 브라우저 기반 관리 도구. 소프트웨어 버전 정보 편집 + 원클릭 배포.
"""
import sys
import os
import json
import copy
import threading
import webbrowser
import socket
import urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

import manage_portal
from manage_portal import (
    read_portal_data,
    write_portal_data,
    run_extract,
    run_translate,
    detect_changes,
    save_history,
    deploy_to_server,
    deploy_to_github,
)

# exe 빌드 시 경로 보정: __file__ 대신 실행 파일 위치 기준
if getattr(sys, "frozen", False):
    _EXE_DIR = os.path.dirname(sys.executable)
    _p = __import__("pathlib").Path(_EXE_DIR)
    manage_portal._SCRIPT_DIR = _p
    manage_portal.REPO_DIR = _p
    manage_portal._ENV_FILE = _p / ".env"
    manage_portal.DEFAULT_HTML = str(_p / "index.html")

_SCRIPT_DIR = manage_portal._SCRIPT_DIR
DEFAULT_HTML = str(_SCRIPT_DIR / "Smart Review Version Portal.html")

ANALYTICS_SERVER = "http://10.4.10.140:9090"

# ── Shared state ─────────────────────────────────────────────────────────────
_data = None
_html = None
_html_path = os.path.abspath(DEFAULT_HTML)
_logs = []
_deploy_running = False
_deploy_done = False


def _load_data():
    global _data, _html
    _data, _html = read_portal_data(_html_path)
    json_path = os.path.join(os.path.dirname(_html_path), "portal-data.json")
    if os.path.isfile(json_path):
        with open(json_path, encoding="utf-8") as f:
            existing = json.load(f)
        _data["history"] = existing.get("history", [])


def _add_log(msg):
    _logs.append(msg)


def _run_deploy_thread():
    global _deploy_running, _deploy_done
    _deploy_running = True
    _deploy_done = False
    try:
        old_data = copy.deepcopy(_data)

        _add_log("🔗 버전명 추출 중...")
        count = run_extract(_data)
        _add_log(f"  → {count}개 항목 추출 완료")

        _add_log("🌐 번역 중 (Claude API)...")
        t_count = run_translate(_data)
        _add_log(f"  → {t_count}회 번역 호출 완료")

        changes = detect_changes(old_data, _data)
        if changes:
            _add_log(f"📋 변경 감지: {len(changes)}건")
            json_path = os.path.join(os.path.dirname(_html_path), "portal-data.json")
            if os.path.isfile(json_path):
                with open(json_path, encoding="utf-8") as f:
                    existing = json.load(f)
                _data["history"] = existing.get("history", [])
            save_history(_data, changes)
        else:
            _add_log("— 변경사항 없음")
            json_path = os.path.join(os.path.dirname(_html_path), "portal-data.json")
            if os.path.isfile(json_path):
                with open(json_path, encoding="utf-8") as f:
                    existing = json.load(f)
                _data["history"] = existing.get("history", [])

        _add_log("💾 HTML 파일 저장 중...")
        write_portal_data(_html_path, _html, _data)

        src_html = os.path.join(_SCRIPT_DIR, "Smart Review Version Portal.html")
        if os.path.abspath(_html_path) != os.path.abspath(src_html):
            import shutil
            shutil.copy2(_html_path, src_html)

        _add_log("📡 서버 배포 중...")
        server_ok = deploy_to_server(_data)
        _add_log(f"  → 서버: {'✅ 성공' if server_ok else '❌ 실패'}")

        _add_log("🌐 GitHub 배포 중...")
        github_ok = deploy_to_github(_data)
        _add_log(f"  → GitHub: {'✅ 성공' if github_ok else '❌ 실패'}")

        result = "✅ 배포 완료!" if (server_ok or github_ok) else "❌ 배포 실패"
        _add_log(f"\n{'='*40}\n{result}\n{'='*40}")

    except Exception as e:
        _add_log(f"❌ 오류: {e}")
    finally:
        _deploy_running = False
        _deploy_done = True


# ── HTTP Handler ─────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _json_response(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            page = _build_html()
            body = page.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif self.path.startswith("/api/logs"):
            since = 0
            if "?since=" in self.path:
                try:
                    since = int(self.path.split("?since=")[1])
                except ValueError:
                    pass
            self._json_response({
                "logs": _logs[since:],
                "total": len(_logs),
                "running": _deploy_running,
                "done": _deploy_done,
            })

        elif self.path == "/api/data":
            self._json_response({"success": True, "data": _data})

        elif self.path == "/api/analytics_proxy":
            try:
                req = urllib.request.Request(ANALYTICS_SERVER + "/api/analytics")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    raw = resp.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            except Exception as e:
                self._json_response({"error": str(e), "events": []}, status=502)

        else:
            self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        body = json.loads(raw.decode("utf-8")) if raw else {}

        if self.path == "/api/save_item":
            for sw in _data.get("software", []):
                if sw["id"] == body["id"]:
                    sw["link"] = body.get("link", sw.get("link", ""))
                    sw["versionName"] = body.get("versionName", sw.get("versionName", ""))
                    sw["changelog_ko"] = body.get("changelog_ko", sw.get("changelog_ko", ""))
                    sw["date"] = body.get("date", sw.get("date", ""))
                    if body.get("changelog_ko", "") != sw.get("_prev_changelog_ko", ""):
                        sw["changelog_en"] = ""
                        sw["changelog_zh"] = ""
                        sw["changelog_ja"] = ""
                        sw["changelog_es"] = ""
                        sw["changelog_de"] = ""
                    break
            self._json_response({"success": True})

        elif self.path == "/api/save_notice":
            if body.get("notice_ko", "") != _data.get("notice_ko", ""):
                _data["notice_en"] = ""
                _data["notice_zh"] = ""
                _data["notice_ja"] = ""
                _data["notice_es"] = ""
                _data["notice_de"] = ""
            _data["notice_ko"] = body.get("notice_ko", _data.get("notice_ko", ""))
            _data["lastUpdated"] = body.get("lastUpdated", _data.get("lastUpdated", ""))
            _data["app_version"] = body.get("app_version", _data.get("app_version", ""))
            _data["app_download_url"] = body.get("app_download_url", _data.get("app_download_url", ""))
            if body.get("rollbackLabel_ko", "") != _data.get("rollbackLabel_ko", ""):
                _data["rollbackLabel_en"] = ""
                _data["rollbackLabel_zh"] = ""
                _data["rollbackLabel_ja"] = ""
                _data["rollbackLabel_es"] = ""
                _data["rollbackLabel_de"] = ""
            _data["rollbackLabel_ko"] = body.get("rollbackLabel_ko", _data.get("rollbackLabel_ko", ""))
            _data["rollbackLink"] = body.get("rollbackLink", _data.get("rollbackLink", ""))
            self._json_response({"success": True})

        elif self.path == "/api/extract":
            count = run_extract(_data)
            self._json_response({"success": True, "data": _data, "count": count})

        elif self.path == "/api/deploy":
            global _deploy_done
            if _deploy_running:
                self._json_response({"success": False, "error": "이미 배포 중"})
                return
            _logs.clear()
            _deploy_done = False
            thread = threading.Thread(target=_run_deploy_thread, daemon=True)
            thread.start()
            self._json_response({"success": True, "message": "배포 시작됨"})

        else:
            self.send_error(404)


# ── GUI HTML ─────────────────────────────────────────────────────────────────
def _build_html():
    data_json = json.dumps(_data, ensure_ascii=False)
    return r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>Portal Manager</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Segoe UI', -apple-system, sans-serif; background: #f0f2f5; color: #1e293b; }

  .header {
    background: linear-gradient(135deg, #4a5a8a 0%, #5e4d7a 50%, #7a5a6a 100%);
    padding: 20px 28px; display: flex; align-items: center; justify-content: space-between;
    position: sticky; top: 0; z-index: 100;
  }
  .header h1 { color: #fff; font-size: 20px; font-weight: 700; }
  .header-btns { display: flex; gap: 10px; }
  .btn {
    padding: 10px 22px; border-radius: 8px; font-size: 13px; font-weight: 600;
    cursor: pointer; border: none; transition: all 0.2s;
  }
  .btn-extract { background: rgba(255,255,255,0.2); color: #fff; border: 1px solid rgba(255,255,255,0.3); }
  .btn-extract:hover { background: rgba(255,255,255,0.35); }
  .btn-deploy { background: #fff; color: #4a5a8a; box-shadow: 0 2px 8px rgba(0,0,0,0.15); }
  .btn-deploy:hover { transform: scale(1.03); box-shadow: 0 4px 16px rgba(0,0,0,0.2); }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none !important; }

  /* === TABS === */
  .tab-bar {
    display: flex; gap: 4px; background: rgba(0,0,0,0.15); border-radius: 8px; padding: 3px;
  }
  .tab-btn {
    padding: 8px 20px; border-radius: 6px; font-size: 13px; font-weight: 600;
    cursor: pointer; border: none; background: transparent; color: rgba(255,255,255,0.65);
    transition: all 0.2s;
  }
  .tab-btn:hover { color: #fff; background: rgba(255,255,255,0.1); }
  .tab-btn.active { background: rgba(255,255,255,0.2); color: #fff; }
  .tab-content { display: none; }
  .tab-content.active { display: block; }

  .content { max-width: 960px; margin: 0 auto; padding: 24px 20px; }

  .section-title { font-size: 13px; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 1px; margin: 20px 0 10px; }

  .global-card {
    background: #fff; border-radius: 12px; padding: 20px 24px; margin-bottom: 16px;
    border: 1px solid #dde3eb; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }
  .field-row { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
  .field-row:last-child { margin-bottom: 0; }
  .field-label { font-size: 12px; font-weight: 600; color: #64748b; width: 110px; flex-shrink: 0; }
  .field-input {
    flex: 1; padding: 8px 12px; border: 1px solid #dde3eb; border-radius: 8px;
    font-size: 13px; font-family: inherit; transition: border-color 0.2s;
  }
  .field-input:focus { outline: none; border-color: #4a5a8a; box-shadow: 0 0 0 3px rgba(74,90,138,0.1); }
  textarea.field-input { resize: vertical; min-height: 50px; }

  .sw-card {
    background: #fff; border-radius: 12px; padding: 18px 22px; margin-bottom: 10px;
    border: 1px solid #dde3eb; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    transition: border-color 0.2s;
  }
  .sw-card:hover { border-color: #9ba4d4; }
  .sw-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
  .sw-name { font-size: 15px; font-weight: 700; color: #1e293b; display: flex; align-items: center; gap: 8px; }
  .sw-tag { font-size: 10px; padding: 3px 10px; border-radius: 20px; font-weight: 600; }
  .sw-tag.vision { background: #eef0f7; color: #4a4a8a; }
  .sw-tag.review { background: #e8f5ef; color: #2a6a5a; }
  .sw-tag.both { background: #f0edf7; color: #6a4a8a; }
  .sw-tag.tool { background: #f7f0e4; color: #8a6a2a; }

  .log-panel {
    position: fixed; bottom: 0; left: 0; right: 0; background: #1e293b;
    max-height: 200px; overflow-y: auto; transition: max-height 0.3s; z-index: 100;
  }
  .log-panel.collapsed { max-height: 36px; overflow: hidden; }
  .log-toggle {
    display: block; width: 100%; background: #334155; border: none;
    color: #94a3b8; font-size: 12px; padding: 8px 20px; text-align: left; cursor: pointer;
  }
  .log-toggle:hover { background: #3b4f6b; }
  .log-content { padding: 8px 20px 12px; }
  .log-line { font-size: 12px; font-family: 'Consolas', monospace; color: #94a3b8; padding: 2px 0; white-space: pre-wrap; }
  .log-line.success { color: #4ade80; }
  .log-line.error { color: #f87171; }

  .loading-overlay {
    display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.3); backdrop-filter: blur(2px); z-index: 200;
    align-items: center; justify-content: center;
  }
  .loading-overlay.active { display: flex; }
  .loading-box {
    background: #fff; border-radius: 16px; padding: 32px 40px; text-align: center;
    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
  }
  .loading-spinner {
    width: 40px; height: 40px; border: 4px solid #dde3eb; border-top-color: #4a5a8a;
    border-radius: 50%; animation: spin 0.8s linear infinite; margin: 0 auto 16px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .loading-text { font-size: 15px; font-weight: 600; color: #1e293b; }

  /* === DASHBOARD === */
  .dash-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }
  .stat-card {
    background: #fff; border-radius: 14px; padding: 20px 22px;
    border: 1px solid #dde3eb; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }
  .stat-card .stat-label { font-size: 11px; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; }
  .stat-card .stat-value { font-size: 32px; font-weight: 800; color: #1e293b; margin: 6px 0 2px; }
  .stat-card .stat-sub { font-size: 11px; color: #94a3b8; }

  .dash-section {
    background: #fff; border-radius: 14px; padding: 24px; margin-bottom: 20px;
    border: 1px solid #dde3eb; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }
  .dash-section h3 { font-size: 15px; font-weight: 700; color: #1e293b; margin-bottom: 16px; }

  .bar-chart { display: flex; flex-direction: column; gap: 10px; }
  .bar-row { display: flex; align-items: center; gap: 12px; }
  .bar-label { font-size: 12px; font-weight: 600; color: #475569; width: 90px; flex-shrink: 0; text-align: right; }
  .bar-track { flex: 1; height: 28px; background: #f1f5f9; border-radius: 6px; position: relative; overflow: hidden; }
  .bar-fill {
    height: 100%; border-radius: 6px; transition: width 0.6s ease;
    background: linear-gradient(90deg, #4a5a8a, #7a5a6a);
    display: flex; align-items: center; justify-content: flex-end; padding-right: 8px;
    font-size: 11px; font-weight: 700; color: #fff; min-width: 32px;
  }
  .bar-count { font-size: 12px; font-weight: 600; color: #64748b; width: 50px; text-align: right; flex-shrink: 0; }

  .trend-chart { display: flex; align-items: flex-end; gap: 4px; height: 180px; padding-top: 20px; }
  .trend-bar-wrap { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 4px; height: 100%; justify-content: flex-end; min-width: 0; }
  .trend-stack { width: 100%; display: flex; flex-direction: column-reverse; border-radius: 4px 4px 0 0; min-height: 2px; position: relative; }
  .trend-stack > .trend-seg:first-child { border-radius: 0 0 4px 4px; }
  .trend-stack > .trend-seg:last-child { border-radius: 4px 4px 0 0; }
  .trend-seg { width: 100%; min-height: 6px; position: relative; cursor: pointer; transition: filter 0.15s; }
  .trend-seg:hover { filter:brightness(1.2); z-index:50; }
  .trend-tip {
    display:none; position:absolute; bottom:calc(100% + 10px); left:50%; transform:translateX(-50%);
    background:#1e293b; color:#fff; padding:8px 14px; border-radius:8px; font-size:13px; font-weight:700;
    white-space:nowrap; z-index:9999; pointer-events:none; box-shadow:0 6px 20px rgba(0,0,0,0.35);
    letter-spacing: 0.3px;
  }
  .trend-tip::after {
    content:''; position:absolute; top:100%; left:50%; transform:translateX(-50%);
    border:6px solid transparent; border-top-color:#1e293b;
  }
  .trend-seg:hover .trend-tip { display:block; }
  .trend-label { font-size: 9px; color: #94a3b8; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
  .trend-count { font-size: 10px; font-weight: 700; color: #475569; }

  .period-tabs { display: flex; gap: 6px; margin-bottom: 16px; }
  .period-tab {
    padding: 6px 16px; border-radius: 8px; font-size: 12px; font-weight: 600;
    border: 1px solid #dde3eb; background: #f8f9fc; color: #64748b; cursor: pointer; transition: all 0.2s;
  }
  .period-tab:hover { border-color: #4a5a8a; color: #4a5a8a; }
  .period-tab.active { background: linear-gradient(135deg, #4a5a8a, #5e4d7a); color: #fff; border-color: transparent; }

  .trend-legend { display: flex; flex-wrap: wrap; gap: 8px 16px; margin-bottom: 14px; }
  .trend-legend-item { display: flex; align-items: center; gap: 5px; font-size: 11px; color: #475569; font-weight: 500; }
  .trend-legend-dot { width: 10px; height: 10px; border-radius: 3px; flex-shrink: 0; }

  .detail-table { width: 100%; border-collapse: collapse; }
  .detail-table th {
    text-align: left; padding: 10px 14px; font-size: 11px; font-weight: 700;
    color: #64748b; text-transform: uppercase; letter-spacing: 0.5px;
    border-bottom: 2px solid #e2e8f0; background: #f8fafc;
  }
  .detail-table td {
    padding: 12px 14px; font-size: 13px; color: #334155; border-bottom: 1px solid #f1f5f9;
  }
  .detail-table tr:hover td { background: #f8fafc; }
  .detail-table .num { font-family: 'Consolas', monospace; font-weight: 600; text-align: center; }

  .dash-refresh { font-size: 11px; color: #94a3b8; float: right; margin-top: -32px; }
  .dash-error { padding: 40px; text-align: center; color: #94a3b8; font-size: 14px; }
  .dash-loading { padding: 60px; text-align: center; color: #94a3b8; font-size: 14px; }

  .warn-yellow { background: #fef9c3 !important; }
  .warn-red { background: #fee2e2 !important; }
  .badge-inactive { display:inline-block; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:700; }
  .badge-yellow { background:#fbbf24; color:#78350f; }
  .badge-red { background:#ef4444; color:#fff; }
  .badge-green { background:#22c55e; color:#fff; }
  .badge-gray { background:#cbd5e1; color:#475569; }
</style>
</head>
<body>

<div class="header">
  <div style="display:flex;align-items:center;gap:20px;">
    <h1>🛠️ Portal Manager</h1>
    <div class="tab-bar">
      <button class="tab-btn active" onclick="switchTab('manage')">📋 관리</button>
      <button class="tab-btn" onclick="switchTab('dashboard')">📊 대시보드</button>
    </div>
  </div>
  <div class="header-btns" id="manageBtns">
    <button class="btn btn-extract" id="btnExtract" onclick="onExtract()">🔗 버전추출</button>
    <button class="btn btn-deploy" id="btnDeploy" onclick="onDeploy()">🚀 배포</button>
  </div>
</div>

<div class="tab-content active" id="tab-manage">
  <div class="content" id="content">
    <div class="section-title">전역 설정</div>
    <div class="global-card" id="globalCard"></div>

    <div class="section-title">소프트웨어 항목</div>
    <div id="swList"></div>
    <div style="height: 220px;"></div>
  </div>
</div>

<div class="tab-content" id="tab-dashboard">
  <div class="content">
    <div id="dashContent"><div class="dash-loading">📊 데이터 로딩 중...</div></div>
  </div>
</div>

<div class="log-panel collapsed" id="logPanel">
  <button class="log-toggle" onclick="toggleLog()">📋 로그 <span id="logCount">(0)</span></button>
  <div class="log-content" id="logContent"></div>
</div>

<div class="loading-overlay" id="loadingOverlay">
  <div class="loading-box">
    <div class="loading-spinner"></div>
    <div class="loading-text" id="loadingText">배포 중...</div>
  </div>
</div>

<script>
var portalData = """ + data_json + r""";
var logLines = 0;
var logPollTimer = null;
var logSince = 0;

function esc(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function getCatLabel(c) {
  return {vision:'Vision PC', review:'Review PC', both:'Vision+Review', tool:'Standalone'}[c] || c;
}

function api(path, body) {
  return fetch(path, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body || {})
  }).then(function(r) { return r.json(); });
}

function renderGlobal() {
  var d = portalData;
  document.getElementById('globalCard').innerHTML = [
    '<div class="field-row">',
    '  <span class="field-label">최종 업데이트</span>',
    '  <input type="date" class="field-input" id="fLastUpdated" value="' + esc(d.lastUpdated) + '" onchange="onGlobalChange()">',
    '</div>',
    '<div class="field-row">',
    '  <span class="field-label">공지사항 (KO)</span>',
    '  <textarea class="field-input" id="fNoticeKo" onchange="onGlobalChange()">' + esc(d.notice_ko) + '</textarea>',
    '</div>',
    '<div class="field-row">',
    '  <span class="field-label">앱 버전</span>',
    '  <input class="field-input" id="fAppVersion" value="' + esc(d.app_version || '') + '" onchange="onGlobalChange()" placeholder="예: 1.0.0" style="font-family:Consolas,monospace;font-size:12px;color:#4a4a8a;background:#f8f9fc;">',
    '</div>',
    '<div class="field-row">',
    '  <span class="field-label">앱 다운로드 URL</span>',
    '  <input class="field-input" id="fAppDownloadUrl" value="' + esc(d.app_download_url || '') + '" onchange="onGlobalChange()" placeholder="exe 다운로드 링크 (GitHub Release 등)">',
    '</div>',
    '<hr style="border:none;border-top:1px solid #eee;margin:16px 0;">',
    '<div class="field-row">',
    '  <span class="field-label">🔄 롤백 라벨</span>',
    '  <input class="field-input" id="fRollbackLabel" value="' + esc(d.rollbackLabel_ko || '') + '" onchange="onGlobalChange()" placeholder="예: SMART Review 2.3 롤백 버전">',
    '</div>',
    '<div class="field-row">',
    '  <span class="field-label">🔄 롤백 링크</span>',
    '  <input class="field-input" id="fRollbackLink" value="' + esc(d.rollbackLink || '') + '" onchange="onGlobalChange()" placeholder="OneDrive 압축파일 공유 링크">',
    '</div>'
  ].join('');
}

function renderItems() {
  var sw = portalData.software || [];
  document.getElementById('swList').innerHTML = sw.map(function(s) {
    var tagCls = s.category === 'both' ? 'both' : s.category;
    return [
      '<div class="sw-card" id="card-' + esc(s.id) + '">',
      '  <div class="sw-header">',
      '    <span class="sw-name">' + s.icon + ' ' + esc(s.name) + '</span>',
      '    <span class="sw-tag ' + tagCls + '">' + esc(getCatLabel(s.category)) + '</span>',
      '  </div>',
      '  <div class="field-row">',
      '    <span class="field-label">Version</span>',
      '    <input class="field-input" id="ver-' + esc(s.id) + '" value="' + esc(s.versionName || '') + '" onchange="onItemChange(\'' + esc(s.id) + '\')" placeholder="(버전추출 버튼 또는 직접 입력)" style="font-family:Consolas,monospace;font-size:12px;color:#4a4a8a;background:#f8f9fc;">',
      '  </div>',
      '  <div class="field-row">',
      '    <span class="field-label">Link</span>',
      '    <input class="field-input" id="link-' + esc(s.id) + '" value="' + esc(s.link) + '" onchange="onItemChange(\'' + esc(s.id) + '\')">',
      '  </div>',
      '  <div class="field-row">',
      '    <span class="field-label">Changelog (KO)</span>',
      '    <textarea class="field-input" id="cl-' + esc(s.id) + '" onchange="onItemChange(\'' + esc(s.id) + '\')">' + esc(s.changelog_ko) + '</textarea>',
      '  </div>',
      '  <div class="field-row">',
      '    <span class="field-label">Date</span>',
      '    <input type="date" class="field-input" id="date-' + esc(s.id) + '" value="' + esc(s.date) + '" onchange="onItemChange(\'' + esc(s.id) + '\')">',
      '  </div>',
      '</div>'
    ].join('');
  }).join('');
}

function onGlobalChange() {
  api('/api/save_notice', {
    notice_ko: document.getElementById('fNoticeKo').value,
    lastUpdated: document.getElementById('fLastUpdated').value,
    app_version: document.getElementById('fAppVersion').value,
    app_download_url: document.getElementById('fAppDownloadUrl').value,
    rollbackLabel_ko: document.getElementById('fRollbackLabel').value,
    rollbackLink: document.getElementById('fRollbackLink').value
  });
}

function todayStr() {
  var d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0');
}

function onItemChange(id) {
  var today = todayStr();
  document.getElementById('date-' + id).value = today;
  document.getElementById('fLastUpdated').value = today;
  api('/api/save_item', {
    id: id,
    versionName: document.getElementById('ver-' + id).value,
    link: document.getElementById('link-' + id).value,
    changelog_ko: document.getElementById('cl-' + id).value,
    date: today
  });
  onGlobalChange();
}

function onExtract() {
  document.getElementById('btnExtract').disabled = true;
  api('/api/extract').then(function(res) {
    document.getElementById('btnExtract').disabled = false;
    if (res.success) {
      portalData = res.data;
      portalData.software.forEach(function(s) {
        var el = document.getElementById('ver-' + s.id);
        if (el) el.value = s.versionName || '';
      });
      addLog('✅ 버전명 추출 완료 (' + res.count + '개)');
    } else {
      addLog('❌ 추출 실패: ' + res.error);
    }
  });
}

function onDeploy() {
  document.getElementById('btnDeploy').disabled = true;
  document.getElementById('btnExtract').disabled = true;
  document.getElementById('loadingOverlay').classList.add('active');
  document.getElementById('logPanel').classList.remove('collapsed');
  addLog('🚀 배포 시작...');
  logSince = 0;

  api('/api/deploy').then(function() {
    pollLogs();
  });
}

function pollLogs() {
  fetch('/api/logs?since=' + logSince).then(function(r) { return r.json(); }).then(function(res) {
    res.logs.forEach(function(msg) { addLog(msg); });
    logSince = res.total;
    if (res.done) {
      document.getElementById('btnDeploy').disabled = false;
      document.getElementById('btnExtract').disabled = false;
      document.getElementById('loadingOverlay').classList.remove('active');
      // Reload data after deploy
      fetch('/api/data').then(function(r) { return r.json(); }).then(function(r) {
        if (r.success) {
          portalData = r.data;
          portalData.software.forEach(function(s) {
            var el = document.getElementById('ver-' + s.id);
            if (el) el.value = s.versionName || '';
          });
        }
      });
    } else {
      setTimeout(pollLogs, 500);
    }
  });
}

function addLog(msg) {
  logLines++;
  document.getElementById('logCount').textContent = '(' + logLines + ')';
  var el = document.getElementById('logContent');
  var cls = 'log-line';
  if (msg.indexOf('✅') >= 0 || msg.indexOf('성공') >= 0) cls += ' success';
  if (msg.indexOf('❌') >= 0 || msg.indexOf('실패') >= 0 || msg.indexOf('오류') >= 0) cls += ' error';
  el.innerHTML += '<div class="' + cls + '">' + esc(msg) + '</div>';
  el.scrollTop = el.scrollHeight;
}

function toggleLog() {
  document.getElementById('logPanel').classList.toggle('collapsed');
}

// === TAB SWITCHING ===
var currentTab = 'manage';
var dashLoaded = false;
var dashTimer = null;

function switchTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.tab-btn').forEach(function(b) { b.classList.remove('active'); });
  document.querySelectorAll('.tab-content').forEach(function(c) { c.classList.remove('active'); });
  document.querySelector('.tab-btn[onclick*="' + tab + '"]').classList.add('active');
  document.getElementById('tab-' + tab).classList.add('active');
  document.getElementById('manageBtns').style.display = tab === 'manage' ? 'flex' : 'none';
  if (tab === 'dashboard') {
    loadDashboard();
    if (!dashTimer) dashTimer = setInterval(loadDashboard, 30000);
  } else {
    if (dashTimer) { clearInterval(dashTimer); dashTimer = null; }
  }
}

// === DASHBOARD ===
var SITES = [
  {code:'KYK', name:'한국'},
  {code:'KYA', name:'미주'},
  {code:'KYA-MX', name:'멕시코'},
  {code:'JKY', name:'일본'},
  {code:'KYSEA', name:'동남아'},
  {code:'KYV', name:'베트남'},
  {code:'KYE', name:'유럽'},
  {code:'KYC', name:'중국'},
  {code:'KYTW', name:'대만'},
  {code:'AES', name:'본사(HQ)'}
];

function loadDashboard() {
  fetch('/api/analytics_proxy')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error && (!data.events || data.events.length === 0)) {
        document.getElementById('dashContent').innerHTML = '<div class="dash-error">⚠️ 서버 연결 실패: ' + esc(data.error) + '</div>';
        return;
      }
      renderDashboard(data.events || []);
    })
    .catch(function(e) {
      document.getElementById('dashContent').innerHTML = '<div class="dash-error">⚠️ 데이터를 불러올 수 없습니다.</div>';
    });
}

function todayDate() {
  var d = new Date(); return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0');
}

function getWeekStart() {
  var d = new Date(); d.setDate(d.getDate() - d.getDay()); d.setHours(0,0,0,0); return d;
}

function renderDashboard(events) {
  var now = new Date();
  var today = todayDate();
  var weekStart = getWeekStart();

  // Aggregate
  var totalCount = events.length;
  var todayCount = 0;
  var weekCount = 0;
  var bySite = {};
  var byDay = {};
  var activeSites = {};
  var bySw = {};
  var siteDates = {};

  SITES.forEach(function(s) { bySite[s.code] = {total:0, today:0, week:0, last:null}; siteDates[s.code] = {}; });

  events.forEach(function(ev) {
    var d = ev.ts ? ev.ts.substring(0,10) : '';
    var evDate = ev.ts ? new Date(ev.ts) : null;
    var site = ev.site;

    if (!bySite[site]) bySite[site] = {total:0, today:0, week:0, last:null};
    if (!siteDates[site]) siteDates[site] = {};
    bySite[site].total++;
    if (evDate && (!bySite[site].last || evDate > new Date(bySite[site].last))) bySite[site].last = ev.ts;
    if (d) siteDates[site][d] = true;

    if (d === today) { todayCount++; bySite[site].today++; }
    if (evDate && evDate >= weekStart) { weekCount++; bySite[site].week++; }

    if (!byDay[d]) byDay[d] = 0;
    byDay[d]++;
    if (bySite[site].total > 0) activeSites[site] = true;

    if (ev.action === 'download' && ev.sw) {
      if (!bySw[ev.sw]) bySw[ev.sw] = 0;
      bySw[ev.sw]++;
    }
  });

  var activeCount = Object.keys(activeSites).length;

  // Store events globally for trend tab switching
  window._dashEvents = events;

  // Site ranking by total + gap calculation
  function calcGaps(dates) {
    var keys = Object.keys(dates).sort();
    if (keys.length === 0) return {maxGap: -1, daysSinceLast: -1, lastDate: null};
    var maxGap = 0;
    for (var i = 1; i < keys.length; i++) {
      var gap = Math.round((new Date(keys[i]) - new Date(keys[i-1])) / 86400000);
      if (gap > maxGap) maxGap = gap;
    }
    var lastDate = keys[keys.length - 1];
    var daysSinceLast = Math.round((new Date(today) - new Date(lastDate)) / 86400000);
    if (daysSinceLast > maxGap) maxGap = daysSinceLast;
    return {maxGap: maxGap, daysSinceLast: daysSinceLast, lastDate: lastDate};
  }
  var siteArr = SITES.map(function(s) {
    var gaps = calcGaps(siteDates[s.code] || {});
    return {code:s.code, name:s.name, data:bySite[s.code]||{total:0,today:0,week:0,last:null}, gaps:gaps};
  });
  siteArr.sort(function(a,b) { return b.data.total - a.data.total; });
  var maxSite = siteArr.length > 0 ? (siteArr[0].data.total || 1) : 1;

  // SW download ranking
  var swArr = [];
  for (var sw in bySw) { swArr.push({name:sw, count:bySw[sw]}); }
  swArr.sort(function(a,b) { return b.count - a.count; });
  var maxSw = swArr.length > 0 ? swArr[0].count : 1;

  var refreshTime = new Date().toLocaleTimeString('ko-KR', {hour:'2-digit',minute:'2-digit',second:'2-digit'});

  var html = '';

  // Summary cards
  html += '<div class="dash-grid">';
  html += '<div class="stat-card"><div class="stat-label">오늘 접속</div><div class="stat-value">' + todayCount + '</div><div class="stat-sub">' + today + '</div></div>';
  html += '<div class="stat-card"><div class="stat-label">이번 주</div><div class="stat-value">' + weekCount + '</div><div class="stat-sub">일요일부터 누적</div></div>';
  html += '<div class="stat-card"><div class="stat-label">전체 접속</div><div class="stat-value">' + totalCount + '</div><div class="stat-sub">전체 기간 누적</div></div>';
  html += '<div class="stat-card"><div class="stat-label">활성 지사</div><div class="stat-value">' + activeCount + '<span style="font-size:16px;color:#94a3b8;font-weight:400;"> / ' + SITES.length + '</span></div><div class="stat-sub">접속 기록이 있는 지사</div></div>';
  html += '</div>';

  // Bar chart
  html += '<div class="dash-section"><h3>📊 지사별 접속 현황</h3><div class="dash-refresh">마지막 갱신: ' + refreshTime + ' (30초 자동)</div><div class="bar-chart">';
  siteArr.forEach(function(s) {
    var pct = s.data.total > 0 ? Math.max(5, Math.round(s.data.total / maxSite * 100)) : 0;
    html += '<div class="bar-row"><span class="bar-label">' + esc(s.code) + '</span><div class="bar-track"><div class="bar-fill" style="width:' + pct + '%">' + s.data.total + '</div></div></div>';
  });
  html += '</div></div>';

  // Trend section (period tabs + stacked chart)
  html += '<div class="dash-section"><h3>📈 접속 트렌드</h3><div id="trendContainer"></div></div>';

  // SW download ranking
  html += '<div class="dash-section"><h3>⬇️ SW별 다운로드 순위</h3>';
  if (swArr.length === 0) {
    html += '<div style="padding:20px;text-align:center;color:#94a3b8;font-size:14px;">다운로드 기록 없음</div>';
  } else {
    html += '<div class="bar-chart">';
    swArr.forEach(function(s) {
      var pct = Math.max(5, Math.round(s.count / maxSw * 100));
      html += '<div class="bar-row"><span class="bar-label" style="width:160px;font-size:11px;">' + esc(s.name) + '</span><div class="bar-track"><div class="bar-fill" style="width:' + pct + '%;background:linear-gradient(90deg,#2563eb,#7c3aed);">' + s.count + '</div></div></div>';
    });
    html += '</div>';
  }
  html += '</div>';

  // Detail table with access monitoring
  html += '<div class="dash-section"><h3>📋 지사별 상세</h3><table class="detail-table"><thead><tr><th>지사</th><th>이름</th><th style="text-align:center">오늘</th><th style="text-align:center">이번 주</th><th style="text-align:center">전체</th><th>최근 접속일</th><th style="text-align:center">미접속 일수</th><th style="text-align:center">최대 미접속</th></tr></thead><tbody>';
  siteArr.forEach(function(s) {
    var g = s.gaps;
    var lastStr = g.lastDate || '-';
    var sinceStr, sinceBadge, maxStr, maxBadge, rowClass = '';
    if (g.daysSinceLast < 0) {
      sinceStr = '미접속'; sinceBadge = 'badge-gray'; maxStr = '-'; maxBadge = '';
      rowClass = 'warn-red';
    } else {
      sinceStr = g.daysSinceLast + '일';
      maxStr = g.maxGap + '일';
      if (g.daysSinceLast === 0) { sinceBadge = 'badge-green'; }
      else if (g.daysSinceLast >= 14) { sinceBadge = 'badge-red'; rowClass = 'warn-red'; }
      else if (g.daysSinceLast >= 7) { sinceBadge = 'badge-yellow'; rowClass = 'warn-yellow'; }
      else { sinceBadge = 'badge-green'; }
      if (g.maxGap >= 14) { maxBadge = 'badge-red'; }
      else if (g.maxGap >= 7) { maxBadge = 'badge-yellow'; }
      else { maxBadge = 'badge-green'; }
    }
    html += '<tr class="' + rowClass + '"><td style="font-weight:700">' + esc(s.code) + '</td><td>' + esc(s.name) + '</td><td class="num">' + s.data.today + '</td><td class="num">' + s.data.week + '</td><td class="num">' + s.data.total + '</td><td style="font-size:12px;color:#64748b">' + esc(lastStr) + '</td><td class="num"><span class="badge-inactive ' + sinceBadge + '">' + sinceStr + '</span></td><td class="num">' + (maxBadge ? '<span class="badge-inactive ' + maxBadge + '">' + maxStr + '</span>' : maxStr) + '</td></tr>';
  });
  html += '</tbody></table></div>';

  html += '<div style="height:220px"></div>';

  document.getElementById('dashContent').innerHTML = html;
  renderTrend('1W');
}

var SITE_COLORS = {
  'KYK':'#4a5a8a','KYA':'#7c3aed','KYA-MX':'#059669','JKY':'#dc2626','KYSEA':'#d97706',
  'KYV':'#2563eb','KYE':'#db2777','KYC':'#ea580c','KYTW':'#0891b2','AES':'#4f46e5'
};

function renderTrend(periodKey) {
  var events = window._dashEvents || [];
  var now = new Date();
  var todayStr = todayDate();
  var dayNames = ['일','월','화','수','목','금','토'];

  var periods = {
    '1W':  {label:'1주일', days:7},
    '1M':  {label:'1개월', days:30},
    '3M':  {label:'3개월', days:90},
    '6M':  {label:'6개월', days:180},
    '1Y':  {label:'1년',   days:365}
  };
  var p = periods[periodKey];

  // Generate buckets
  var buckets = [];
  var startDate = new Date(now);
  startDate.setDate(startDate.getDate() - p.days + 1);

  if (periodKey === '1W') {
    for (var i = 0; i < 7; i++) {
      var d = new Date(startDate); d.setDate(d.getDate() + i);
      var k = fmtDate(d);
      buckets.push({key:k, label:(d.getMonth()+1)+'/'+d.getDate()+' ('+dayNames[d.getDay()]+')', from:k, to:k});
    }
  } else if (periodKey === '1M') {
    for (var i = 0; i < 30; i++) {
      var d = new Date(startDate); d.setDate(d.getDate() + i);
      var k = fmtDate(d);
      buckets.push({key:k, label:d.getDate()+'', from:k, to:k});
    }
  } else if (periodKey === '3M') {
    var wk = new Date(startDate);
    wk.setDate(wk.getDate() - wk.getDay() + 1);
    while (wk <= now) {
      var wEnd = new Date(wk); wEnd.setDate(wEnd.getDate() + 6);
      var wLabel = (wk.getMonth()+1)+'/'+wk.getDate()+'~'+(wEnd.getMonth()+1)+'/'+wEnd.getDate();
      buckets.push({key:fmtDate(wk), label:wLabel, from:fmtDate(wk), to:fmtDate(wEnd)});
      wk.setDate(wk.getDate() + 7);
    }
  } else {
    var mCount = periodKey === '6M' ? 6 : 12;
    for (var i = mCount - 1; i >= 0; i--) {
      var md = new Date(now.getFullYear(), now.getMonth() - i, 1);
      var mEnd = new Date(md.getFullYear(), md.getMonth() + 1, 0);
      var mLabel = md.getFullYear()+'.'+(md.getMonth()+1);
      buckets.push({key:mLabel, label:(md.getMonth()+1)+'월', from:fmtDate(md), to:fmtDate(mEnd)});
    }
  }

  // Aggregate events into buckets per site
  var bucketData = buckets.map(function(b) {
    var sites = {}; var total = 0;
    SITES.forEach(function(s) { sites[s.code] = 0; });
    events.forEach(function(ev) {
      var d = ev.ts ? ev.ts.substring(0,10) : '';
      if (d >= b.from && d <= b.to) { sites[ev.site] = (sites[ev.site]||0) + 1; total++; }
    });
    return {label:b.label, sites:sites, total:total};
  });
  var maxTotal = Math.max.apply(null, bucketData.map(function(b){return b.total;})) || 1;

  // Build HTML
  var h = '';

  // Period tabs
  h += '<div class="period-tabs">';
  ['1W','1M','3M','6M','1Y'].forEach(function(pk) {
    var cls = pk === periodKey ? 'period-tab active' : 'period-tab';
    h += '<button class="'+cls+'" onclick="renderTrend(\''+pk+'\')">' + periods[pk].label + '</button>';
  });
  h += '</div>';

  // Legend
  h += '<div class="trend-legend">';
  h += '<div class="trend-legend-item"><div class="trend-legend-dot" style="background:#1e293b;border-radius:50%;"></div><span style="font-weight:700;">총계</span></div>';
  SITES.forEach(function(s) {
    h += '<div class="trend-legend-item"><div class="trend-legend-dot" style="background:' + SITE_COLORS[s.code] + ';"></div><span>' + s.code + '</span></div>';
  });
  h += '</div>';

  // Stacked bar chart
  h += '<div class="trend-chart">';
  bucketData.forEach(function(bd) {
    h += '<div class="trend-bar-wrap">';
    h += '<div class="trend-count">' + bd.total + '</div>';
    h += '<div class="trend-stack" style="height:' + (bd.total > 0 ? Math.max(8, Math.round(bd.total/maxTotal*100)) : 2) + '%">';
    SITES.forEach(function(s) {
      var cnt = bd.sites[s.code] || 0;
      if (cnt > 0) {
        var segH = Math.round(cnt / bd.total * 100);
        h += '<div class="trend-seg" style="height:'+segH+'%;background:'+SITE_COLORS[s.code]+';"><div class="trend-tip">'+s.code+' — '+cnt+'건</div></div>';
      }
    });
    h += '</div>';
    h += '<div class="trend-label">' + esc(bd.label) + '</div>';
    h += '</div>';
  });
  h += '</div>';

  // Per-site summary table for selected period
  var periodSites = {};
  SITES.forEach(function(s) { periodSites[s.code] = {name:s.name, count:0}; });
  bucketData.forEach(function(bd) {
    SITES.forEach(function(s) { periodSites[s.code].count += (bd.sites[s.code]||0); });
  });
  var psArr = SITES.map(function(s){return {code:s.code,name:s.name,count:periodSites[s.code].count};});
  psArr.sort(function(a,b){return b.count-a.count;});
  var grandTotal = psArr.reduce(function(sum,s){return sum+s.count;},0);

  h += '<table class="detail-table" style="margin-top:16px;"><thead><tr><th>지사</th><th>이름</th><th style="text-align:center">접속 수</th><th style="text-align:center">비율</th><th>그래프</th></tr></thead><tbody>';
  h += '<tr style="background:#f0f4ff;font-weight:700;"><td>ALL</td><td>전 지사 합계</td><td class="num">' + grandTotal + '</td><td class="num">100%</td><td><div style="height:8px;border-radius:4px;background:linear-gradient(90deg,#4a5a8a,#5e4d7a);"></div></td></tr>';
  psArr.forEach(function(s) {
    var pct = grandTotal > 0 ? Math.round(s.count/grandTotal*100) : 0;
    var barW = grandTotal > 0 ? Math.max(1, Math.round(s.count/grandTotal*100)) : 0;
    h += '<tr><td style="font-weight:600;"><span class="trend-legend-dot" style="display:inline-block;width:8px;height:8px;border-radius:3px;background:'+SITE_COLORS[s.code]+';margin-right:6px;vertical-align:middle;"></span>'+esc(s.code)+'</td><td>'+esc(s.name)+'</td><td class="num">'+s.count+'</td><td class="num">'+pct+'%</td><td><div style="height:8px;border-radius:4px;width:'+barW+'%;background:'+SITE_COLORS[s.code]+';min-width:'+(s.count>0?'4px':'0')+'"></div></td></tr>';
  });
  h += '</tbody></table>';

  document.getElementById('trendContainer').innerHTML = h;
}

function fmtDate(d) {
  return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
}

renderGlobal();
renderItems();
</script>
</body>
</html>"""


# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        _load_data()

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        url = f"http://127.0.0.1:{port}"

        if sys.stdout:
            print(f"Portal Manager: {url}")
            print("브라우저가 자동으로 열립니다. 종료하려면 Ctrl+C를 누르세요.")

        webbrowser.open(url)

        try:
            server.serve_forever()
        except KeyboardInterrupt:
            server.shutdown()
    except Exception:
        import traceback
        _log = os.path.join(os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else ".", "portal_manager_error.log")
        with open(_log, "w", encoding="utf-8") as _f:
            traceback.print_exc(file=_f)
        raise
