# Smart Review Version Portal - 대화 이력

## 2026-06-11

### 21:30 - Smart Review Test Tracker 개발 (진행 중)
- **요청**: Smart Review 신규 버전 성능 풀테스트용 실시간 웹 도구 개발. 해외 출장 중 대리 테스터와 실시간 공유/피드백 가능한 시스템.
- **결과**:
  - 설계 문서 작성 완료 (`docs/superpowers/specs/2026-06-11-smart-review-test-tracker-design.md`)
  - 구현 계획 수립 (`docs/superpowers/plans/2026-06-11-smart-review-test-tracker.md`)
  - Task 1~6 구현 완료: DB 스키마, Flask API, 테스트 16개 전체 통과, SPA 프론트엔드, 배포 스크립트
  - Task 7 최종 검증 진행 중: 브라우저 E2E 테스트 완료 (로그인, 세션, 카테고리/항목 추가, Pass 결과 입력, 피드백 댓글 정상)
  - **남은 작업**: uploads 정리 → 최종 커밋 → 서버 배포 (10.4.10.140:9091)
- **주요 기능**: Flask+SocketIO 실시간 동기화, 4단계 역할 권한, 피드백 스레드 + 인라인 이미지, 기록 보관소, 템플릿 복사
- **관련 파일**: `tracker/app.py`, `tracker/models.py`, `tracker/templates/index.html`, `tracker/tests/`, `tracker/start_tracker.bat`, `tracker/TrackerServer.spec`

## 2026-06-10

### 15:30 - 롤백 라벨 다국어 번역 + 스페인어/독일어 번역 누락 보정
- **요청**: 롤백 라벨("SMART Review 2.3 롤백 버전")이 언어 전환 시 번역되지 않는 문제 수정 + 스페인어/독일어 notice·changelog 누락 보정 + 독일어 Download 버튼 현지화
- **결과**:
  - `rollbackLabel` → `rollbackLabel_ko/en/zh/ja/es/de` 다국어 필드 패턴으로 변경
  - `manage_portal.py`의 `run_translate()`에 rollbackLabel 번역 블록 추가
  - `manage_gui.py` 저장 핸들러: 라벨 변경 시 번역 필드 자동 초기화 (notice_ko 패턴 동일)
  - HTML에 `getRollbackLabel()` 함수 추가, 언어 전환 시 라벨 자동 갱신
  - notice_es, notice_de 번역 추가 (기존 누락)
  - SW 5종(AOIGUI-Halcon, FastRed, ONNX, Base Library, Graphic Driver) changelog_es/de 추가
  - Graphic Driver changelog_en/zh/ja도 함께 보정 (기존 빈값)
  - 독일어 다운로드 버튼: "Download" → "Herunterladen"
  - 서버 + GitHub 배포 완료, SmartReviewPortal.exe 재빌드 + 배포 폴더 복사 완료
- **관련 파일**: `portal-data.json`, `manage_portal.py`, `manage_gui.py`, `Smart Review Version Portal.html`, `index.html`

### 14:00 - 상시 롤백 다운로드 기능 구현
- **요청**: 배포 버전에 치명적 문제 발생 시 안전장치로 롤백 버전(OneDrive 압축파일) 상시 다운로드 기능 추가
- **결과**:
  - portal-data.json에 rollbackLink/rollbackLabel 필드 추가
  - Portal Manager GUI에 롤백 라벨/링크 입력란 추가
  - 포탈 HTML에 토글 스위치 + 다운로드 패널 추가 (6개 언어 UI 번역 포함)
  - 서버 + GitHub 배포, SmartReviewPortal.exe + Portal Manager.exe 재빌드
- **관련 파일**: `portal-data.json`, `manage_gui.py`, `Smart Review Version Portal.html`, `index.html`

## 2026-06-09

### 20:30 - 대시보드 고도화 (SW 순위 + 미접속 모니터링 + 기간별 트렌드)
- **요청**: 대시보드에 유의미한 통계 추가 — SW별 다운로드 순위, 미접속 지사 알림(최대 미접속 일수 + 최근 미접속 일수), 기간별 트렌드(1W/1M/3M/6M/1Y), 호버 툴팁
- **결과**:
  - SW별 다운로드 순위 막대 그래프 추가
  - 상세 테이블에 미접속 일수/최대 미접속 컬럼 + 7일/14일 경고 뱃지
  - 기간별 탭 전환 + 지사별 색상 스택 차트 + 범례 + 기간별 비교 테이블(합계/비율)
  - 차트 세그먼트 호버 시 말풍선 툴팁 ("KYK — 2건")
  - AES(HQ) 10번째 지사 추가, 지사 선택 UI 영문화, analytics 초기화 API 추가
  - Portal Manager exe 재빌드 완료
- **관련 파일**: `manage_gui.py`, `server/server.py`, `app.py`

### 20:10 - Portal Manager exe 크래시 수정
- **요청**: Portal Manager.exe가 console=False 빌드 시 크래시 발생 — 수정 요청
- **결과**:
  - **원인**: `manage_portal.py`에서 `sys.stdout.buffer` 접근 시, console=False 빌드에서는 `sys.stdout`이 `None`이라 `AttributeError` 발생
  - **수정**: `manage_portal.py` — stdout/stderr None 가드 추가, `manage_gui.py` — print 가드 + 에러 로그 파일 출력 추가
  - console=False로 최종 빌드 완료, 정상 동작 확인
