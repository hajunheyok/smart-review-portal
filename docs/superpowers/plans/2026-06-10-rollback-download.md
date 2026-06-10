# 상시 롤백 다운로드 기능 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 포탈 사용자(본사+해외)가 토글 스위치로 롤백 버전 다운로드를 언제든 이용할 수 있도록 한다.

**Architecture:** portal-data.json에 `rollbackLink`/`rollbackLabel` 필드를 추가하고, Portal Manager GUI에 입력란을, 포탈 HTML에 토글+다운로드 영역을 추가한다. 기존 배포 흐름(서버+GitHub)으로 함께 반영된다.

**Tech Stack:** Python (manage_gui.py, manage_portal.py), HTML/CSS/JS (Portal HTML), JSON (portal-data.json)

---

### Task 1: portal-data.json에 롤백 필드 추가

**Files:**
- Modify: `portal-data.json` (최상위 레벨)

- [ ] **Step 1: rollback 필드 추가**

`portal-data.json`의 최상위에 다음 2개 필드를 추가한다 (`"lastUpdated"` 바로 위):

```json
{
  "rollbackLink": "",
  "rollbackLabel": "SMART Review 2.3 롤백 버전",
  "lastUpdated": "2026-06-09",
  ...
}
```

- [ ] **Step 2: 커밋**

```bash
git add portal-data.json
git commit -m "feat: portal-data.json에 rollbackLink/rollbackLabel 필드 추가"
```

---

### Task 2: Portal Manager GUI에 롤백 입력란 추가

**Files:**
- Modify: `manage_gui.py` — `renderGlobal()` JS 함수, `onGlobalChange()` JS 함수, `/api/save_notice` 핸들러

- [ ] **Step 1: renderGlobal()에 롤백 입력란 HTML 추가**

`manage_gui.py`의 `renderGlobal()` 함수에서, 앱 다운로드 URL 필드(`fAppDownloadUrl`) 뒤에 롤백 필드 2개를 추가한다:

```javascript
'<div class="field-row">',
'  <span class="field-label">앱 다운로드 URL</span>',
'  <input class="field-input" id="fAppDownloadUrl" value="' + esc(d.app_download_url || '') + '" onchange="onGlobalChange()" placeholder="exe 다운로드 링크 (GitHub Release 등)">',
'</div>',
'<hr style="border:none;border-top:1px solid #eee;margin:16px 0;">',
'<div class="field-row">',
'  <span class="field-label">🔄 롤백 라벨</span>',
'  <input class="field-input" id="fRollbackLabel" value="' + esc(d.rollbackLabel || '') + '" onchange="onGlobalChange()" placeholder="예: SMART Review 2.3 롤백 버전">',
'</div>',
'<div class="field-row">',
'  <span class="field-label">🔄 롤백 링크</span>',
'  <input class="field-input" id="fRollbackLink" value="' + esc(d.rollbackLink || '') + '" onchange="onGlobalChange()" placeholder="OneDrive 압축파일 공유 링크">',
'</div>'
```

- [ ] **Step 2: onGlobalChange()에 rollback 필드 전송 추가**

`onGlobalChange()` 함수에서 API 호출 시 rollback 필드를 포함한다:

```javascript
function onGlobalChange() {
  api('/api/save_notice', {
    notice_ko: document.getElementById('fNoticeKo').value,
    lastUpdated: document.getElementById('fLastUpdated').value,
    app_version: document.getElementById('fAppVersion').value,
    app_download_url: document.getElementById('fAppDownloadUrl').value,
    rollbackLabel: document.getElementById('fRollbackLabel').value,
    rollbackLink: document.getElementById('fRollbackLink').value
  });
}
```

- [ ] **Step 3: /api/save_notice 핸들러에 rollback 필드 저장 추가**

`do_POST`의 `/api/save_notice` 분기에서, 기존 `app_download_url` 저장 뒤에 추가:

```python
_data["rollbackLabel"] = body.get("rollbackLabel", _data.get("rollbackLabel", ""))
_data["rollbackLink"] = body.get("rollbackLink", _data.get("rollbackLink", ""))
```

- [ ] **Step 4: 동작 확인**

Portal Manager 실행 후:
1. 전역 설정 카드에 "롤백 라벨", "롤백 링크" 입력란이 표시되는지 확인
2. 값 입력 후 배포 → portal-data.json에 필드가 포함되는지 확인

- [ ] **Step 5: 커밋**

```bash
git add manage_gui.py
git commit -m "feat: Portal Manager GUI에 롤백 링크/라벨 입력란 추가"
```

