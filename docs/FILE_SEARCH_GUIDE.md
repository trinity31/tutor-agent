# Gemini File Search Store 가이드

## 구조 개요

```
사용자 1명 = Store 1개 = 그 사용자의 모든 과목 PDF

Gemini File Search Store (tutor-test_user)
├── ym2y94byzmdm  (PDF)       ← 폴더 없이 flat하게 저장
├── 2kqll4bm7s20  (PDF)       ← document ID로만 식별
├── ...
└── gs5wql6pm4eq  (PDF)
    = 84개 문서, 과목 구분 없음

로컬 (tutor-agent 프로젝트)
└── materials/test_user/manifest.json  ← 어떤 파일이 있는지 여기서 관리
```

- Store 내부에 **폴더 개념 없음** — 모든 PDF가 flat하게 저장
- **manifest는 Store에 업로드되지 않음** — 로컬에만 존재
- 과목 구분은 **manifest + 검색 힌트**로 처리

## 사용자별 Store 구조

```
tutor-user_a  (Store) → 사용자 A의 모든 PDF
tutor-user_b  (Store) → 사용자 B의 모든 PDF
tutor-test_user (Store) → 테스트용 (84개 PDF)
```

- Store 개수에 따른 추가 비용 없음
- 과금 기준: 초기 인덱싱 토큰 수 ($0.15/1M 토큰, 1회성)
- 스토리지 및 검색 쿼리 임베딩: 무료

## 검색 흐름

```
사용자: "양택풍수론 4주차"
  → manifest에서 display_name 매칭 (LLM)
  → "양택풍수론 - 제04주차_전통건축의 이해 한옥과 문화재 풍수"
  → 검색 쿼리에 "이 파일만 정리해줘" 힌트 포함
  → Gemini가 Store 내 84개 문서에서 해당 내용만 찾아 반환
```

## 서비스 계층

```
[CLI] setup_store.py ──────────┐
[추후] REST API ───────────────┤
[추후] Slack/카카오톡 어댑터 ──┤
                               ▼
                   tutor_agent/file_search.py  ← 유일한 접근점
                   ├── get_or_create_store()   # Store 생성/조회
                   ├── upload_pdf()            # 개별 파일 업로드
                   ├── upload_pdfs()           # 일괄 업로드
                   ├── save_manifest()         # manifest 저장
                   ├── load_manifest()         # manifest 로드
                   ├── find_matching_file()    # LLM 기반 파일 매칭
                   └── search()               # File Search 실행
```

## CLI 명령어

### Store 세팅 (최초 1회)

```bash
# 업로드 대상 확인
uv run python setup_store.py --user-id test_user --knowledge-dir /path/to/pdfs --dry-run

# Store 생성 + PDF 업로드 + manifest 생성
uv run python setup_store.py --user-id test_user --knowledge-dir /path/to/pdfs

# Store 재생성 (기존 삭제 후 새로 만듦)
uv run python setup_store.py --user-id test_user --knowledge-dir /path/to/pdfs --reset
```

### Store 조회

```bash
# Store 목록
uv run python -c "
from tutor_agent.file_search import get_client
for store in get_client().file_search_stores.list():
    print(f'{store.name}  ({store.display_name})')
"

# Store 상세 정보
uv run python -c "
from tutor_agent.file_search import get_client
store = get_client().file_search_stores.get(name='fileSearchStores/tutortestuser-jb5wchn3gcxp')
print(f'Name: {store.name}')
print(f'Display Name: {store.display_name}')
"
```

### Document 조회

```bash
# Store 내 문서 목록 (document ID, 용량, 상태)
uv run python -c "
from tutor_agent.file_search import get_client
for doc in get_client().file_search_stores.documents.list(parent='fileSearchStores/tutortestuser-jb5wchn3gcxp'):
    print(f'{doc.name}  {doc.size_bytes}bytes  {doc.state}')
"

# Store 내 총 문서 수 및 용량
uv run python -c "
from tutor_agent.file_search import get_client
total_bytes = 0
count = 0
for doc in get_client().file_search_stores.documents.list(parent='fileSearchStores/tutortestuser-jb5wchn3gcxp'):
    total_bytes += doc.size_bytes or 0
    count += 1
print(f'문서 수: {count}개')
print(f'총 용량: {total_bytes:,} bytes ({total_bytes / 1024 / 1024:.1f} MB)')
"
```

### Manifest 조회

```bash
# manifest 내용 확인 (사람이 읽을 수 있는 파일 목록)
cat materials/test_user/manifest.json
```

### 검색 테스트

```bash
# 검색 테스트
uv run python -c "
from tutor_agent.file_search import search
result = search(query='양택풍수론 4주차 핵심 개념 정리', user_message='양택풍수론 4주차')
print(result[:500])
"

# LangGraph Studio에서 테스트
uv run langgraph dev
```

## 비용 (Free 티어 기준)

| 항목 | 비용 |
|------|------|
| Store 생성 | 무료 (개수 무제한) |
| 스토리지 | 무료 (Free 1GB / Tier1 10GB) |
| 검색 쿼리 임베딩 | 무료 |
| 초기 인덱싱 | $0.15 / 1M 토큰 (업로드 시 1회) |
| 검색 결과 토큰 | 표준 컨텍스트 토큰으로 과금 |

현재 test_user Store: 84개 PDF, 453MB → 인덱싱 비용 약 $0.15~$0.30 (1회성)

## 참고

- Google AI Studio Files 탭에서 업로드된 원본 파일 확인 가능: https://aistudio.google.com
- Files API로 업로드된 원본 파일은 48시간 후 삭제되지만, Store에 import된 데이터는 수동 삭제 전까지 영구 보존
- Store의 document에는 원본 display_name이 보존되지 않으므로, manifest를 별도로 관리해야 함
- 상품화 시 Manifest 파일은 DB 나 클라우드 스토리지로 옮겨야 하며, 사용자 수가 많아지면 Google File Search Store 에서 Pinecone 등의 Vector DB 로 마이그레이션 해야 함
