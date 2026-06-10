# Smart Review Version Portal - 변경 히스토리

## 2026-06-10

### HTML 원격 로딩 구조 개선 + server 폴더 통합
- **파일**: `app.py`, `server-dist/server.py`, `manage_portal.py`, `PortalDataServer.spec`, `SmartReviewPortal.spec`
- **변경**:
  1. `app.py` — `fetch_remote_html()` 함수 추가 (서버/GitHub 병렬 요청), HTML 캐시, fallback 체인 (원격→캐시→로컬)
  2. `server-dist/server.py` — GET/POST `/portal.html` 엔드포인트 추가
  3. `manage_portal.py` — `deploy_to_server()`에 HTML 업로드 추가 (portal-data.json + HTML 동시 배포)
  4. `server/` + `server-dist/` 폴더 통합 → `server-dist/` 단일 폴더로 정리
  5. SmartReviewPortal.exe, PortalDataServer.exe 재빌드

### 롤백 라벨 다국어 번역 + 스페인어/독일어 전체 번역 보정
- **파일**: `portal-data.json`, `manage_portal.py`, `manage_gui.py`, `Smart Review Version Portal.html`, `index.html`
- **변경**:
  1. `portal-data.json` — `rollbackLabel` → `rollbackLabel_ko/en/zh/ja/es/de` 다국어 패턴으로 변경, notice_es/notice_de 추가, SW 5종 changelog_es/de 추가, Graphic Driver changelog_en/zh/ja 보정
  2. `manage_portal.py` — `run_translate()`에 rollbackLabel 번역 블록 추가 (notice와 동일 패턴)
  3. `manage_gui.py` — GUI 필드 `rollbackLabel_ko` 참조로 변경, 저장 핸들러에 라벨 변경 시 번역 필드 초기화 로직 추가
  4. `Smart Review Version Portal.html` — `getRollbackLabel()` 함수 추가, renderPortal/applyTranslations에서 언어별 라벨 표시, rollbackName id 추가, 독일어 btnDownload "Download" → "Herunterladen"
  5. `index.html` — HTML과 동기화

### 상시 롤백 다운로드 기능 구현
- **파일**: `portal-data.json`, `manage_gui.py`, `manage_portal.py`, `Smart Review Version Portal.html`, `index.html`, `PortalManager.spec`, `SmartReviewPortal.spec`
- **변경**:
  1. `portal-data.json` — rollbackLink, rollbackLabel 필드 추가
  2. `manage_gui.py` — renderGlobal()에 롤백 라벨/링크 입력란 추가, onGlobalChange()에 rollback 필드 전송, /api/save_notice에 rollback 저장
  3. `Smart Review Version Portal.html` — CSS(토글 스위치, 롤백 패널), UI_TRANSLATIONS 6개 언어에 rollbackToggle/rollbackDownload 추가, renderPortal()에 토글+다운로드 영역, toggleRollback() 함수, applyTranslations()에 롤백 번역
  4. SmartReviewPortal.exe, Portal Manager.exe 재빌드

## 2026-06-09

### 대시보드 고도화: SW별 다운로드 순위 + 미접속 모니터링 + 기간별 트렌드
- **파일**: `manage_gui.py`
- **변경**:
  1. SW별 다운로드 순위 — 파란-보라 막대 그래프, download 이벤트의 sw 필드 집계
  2. 미접속 지사 모니터링 — 상세 테이블에 "미접속 일수", "최대 미접속" 컬럼 추가, 7일 노란색/14일 빨간색 경고 뱃지
  3. 기간별 접속 트렌드 — 1주일/1개월/3개월/6개월/1년 탭 전환, 지사별 색상 스택 차트 + 범례 + 기간별 비교 테이블(합계/비율)
  4. 호버 툴팁 — 차트 세그먼트에 마우스 오버 시 "KYK — 2건" 말풍선 표시
  5. AES(HQ) 지사 추가 — server.py VALID_SITES, app.py FALLBACK_SITES, manage_gui.py SITES (총 10개 지사)
  6. 지사 선택 UI 영문화 — "Select Branch" / "Please select your branch office" / "Confirm"
  7. DELETE `/api/analytics` 초기화 엔드포인트 추가 (server.py)

### 3차 고도화: Usage Analytics Dashboard (지사별 사용 현황 대시보드)
- **파일**: `server-dist/server.py`, `app.py`, `manage_gui.py`, `portal-data.json`, `config.json`
- **변경**:
  1. `server-dist/server.py` — POST `/api/event` (이벤트 수집), GET `/api/analytics` (데이터 조회), OPTIONS preflight, `analytics.json` 별도 저장
  2. `app.py` — 최초 실행 시 지사 선택 모달 (포털 HTML 내), launch 이벤트 fire-and-forget 전송, `AppApi.set_site()` 추가
  3. `manage_gui.py` — 탭 네비게이션 (📋 관리 / 📊 대시보드), 대시보드: 요약 카드, 지사별 막대 그래프, 7일 트렌드, 상세 테이블, 30초 자동 갱신
  4. `portal-data.json` — `sites` 필드 추가 (9개 지사: KYK, KYA, KYA-MX, JKY, KYSEA, KYV, KYE, KYC, KYTW)
  5. `Smart Review Version Portal.html` — 지사 선택 모달 오버레이, `confirmSiteSelection()` → pywebview API 연동