- **관련 파일**: `manage_portal.py`, `manage_gui.py`, `PortalManager.spec`

### 18:30 - 3차 고도화: Usage Analytics Dashboard
- **요청**: 지사별 포털 사용 현황을 실시간 시각화 대시보드로 확인 (개인정보 수집 금지)
- **결과**:
  - **server/server.py**: POST `/api/event` (익명 이벤트 수집), GET `/api/analytics` (데이터 조회), analytics.json 별도 저장
  - **app.py**: 최초 실행 시 지사 선택 모달(포털 HTML 내), launch 이벤트 fire-and-forget 전송
  - **manage_gui.py**: 탭 네비게이션 추가 (📋 관리 / 📊 대시보드), 대시보드 UI (요약 카드 4종, 지사별 막대 그래프, 7일 트렌드 차트, 상세 테이블), 30초 자동 갱신
  - **portal-data.json**: sites 필드 추가 (9개 지사)
  - exe 빌드 + 배포 zip 생성 (14MB) + 서버/GitHub 배포
  - ⚠️ server.py는 서버 머신(10.4.10.140)에서 수동 교체 + 재시작 필요
- **관련 파일**: `server/server.py`, `app.py`, `manage_gui.py`, `portal-data.json`, `Smart Review Version Portal.html`

### 17:35 - 국기 이모지 + 스페인어 지원 + 빌드/배포
- **요청**: 언어 버튼에 국기 아이콘 추가 + 스페인어(5번째 언어) 추가
- **결과**:
  - 5개 언어 버튼에 국기 이모지 추가 (🇺🇸🇰🇷🇨🇳🇯🇵🇪🇸)
  - 스페인어 완전 지원: UI_TRANSLATIONS, BATCH_LABELS, APP_UPDATE_LABELS, UPDATE_LABELS, changelog_es
  - manage_portal.py: 번역 대상에 es 추가 (Claude API 자동 번역)
  - manage_gui.py: changelog_es/notice_es 필드 연동
  - portal-data.json: notice_es + 전 소프트웨어 changelog_es 추가
  - exe 빌드 + 배포 폴더 복사 + zip 재생성 (14MB)
  - 서버(10.4.10.140:9090) + GitHub Pages 배포 완료
- **관련 파일**: `Smart Review Version Portal.html`, `index.html`, `manage_portal.py`, `manage_gui.py`, `portal-data.json`

### 23:30 - 2차 고도화: exe 자동 업데이트 + 일괄 다운로드
- **요청**: exe 자동 업데이트 기능 + 소프트웨어 일괄 다운로드 기능 추가
- **결과**:
  - **exe 자동 업데이트**: app.py에서 portal-data.json의 app_version과 비교 → 새 버전 다운로드 → _updater.bat로 교체+재시작
  - **앱 업데이트 팝업**: 포털 HTML에 4개 국어 팝업 (재시작/나중에 버튼)
  - **일괄 다운로드**: 체크박스 + 전체 선택 + 일괄 다운로드 버튼 (0.6초 간격 순차 오픈)
  - **관리 GUI**: 전역 설정에 앱 버전 / 다운로드 URL 필드 추가
  - **사용방법.txt 업데이트**: 섹션 8, 9 추가
- **관련 파일**: `app.py`, `Smart Review Version Portal.html`, `index.html`, `manage_gui.py`, `portal-data.json`, `사용방법.txt`

### 22:00 - GitHub Pages 배포 (외부 접근용)
- **요청**: 해외지사 외부 인원도 접근 가능하도록 GitHub Pages 배포
- **결과**:
  - GitHub CLI 인증 완료 (hajunheyok 계정)
  - 공개 리포지토리 생성 + GitHub Pages 활성화
  - 검색엔진 완전 차단 (robots.txt + noindex 메타태그)
  - manage_portal.py에 서버+GitHub 동시 자동 배포 기능 추가
  - `python manage_portal.py` 실행 시 서버(10.4.10.140:9090) + GitHub Pages 동시 업데이트
- **URL**: https://hajunheyok.github.io/smart-review-portal/
- **관련 파일**: `index.html`, `robots.txt`, `manage_portal.py`, `portal-data.json`

## 2026-06-08

### 21:00 - 버전 비교 테스트 및 버그 수정
- **요청**: 실제 설치 파일 다운로드 후 드래그 앤 드롭 버전 비교 테스트
- **결과**: 
  - ONNX, Base Library: `_Installer` 접미사 제거 로직 추가로 해결
  - Graphic Driver: matchPattern을 `desktop`으로 변경하여 해결
  - Review Station 3: `(1)` 중복 다운로드 번호 제거 시 빌드번호 보존 로직 추가
  - SROCV: 확장자 제거 정규식을 알려진 확장자만 제거하도록 변경하여 해결
  - 서버 원격 업데이트: POST 엔드포인트 추가로 curl 업데이트 가능
- **관련 파일**: `Smart Review Version Portal.html`, `portal-data.json`, `server/server.py`, `deploy/SmartReviewPortal.exe`

### 21:15 - 전체 테스트 통과 및 배포 준비 완료
- **요청**: 최종 SROCV 버전 비교 테스트
- **결과**: 9개 소프트웨어 전체 버전 비교 정상 동작 확인
- **배포**: deploy/ 폴더 OneDrive 업로드 완료, 지사 배포만 남음
