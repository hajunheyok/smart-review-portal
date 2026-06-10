# 상시 롤백 다운로드 기능 설계

> 2026-06-10 | SMART Review Version Portal

## 목적

배포된 최신 버전에 치명적 이슈(코너케이스 등) 발생 시, 본사 및 해외 지사 모든 사용자가 즉시 검증된 안정 버전을 다운로드하여 현장 대응할 수 있도록 상시 롤백 다운로드 기능을 제공한다.

## 핵심 컨셉

- 전체 SW를 하나의 압축파일로 묶어 OneDrive에 상시 업로드
- 포탈 화면에 토글 스위치를 항상 표시하여, 사용자가 필요 시 직접 ON/OFF
- 긴급 상황 시 별도 긴급 모드 불필요 — Portal Manager에서 최신 버전 링크를 직접 교체하면 됨

## 1. 데이터 구조

`portal-data.json` 최상위에 2개 필드 추가:

```json
{
  "rollbackLink": "https://kohyoung-my.sharepoint.com/..../SMART_Review_2.3_Rollback.zip",
  "rollbackLabel": "SMART Review 2.3 롤백 버전",
  "lastUpdated": "2026-06-09",
  "software": [...]
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `rollbackLink` | string | 롤백 압축파일 OneDrive 공유 링크. 항상 값이 존재 |
| `rollbackLabel` | string | 포탈에 표시할 이름. 예: "SMART Review 2.3 롤백 버전" |

## 2. Portal Manager GUI 변경

기존 화면 상단(공지사항 영역 근처)에 2개 입력란 추가:

- **롤백 링크** — OneDrive 압축파일 URL 입력/수정
- **롤백 라벨** — 포탈에 표시할 이름 (기본값: "SMART Review 2.3 롤백 버전")

배포 시 `rollbackLink`, `rollbackLabel`이 portal-data.json에 포함되어 서버(10.4.10.140:9090) + GitHub Pages에 동시 반영된다. 기존 배포 흐름과 동일하며 추가 조작 불필요.

## 3. 포탈 화면 (사용자 측)

### 토글 스위치

- 포탈 화면에 **"롤백 버전"** 토글 스위치를 항상 표시
- 토글은 클라이언트 사이드 전용 (서버에 상태 저장하지 않음)
- 페이지 새로고침 시 OFF 상태로 초기화

### 토글 OFF (기본)

- 평소 화면 그대로. 롤백 관련 영역 숨김

### 토글 ON

- 롤백 다운로드 영역이 나타남
- 라벨명 + 다운로드 버튼 표시
- 다운로드 버튼 클릭 시 OneDrive 링크로 이동

### 다국어 지원

- 토글 스위치 라벨, 다운로드 버튼 텍스트는 기존 다국어 체계(6개 언어)에 맞춰 번역
- `rollbackLabel`은 관리자가 입력한 값을 그대로 표시 (제품 버전명이므로 번역 불필요)

## 4. 변경 대상 파일

| 파일 | 변경 내용 |
|------|-----------|
| `manage_gui.py` | 롤백 링크/라벨 입력란 UI 추가, API 엔드포인트에 롤백 필드 포함 |
| `manage_portal.py` | `read_portal_data`/`write_portal_data`에서 rollback 필드 읽기/쓰기 |
| `portal-data.json` | `rollbackLink`, `rollbackLabel` 필드 추가 |
| `Smart Review Version Portal.html` | 토글 스위치 + 롤백 다운로드 영역 UI 추가 |
| `index.html` | 위 HTML과 동일 (GitHub Pages용 복사본) |

## 5. 배포 흐름

기존과 동일:

1. Portal Manager에서 롤백 링크/라벨 입력 (또는 수정)
2. 배포 버튼 클릭
3. portal-data.json에 rollback 필드 포함 → 서버 + GitHub Pages 동시 배포
4. 전체 사용자(본사+해외) 포탈에 즉시 반영