---

### Task 3: 포탈 HTML에 롤백 토글 + 다운로드 영역 추가

**Files:**
- Modify: `Smart Review Version Portal.html` — CSS, UI_TRANSLATIONS, renderPortal(), JS

- [ ] **Step 1: CSS 스타일 추가**

기존 스타일 블록(`.download-btn` 정의 부근)에 다음을 추가:

```css
.rollback-toggle-wrap {
  display: flex; align-items: center; gap: 10px; margin: 18px 0 0;
}
.rollback-toggle-label {
  font-size: 13px; font-weight: 600; color: #64748b; cursor: pointer;
}
.rollback-switch {
  position: relative; width: 44px; height: 24px; cursor: pointer;
}
.rollback-switch input { opacity: 0; width: 0; height: 0; }
.rollback-slider {
  position: absolute; top: 0; left: 0; right: 0; bottom: 0;
  background: #cbd5e1; border-radius: 24px; transition: 0.3s;
}
.rollback-slider::before {
  content: ''; position: absolute; width: 18px; height: 18px;
  left: 3px; bottom: 3px; background: #fff; border-radius: 50%; transition: 0.3s;
}
.rollback-switch input:checked + .rollback-slider { background: #4a5a8a; }
.rollback-switch input:checked + .rollback-slider::before { transform: translateX(20px); }

.rollback-panel {
  display: none; margin-top: 14px; padding: 16px 20px;
  background: linear-gradient(135deg, #f0f2f7 0%, #e8eaf3 100%);
  border: 1px solid #c8cee0; border-radius: 12px;
  animation: rollbackFadeIn 0.3s ease;
}
.rollback-panel.active { display: flex; align-items: center; justify-content: space-between; }
@keyframes rollbackFadeIn { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: translateY(0); } }
.rollback-info { display: flex; align-items: center; gap: 10px; }
.rollback-icon { font-size: 24px; }
.rollback-name { font-size: 15px; font-weight: 700; color: #1e293b; }
.rollback-dl-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 10px 22px; background: linear-gradient(135deg, #4a5a8a, #5e4d7a);
  color: #fff; font-size: 13px; font-weight: 700; border-radius: 10px;
  text-decoration: none; transition: all 0.2s; border: none; cursor: pointer;
}
.rollback-dl-btn:hover { transform: scale(1.04); box-shadow: 0 4px 16px rgba(74,90,138,0.35); }
```

- [ ] **Step 2: UI_TRANSLATIONS에 롤백 관련 텍스트 추가**

각 언어 객체에 다음 키를 추가:

```javascript
// en:
rollbackToggle: "Rollback Version",
rollbackDownload: "⬇ Download",

// ko:
rollbackToggle: "롤백 버전",
rollbackDownload: "⬇ 다운로드",

// zh:
rollbackToggle: "回滚版本",
rollbackDownload: "⬇ 下载",

// ja:
rollbackToggle: "ロールバックバージョン",
rollbackDownload: "⬇ ダウンロード",

// es:
rollbackToggle: "Versión de reversión",
rollbackDownload: "⬇ Descargar",

// de:
rollbackToggle: "Rollback-Version",
rollbackDownload: "⬇ Herunterladen",
```

- [ ] **Step 3: renderPortal()의 downloadsHTML에 롤백 토글 삽입**

`downloadsHTML` 배열에서, `'<div class="sw-grid" id="swGrid">'` 줄 바로 앞에 롤백 토글 영역을 삽입:

```javascript
var rollbackLabel = d.rollbackLabel || 'Rollback Version';
var t = UI_TRANSLATIONS[currentLang] || UI_TRANSLATIONS['en'];

var rollbackHTML = [
  '<div class="rollback-toggle-wrap">',
  '  <label class="rollback-switch">',
  '    <input type="checkbox" id="rollbackToggle" onchange="toggleRollback()">',
  '    <span class="rollback-slider"></span>',
  '  </label>',
  '  <span class="rollback-toggle-label" id="rollbackToggleLabel">' + esc(t.rollbackToggle) + '</span>',
  '</div>',
  '<div class="rollback-panel" id="rollbackPanel">',
  '  <div class="rollback-info">',
  '    <span class="rollback-icon">🔄</span>',
  '    <span class="rollback-name">' + esc(rollbackLabel) + '</span>',
  '  </div>',
  '  <a class="rollback-dl-btn" href="' + esc(d.rollbackLink || '') + '" target="_blank" id="rollbackDlBtn">',
  '    <span id="rollbackDlLabel">' + esc(t.rollbackDownload) + '</span>',
  '  </a>',
  '</div>'
].join('\n');
```