### Portal Manager exe 빌드 + 크래시 수정
- **파일**: `manage_gui.py`, `manage_portal.py`, `PortalManager.spec`
- **변경**:
  1. `PortalManager.spec` — manage_gui.py를 단일 exe로 빌드하는 PyInstaller 설정 (console=False)
  2. `manage_gui.py` — exe 빌드 시 경로 보정, stdout 가드, 에러 로그 파일 출력(portal_manager_error.log)
  3. `manage_portal.py` — sys.stdout/stderr None 가드 추가 (console=False 빌드 시 크래시 방지)
  4. `Portal Manager.exe` 생성 — 더블클릭으로 관리 도구 실행 가능 (콘솔 창 없음)

### 독일어(6번째 언어) 추가
- **파일**: `Smart Review Version Portal.html`, `manage_portal.py`, `manage_gui.py`, `portal-data.json`
- **변경**: 독일어 UI_TRANSLATIONS/BATCH_LABELS/APP_UPDATE_LABELS/UPDATE_LABELS + notice_de + changelog_de

### 국기 이모지 + 스페인어(5번째 언어) 추가
- **파일**: `Smart Review Version Portal.html`, `index.html`, `manage_portal.py`, `manage_gui.py`, `portal-data.json`
- **변경**:
  1. `Smart Review Version Portal.html` — 언어 버튼에 국기 이모지(🇺🇸🇰🇷🇨🇳🇯🇵🇪🇸), 스페인어 UI_TRANSLATIONS/BATCH_LABELS/APP_UPDATE_LABELS/UPDATE_LABELS 블록 추가
  2. `manage_portal.py` — langs에 "es" 추가, lang_names에 "es": "Spanish" 추가
  3. `manage_gui.py` — changelog_es/notice_es 필드 클리어 로직 추가
  4. `portal-data.json` — notice_es + 9개 소프트웨어 changelog_es 필드 추가

### 2차 고도화: exe 자동 업데이트 + 일괄 다운로드
- **파일**: `app.py`, `Smart Review Version Portal.html`, `index.html`, `manage_gui.py`, `portal-data.json`, `사용방법.txt`
- **변경**:
  1. `app.py` — `APP_VERSION` 상수, `check_app_update()` (버전 비교+다운로드), `apply_pending_update()` (_update.exe 적용), `AppApi.restart_for_update()` (pywebview js_api)
  2. `Smart Review Version Portal.html` — 앱 업데이트 팝업 (재시작/나중에), 소프트웨어 카드 체크박스, 전체 선택+일괄 다운로드 툴바, 4개 국어 번역 추가
  3. `manage_gui.py` — 전역 설정에 앱 버전/다운로드 URL 필드 추가, API 저장 로직 반영
  4. `portal-data.json` — `app_version`, `app_download_url` 필드 추가
  5. `사용방법.txt` — 자동 업데이트, 일괄 다운로드 섹션 추가

### GitHub Pages 배포 및 자동 동기화
- **파일**: `index.html` (신규), `robots.txt` (신규), `manage_portal.py`
- **변경**:
  1. GitHub 리포지토리 생성 (hajunheyok/smart-review-portal, public)
  2. `index.html` — portal-data.json 동적 로드(fetch) 추가
  3. `robots.txt` — 모든 크롤러 차단
  4. `index.html`, `Smart Review Version Portal.html` — noindex/nofollow 메타태그 추가
  5. `manage_portal.py` — `deploy_to_server()`, `deploy_to_github()` 함수 추가, 기본 실행 시 양쪽 자동 배포

## 2026-06-08

### 버전 비교 버그 수정 (SROCV 등 파일명에 `.`이 포함된 소프트웨어)
- **파일**: `Smart Review Version Portal.html`
- **문제**: `srocv.python_03_10_ocv_BodyFM_multi_v03_N_qdm (1).exe`가 "업데이트 필요"로 잘못 표시
- **원인**: 확장자 제거 정규식 `/\.[^.]+$/`이 `.exe`가 아닌 `.python_...` 부분까지 제거
- **수정**:
  1. 확장자 제거: `/\.[^.]+$/` → `/\.(exe|msi|zip|7z|rar|tar\.gz|gz)$/i` (알려진 확장자만 제거)
  2. `extractVersionCore` fallback에서 `(N)` 전체 제거 및 trim 처리 추가
- **결과**: deploy/SmartReviewPortal.exe 재빌드, 서버 portal-data.json 업데이트 완료

### Graphic Driver matchPattern 변경
- **파일**: `portal-data.json`
- **변경**: `Intel_GraphicDriver` → `desktop` (NVIDIA 등 다양한 드라이버 파일명 대응)

### Review Station 3 중복 다운로드 대응
- **파일**: `Smart Review Version Portal.html`
- **변경**: `(1)`, `(2)` 등 중복 다운로드 번호 제거 시 빌드번호 `(837715326)` 보존 (4자리 이하만 제거)

### 서버 원격 데이터 업데이트 기능 추가
- **파일**: `server-dist/server.py`
- **변경**: POST `/portal-data.json` 엔드포인트 추가 → curl로 원격 업데이트 가능