그리고 `downloadsHTML` 배열에서 `'</div>'` (batchToolbar 닫기) 뒤, `'<div class="sw-grid"...'` 앞에 `rollbackHTML`을 삽입:

```javascript
var downloadsHTML = [
    '<hr class="divider">',
    '<div class="section-title" id="downloadsTitle">📦 Downloads</div>',
    '<div class="batch-toolbar" id="batchToolbar">',
    '  <div class="batch-left">',
    '    <label><input type="checkbox" id="selectAllCheck" onchange="toggleSelectAll(this)"> <span id="selectAllLabel">' + esc(batchLabels.selectAll) + '</span></label>',
    '    <span class="batch-count" id="batchCount">0/' + totalDl + ' ' + esc(batchLabels.selected) + '</span>',
    '  </div>',
    '  <button class="batch-btn" id="batchDlBtn" disabled onclick="batchDownload()">⬇ <span id="batchDlLabel">' + esc(batchLabels.batchDl) + '</span></button>',
    '</div>',
    rollbackHTML,
    '<div class="sw-grid" id="swGrid">',
    swCardsHTML,
    '</div>'
  ].join('\n');
```

- [ ] **Step 4: toggleRollback() JS 함수 추가**

스크립트 영역에 다음 함수를 추가:

```javascript
function toggleRollback() {
  var panel = document.getElementById('rollbackPanel');
  var checked = document.getElementById('rollbackToggle').checked;
  if (checked) {
    panel.classList.add('active');
  } else {
    panel.classList.remove('active');
  }
}
```

- [ ] **Step 5: applyTranslations()에 롤백 라벨 번역 추가**

`applyTranslations()` 함수 내부에서 기존 번역 적용 로직 뒤에 추가:

```javascript
var rbToggleLabel = document.getElementById('rollbackToggleLabel');
if (rbToggleLabel) rbToggleLabel.textContent = t.rollbackToggle;
var rbDlLabel = document.getElementById('rollbackDlLabel');
if (rbDlLabel) rbDlLabel.textContent = t.rollbackDownload;
```

- [ ] **Step 6: 동작 확인**

브라우저에서 포탈 HTML을 열어 확인:
1. Downloads 섹션 상단에 토글 스위치가 보이는지 확인
2. 토글 ON → 롤백 다운로드 영역이 애니메이션과 함께 나타나는지 확인
3. 토글 OFF → 영역이 사라지는지 확인
4. 다운로드 버튼 클릭 시 OneDrive 링크로 이동하는지 확인
5. 언어 전환 시 토글 라벨/버튼 텍스트가 번역되는지 확인

- [ ] **Step 7: 커밋**

```bash
git add "Smart Review Version Portal.html"
git commit -m "feat: 포탈에 상시 롤백 다운로드 토글 기능 추가"
```

---

### Task 4: index.html 동기화 및 최종 배포 테스트

**Files:**
- Modify: `index.html` (Smart Review Version Portal.html의 복사본)

- [ ] **Step 1: index.html 동기화**

```bash
cp "Smart Review Version Portal.html" index.html
```

- [ ] **Step 2: Portal Manager를 통한 전체 플로우 테스트**

`python manage_gui.py` 실행 후:
1. 롤백 라벨에 "SMART Review 2.3 롤백 버전" 입력
2. 롤백 링크에 OneDrive URL 입력
3. 배포 버튼 클릭
4. 서버(10.4.10.140:9090) + GitHub Pages 모두 반영 확인
5. 포탈에서 토글 ON/OFF 동작 확인

- [ ] **Step 3: 커밋**

```bash
git add index.html portal-data.json
git commit -m "feat: 롤백 다운로드 기능 최종 반영 및 index.html 동기화"
```

---

### Task 5: exe 재빌드

**Files:**
- 기존: `PortalManager.spec`

- [ ] **Step 1: Portal Manager exe 재빌드**

```bash
pyinstaller PortalManager.spec --noconfirm
cp "dist/Portal Manager.exe" "Portal Manager.exe"
```

- [ ] **Step 2: 재빌드된 exe 동작 확인**

`Portal Manager.exe` 더블클릭 → 롤백 입력란이 정상 표시되는지 확인

- [ ] **Step 3: 커밋**

```bash
git add "Portal Manager.exe"
git commit -m "chore: Portal Manager exe 재빌드 (롤백 기능 포함)"
```
