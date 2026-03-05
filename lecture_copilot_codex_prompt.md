# Lecture Copilot — Codex 구현 프롬프트 (Phase 1)

## 프로젝트 개요

N100 미니PC(16GB RAM, 512GB SSD)에서 완전히 로컬로 동작하는 AI 강의 보조 시스템을 구축한다.
강사는 미니PC 하나만 들고 다니며 강의할 수 있다.

- HDMI → 프로젝터/대화면: 학생용 슬라이드 표시
- 스마트폰 핫스팟: 인터넷 연결 (Gemini API 호출용)
- 강사 스마트폰: 같은 WiFi로 `http://<N100_IP>:8000/instructor` 접속하여 강사 UI 사용
- USB 마이크: 강사 발화 실시간 인식
- 모든 데이터/모델은 로컬 저장, 외부 의존은 Gemini API 호출뿐

---

## 기술 스택

| 영역 | 기술 | 비고 |
|------|------|------|
| 백엔드 | FastAPI (Python 3.11+) | uvicorn 실행 |
| STT | faster-whisper (small 모델) | 로컬, CPU 동작 |
| LLM | Google Gemini 1.5 Flash API | 무료 티어 사용 |
| Vision | Gemini 1.5 Flash (multimodal) | 이미지 페이지 분석 |
| 임베딩 | sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2) | 로컬, 한국어 지원 |
| 벡터 DB | ChromaDB (로컬 파일 기반) | persist_directory 사용 |
| 자료 파싱 | PyMuPDF (fitz) | PDF 텍스트/이미지 추출 |
| 프론트엔드 | Vue 3 (CDN, 빌드 불필요) + Tailwind CSS (CDN) | 단일 HTML 파일 |
| 실시간 통신 | WebSocket (FastAPI 내장) | 룸 기반 구조 |
| 웨이크워드 | STT 결과 텍스트에서 키워드 매칭 | 로컬, 별도 서비스 불필요 |
| DB | SQLite (aiosqlite) | 세션/설정/참여자 저장 |

---

## 디렉토리 구조

```
lecture_copilot/
├── main.py                          # FastAPI 앱 진입점
├── config.py                        # 전역 설정 (경로, 기본값)
├── requirements.txt
│
├── server/
│   ├── ai/
│   │   ├── stt_engine.py            # faster-whisper STT
│   │   ├── wake_word.py             # 웨이크워드 감지
│   │   ├── context_engine.py        # 발화 맥락 분석
│   │   ├── slide_composer.py        # Gemini로 슬라이드 재구성
│   │   ├── knowledge_retriever.py   # ChromaDB 벡터 검색
│   │   └── agent.py                 # 에이전트 메인 로직 (명령 분기)
│   │
│   ├── ingest/
│   │   ├── pdf_parser.py            # PyMuPDF: 텍스트/이미지 추출
│   │   ├── chunker.py               # 텍스트 청크 분해
│   │   ├── classifier.py            # Gemini로 대/중/소분류 태깅
│   │   └── pipeline.py              # 전체 전처리 파이프라인 오케스트레이터
│   │
│   ├── lecture/
│   │   ├── lecture_plan.py          # 강의 메타데이터 관리
│   │   └── lecture_state.py         # 강의 진행 상태 관리
│   │
│   ├── api/
│   │   ├── ingest_api.py            # 자료 업로드/파이프라인 실행 API
│   │   ├── lecture_api.py           # 강의 설정/상태 API
│   │   ├── slide_api.py             # 슬라이드 조작 API
│   │   ├── knowledge_api.py         # 지식베이스 조회 API
│   │   └── websocket_api.py         # WebSocket 연결 관리
│   │
│   └── db/
│       ├── database.py              # SQLite 연결/초기화
│       └── models.py                # 테이블 정의
│
├── lecture_data/
│   ├── uploads/                     # 강사가 PDF를 넣는 폴더
│   ├── chunks/                      # 추출된 이미지 청크 저장
│   └── chroma_db/                   # ChromaDB 벡터 저장소
│
└── frontend/
    ├── instructor/
    │   └── index.html               # 강사용 UI (Vue3, 3탭)
    └── display/
        └── index.html               # 학생용 디스플레이 (풀스크린)
```

---

## Phase 2 확장을 위한 설계 원칙 (지금 Phase 1에서 반드시 지킬 것)

1. **WebSocket 룸 기반 구조**: 처음부터 룸 딕셔너리로 관리
   ```python
   rooms = {
       "instructor": [],   # 강사 ws
       "display": [],      # 프로젝터 ws
       "students": {}      # Phase 2: {student_id: ws}
   }
   ```
2. **이벤트 타입 정의**: 모든 WebSocket 메시지는 `{"event": "...", "payload": {...}}` 구조
3. **디스플레이 레이어 구조**: HTML에서 z-index로 레이어 분리
   - Layer 1 (z:10): 슬라이드 콘텐츠
   - Layer 2 (z:20): 아바타 표시 영역 (Phase 2용, 지금은 hidden)
   - Layer 3 (z:30): 인터랙션 오버레이 (투표/퀴즈 결과, Phase 2용)
4. **participants 테이블**: SQLite에 미리 생성 (Phase 2에서 바로 사용)
5. **설정값 DB 저장**: 웨이크워드 등 모든 설정은 SQLite settings 테이블에 저장

---

## 상세 구현 명세

---

### 1. config.py

```python
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "lecture_data"
UPLOAD_DIR = DATA_DIR / "uploads"
CHUNK_IMAGE_DIR = DATA_DIR / "chunks"
CHROMA_DIR = DATA_DIR / "chroma_db"
DB_FILE = DATA_DIR / "lecture.db"

# 각 디렉토리 자동 생성
for d in [UPLOAD_DIR, CHUNK_IMAGE_DIR, CHROMA_DIR]:
    d.mkdir(parents=True, exist_ok=True)

WHISPER_MODEL = "small"
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
GEMINI_MODEL = "gemini-1.5-flash"

DEFAULT_WAKE_WORD = "클로드야"
CHUNK_SIZE = 600          # 토큰 기준
CHUNK_OVERLAP = 100
TOP_K_RETRIEVAL = 5       # 벡터 검색 상위 K개
RECOMMEND_COUNT = 3       # 강사에게 추천할 슬라이드 수
STT_CHUNK_SECONDS = 4     # STT 처리 단위 (초)
```

---

### 2. server/db/database.py 및 models.py

SQLite 테이블 스키마:

**settings 테이블**
```sql
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
-- 기본값 삽입
INSERT OR IGNORE INTO settings VALUES ('wake_word', '클로드야', CURRENT_TIMESTAMP);
INSERT OR IGNORE INTO settings VALUES ('gemini_api_key', '', CURRENT_TIMESTAMP);
INSERT OR IGNORE INTO settings VALUES ('whisper_model', 'small', CURRENT_TIMESTAMP);
```

**lecture_plan 테이블**
```sql
CREATE TABLE IF NOT EXISTS lecture_plan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT NOT NULL,
    target_audience TEXT,
    learning_objectives TEXT,    -- JSON array
    total_sessions INTEGER,
    minutes_per_session INTEGER,
    toc TEXT,                    -- JSON array of {id, title, order, session}
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**chunks 테이블**
```sql
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,         -- uuid
    source_file TEXT NOT NULL,
    page_number INTEGER,
    chunk_index INTEGER,
    content_type TEXT NOT NULL,  -- 'text' | 'image'
    content TEXT,                -- 텍스트 내용 또는 이미지 설명
    image_path TEXT,             -- content_type이 image일 때 파일 경로
    category_large TEXT,         -- 대분류
    category_medium TEXT,        -- 중분류
    category_small TEXT,         -- 소분류
    keywords TEXT,               -- JSON array
    embedding_id TEXT,           -- ChromaDB document id
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**lecture_sessions 테이블**
```sql
CREATE TABLE IF NOT EXISTS lecture_sessions (
    id TEXT PRIMARY KEY,         -- uuid
    plan_id INTEGER,
    started_at DATETIME,
    ended_at DATETIME,
    current_section_id TEXT,
    shown_slide_ids TEXT,        -- JSON array
    transcript TEXT              -- 누적 발화 텍스트
);
```

**participants 테이블** (Phase 2용, 지금 미리 생성)
```sql
CREATE TABLE IF NOT EXISTS participants (
    id TEXT PRIMARY KEY,         -- uuid
    session_id TEXT,
    nickname TEXT,
    avatar_emoji TEXT,
    score INTEGER DEFAULT 0,
    joined_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

### 3. server/ingest/pdf_parser.py

PyMuPDF(fitz)를 사용하여 PDF에서 텍스트와 이미지를 추출한다.

구현 요구사항:
- `parse_pdf(pdf_path: Path) -> list[dict]` 함수 구현
- 각 페이지를 순회하며 텍스트 블록과 이미지를 분리 추출
- 텍스트가 거의 없는 페이지(200자 미만)는 이미지 페이지로 분류
- 이미지는 PNG로 `CHUNK_IMAGE_DIR`에 저장 (`{파일명}_p{페이지}_{인덱스}.png`)
- 반환값 형식:
  ```python
  [
    {
      "source_file": "열역학.pdf",
      "page_number": 1,
      "content_type": "text",   # 또는 "image"
      "content": "추출된 텍스트...",
      "image_path": None         # image일 때는 파일 경로
    },
    ...
  ]
  ```

---

### 4. server/ingest/chunker.py

텍스트 페이지를 청크로 분해한다.

구현 요구사항:
- `chunk_text(text: str, source_meta: dict) -> list[dict]` 함수 구현
- CHUNK_SIZE(600자) 기준, CHUNK_OVERLAP(100자) 겹침
- 문장 경계(마침표, 줄바꿈)를 존중하여 자름
- 이미지 타입은 청크 분해 없이 그대로 1개 청크로 처리
- 반환값에 `chunk_index`, `content_type`, `content`, `source_file`, `page_number` 포함

---

### 5. server/ingest/classifier.py

Gemini API를 호출하여 각 청크에 대/중/소 분류와 키워드를 태깅한다.

구현 요구사항:
- `classify_chunk(chunk: dict, subject: str, gemini_api_key: str) -> dict` 함수 구현
- 텍스트 청크: 내용 직접 전달
- 이미지 청크: Gemini Vision API로 이미지 파일을 base64로 인코딩하여 전달
- Gemini에게 보내는 프롬프트:
  ```
  다음은 "{subject}" 과목의 강의 자료입니다.
  아래 내용을 분석하여 JSON으로만 응답하세요 (마크다운 없이):
  {
    "category_large": "대분류명",
    "category_medium": "중분류명",
    "category_small": "소분류명",
    "keywords": ["키워드1", "키워드2", ...],
    "summary": "50자 이내 요약"
  }
  내용: {chunk_content}
  ```
- API 호출 실패 시 재시도 2회, 이후 빈 분류로 처리하고 계속 진행
- Rate limit 방지: 청크당 0.5초 딜레이

---

### 6. server/ingest/pipeline.py

전체 전처리 파이프라인을 오케스트레이션한다.

`run_pipeline(pdf_path: Path, subject: str, gemini_api_key: str, db, chroma_collection)` 함수:

1. PDF 파싱 → 페이지 리스트
2. 청크 분해 → 청크 리스트
3. 청크별 Gemini 분류 (진행률 SSE로 프론트에 전송)
4. sentence-transformers로 임베딩 생성
5. ChromaDB에 저장 (document: content, metadata: 분류/키워드/source 등)
6. SQLite chunks 테이블에 저장
7. 완료 이벤트 전송

진행률 보고 형식:
```python
{"step": "parsing", "progress": 10, "message": "PDF 파싱 중..."}
{"step": "chunking", "progress": 30, "message": "청크 분해 중... (45/120)"}
{"step": "classifying", "progress": 60, "message": "AI 분류 중... (45/120)"}
{"step": "embedding", "progress": 85, "message": "임베딩 생성 중..."}
{"step": "done", "progress": 100, "message": "완료"}
```

---

### 7. server/ai/stt_engine.py

faster-whisper를 사용한 실시간 STT 엔진.

구현 요구사항:
- `STTEngine` 클래스
- `__init__`: faster-whisper WhisperModel 로드 (`small`, `device="cpu"`, `compute_type="int8"`)
- `transcribe_chunk(audio_bytes: bytes) -> str`: 오디오 바이트 → 텍스트
  - 입력: 16kHz, 16bit, mono PCM bytes
  - language="ko" 고정
  - 반환: 인식된 텍스트 문자열
- 싱글톤으로 관리 (앱 시작 시 1회 로드)

---

### 8. server/ai/wake_word.py

STT 결과 텍스트에서 웨이크워드와 명령을 감지한다.

구현 요구사항:
- `WakeWordDetector` 클래스
- `__init__(wake_word: str)`: 웨이크워드 설정
- `detect(text: str) -> dict | None`: 웨이크워드 포함 여부 감지
  - 웨이크워드 없으면 `None` 반환
  - 있으면 명령 분류 반환:
    ```python
    {"command": "show_image", "raw": "클로드야 그 사진 줘봐"}
    {"command": "show_detail", "raw": "클로드야 더 자세히 설명해줘"}
    {"command": "next_section", "raw": "클로드야 다음 내용 뭐야"}
    {"command": "make_quiz", "raw": "클로드야 예제 문제 내줘"}
    {"command": "show_original", "raw": "클로드야 원문 보여줘"}
    {"command": "unknown", "raw": "클로드야 ..."}
    ```
- 명령 분류는 키워드 매칭으로 처리:
  - "사진", "그림", "이미지" → show_image
  - "자세히", "상세", "원문" → show_detail
  - "다음", "넘어가" → next_section
  - "퀴즈", "문제", "테스트" → make_quiz
- `update_wake_word(new_word: str)`: 웨이크워드 변경

---

### 9. server/ai/knowledge_retriever.py

ChromaDB에서 관련 청크를 벡터 검색으로 가져온다.

구현 요구사항:
- `KnowledgeRetriever` 클래스
- `search(query: str, top_k: int = 5, filter_type: str = None) -> list[dict]`
  - query를 임베딩으로 변환 후 ChromaDB 유사도 검색
  - filter_type: `"text"` 또는 `"image"` 또는 None(전체)
  - 반환값: `[{id, content, content_type, image_path, category_large, category_medium, category_small, keywords, score}, ...]`
- `search_by_category(category_small: str, top_k: int) -> list[dict]`: 소분류로 검색
- sentence-transformers 임베딩 모델은 STT 엔진처럼 싱글톤으로 관리

---

### 10. server/ai/slide_composer.py

검색된 청크를 Gemini API로 강의용 슬라이드로 재구성한다.

구현 요구사항:
- `SlideComposer` 클래스
- `compose(chunks: list[dict], context: dict, gemini_api_key: str) -> dict`
  - context: `{subject, target_audience, current_section, transcript_recent}`
  - Gemini에게 보내는 프롬프트:
    ```
    당신은 강의 슬라이드 전문 디자이너입니다.
    과목: {subject}
    대상: {target_audience}
    현재 섹션: {current_section}
    강사 최근 발화: {transcript_recent}

    아래 자료를 바탕으로 강의 슬라이드 1장을 JSON으로만 구성하세요 (마크다운 없이):
    {
      "title": "슬라이드 제목 (15자 이내)",
      "bullets": ["핵심 포인트 1 (20자 이내)", "핵심 포인트 2", ...],  // 최대 4개
      "image_id": "관련 이미지 청크 id 또는 null",
      "note": "강사 참고 노트 (50자 이내)",
      "source_chunk_ids": ["chunk_id1", ...]
    }
    슬라이드 원칙: 글씨 최소화, 핵심만, 학습자 수준에 맞게

    자료:
    {chunks_content}
    ```
  - 반환: 슬라이드 dict
- `compose_detail(chunk: dict) -> dict`: 원문 표시용 (재구성 없이 원문 그대로)

---

### 11. server/ai/agent.py

에이전트 메인 로직. STT 결과를 받아 적절한 액션을 결정하고 실행한다.

구현 요구사항:
- `LectureAgent` 클래스
- `process_transcript(text: str) -> list[dict]`: 일반 발화 처리
  1. WakeWordDetector로 웨이크워드 감지
  2. 웨이크워드 없으면: ContextEngine으로 맥락 업데이트 → 슬라이드 추천
  3. 웨이크워드 있으면: 명령에 따라 즉각 실행
     - show_image → 이미지 타입 청크 검색 → 즉시 표시
     - show_detail → 현재 슬라이드 원문 표시
     - next_section → 다음 섹션으로 이동 유도
     - make_quiz → Gemini로 퀴즈 생성
  4. 결과를 WebSocket으로 브로드캐스트
- `get_recommendations() -> list[dict]`: 현재 맥락 기반 슬라이드 추천 3개 반환
- `make_quiz(context: str) -> dict`: 현재 섹션 내용으로 OX/객관식 퀴즈 생성

WebSocket 브로드캐스트 이벤트 타입:
```python
# 슬라이드 추천 업데이트
{"event": "recommendations_update", "payload": {"slides": [...]}}

# 슬라이드 변경 (학생 화면에도 전송)
{"event": "slide_change", "payload": {"slide": {...}}}

# 에이전트 메시지
{"event": "agent_message", "payload": {"message": "...", "type": "info|warning|suggestion"}}

# STT 자막
{"event": "transcript_update", "payload": {"text": "...", "is_final": true}}

# 진도 업데이트
{"event": "progress_update", "payload": {"section_id": "...", "progress_pct": 35}}
```

---

### 12. server/api/websocket_api.py

WebSocket 연결 관리. Phase 2 확장을 위해 룸 기반으로 구현.

```python
class ConnectionManager:
    def __init__(self):
        self.rooms: dict[str, list[WebSocket]] = {
            "instructor": [],
            "display": [],
            "students": [],   # Phase 2
        }

    async def connect(self, ws: WebSocket, room: str):
        await ws.accept()
        self.rooms[room].append(ws)

    async def disconnect(self, ws: WebSocket, room: str):
        self.rooms[room].remove(ws)

    async def broadcast_to_room(self, room: str, message: dict):
        # 해당 룸의 모든 연결에 전송

    async def broadcast_to_all(self, message: dict):
        # 모든 룸에 전송

# 엔드포인트
# GET /ws/instructor  → instructor 룸
# GET /ws/display     → display 룸
# GET /ws/student     → students 룸 (Phase 2)
```

---

### 13. server/api/ingest_api.py

자료 업로드 및 전처리 파이프라인 실행 API.

엔드포인트:
- `POST /api/ingest/upload`: PDF 파일 업로드 (`UPLOAD_DIR`에 저장)
- `POST /api/ingest/run`: 특정 파일 또는 전체 파이프라인 실행 (백그라운드 태스크)
- `GET /api/ingest/progress`: SSE(Server-Sent Events)로 진행률 스트림
- `GET /api/ingest/files`: 업로드된 파일 목록
- `DELETE /api/ingest/files/{filename}`: 파일 및 관련 청크 삭제

---

### 14. server/api/knowledge_api.py

지식베이스 조회 API (강사 UI 탭 3용).

엔드포인트:
- `GET /api/knowledge/tree`: 대/중/소 분류 트리 전체 반환
  ```json
  [
    {
      "id": "열역학",
      "label": "열역학",
      "type": "large",
      "children": [
        {
          "id": "열전달",
          "label": "열전달",
          "type": "medium",
          "children": [
            {"id": "uuid-...", "label": "전도", "type": "small", "chunk_count": 3}
          ]
        }
      ]
    }
  ]
  ```
- `GET /api/knowledge/chunks?category_small={id}`: 특정 소분류의 청크 목록
- `GET /api/knowledge/chunks/{chunk_id}`: 청크 상세 (원문 또는 이미지)
- `GET /api/knowledge/search?q={query}`: 텍스트 검색

---

### 15. server/api/lecture_api.py

강의 설정/상태 관리 API.

엔드포인트:
- `GET /api/lecture/plan`: 현재 강의 계획 조회
- `POST /api/lecture/plan`: 강의 계획 저장 (과목명, 목표, 대상, 시간, 목차)
- `GET /api/lecture/state`: 현재 강의 상태 (진행 섹션, 시간, 진도율)
- `POST /api/lecture/state/section`: 현재 섹션 변경
- `POST /api/lecture/session/start`: 강의 세션 시작
- `POST /api/lecture/session/end`: 강의 세션 종료 (요약 생성)
- `GET /api/settings`: 설정 전체 조회
- `POST /api/settings`: 설정 저장 (웨이크워드, API 키 등)

---

### 16. server/api/slide_api.py

슬라이드 조작 API.

엔드포인트:
- `POST /api/slide/show`: 특정 슬라이드를 학생 화면에 표시 (WebSocket broadcast)
- `GET /api/slide/recommendations`: 현재 맥락 기반 추천 슬라이드 3개
- `POST /api/slide/compose`: 청크 ID 리스트로 슬라이드 직접 재구성 요청
- `GET /api/slide/current`: 현재 표시 중인 슬라이드

---

### 17. 오디오 처리 흐름 (WebSocket + STT)

강사 브라우저에서 Web Audio API로 마이크 오디오를 캡처하여 WebSocket으로 서버에 전송한다.

**프론트엔드 (instructor/index.html):**
```javascript
// 4초 단위로 오디오 청크를 ArrayBuffer로 전송
navigator.mediaDevices.getUserMedia({ audio: true })
  .then(stream => {
    const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' })
    mediaRecorder.ondataavailable = (e) => {
      ws.send(e.data)  // WebSocket으로 전송
    }
    mediaRecorder.start(4000)  // 4초마다 청크
  })
```

**서버 (websocket_api.py):**
```python
@router.websocket("/ws/audio")
async def audio_ws(ws: WebSocket):
    await ws.accept()
    while True:
        audio_bytes = await ws.receive_bytes()
        # ffmpeg로 webm → pcm 변환
        pcm = convert_webm_to_pcm(audio_bytes)
        # STT
        text = stt_engine.transcribe_chunk(pcm)
        # 에이전트 처리
        await agent.process_transcript(text)
```

오디오 변환: ffmpeg 커맨드라인 호출로 webm → 16kHz mono PCM 변환

---

### 18. frontend/instructor/index.html (강사 UI)

Vue 3 CDN + Tailwind CSS CDN으로 단일 HTML 파일로 구현.

**3탭 구조:**

**탭 1: 설정 (⚙️ 설정)**
- 섹션 1 - AI 설정:
  - Gemini API 키 입력 (password 타입)
  - 웨이크워드 입력 (기본값: "클로드야")
  - Whisper 모델 선택 (tiny/small/medium)
  - 저장 버튼
- 섹션 2 - 강의 정보:
  - 과목명 (text input)
  - 강의 대상 (text input)
  - 학습 목표 (textarea, 여러 줄)
  - 총 차시 수 (number), 차시당 시간 (number, 분)
  - 학습 목차 (동적 추가/삭제 가능한 리스트: 차시번호, 섹션명)
  - 저장 버튼
- 섹션 3 - 자료 관리:
  - PDF 파일 업로드 (drag & drop 또는 클릭)
  - 업로드된 파일 목록 (삭제 버튼 포함)
  - 파이프라인 실행 버튼 ("AI 분석 시작")
  - 진행률 바 (SSE로 실시간 업데이트)

**탭 2: 강의 중 (🎙️ 강의)**
- 상단: 강의 시작/종료 버튼, 경과 시간, 현재 섹션
- 중앙 좌측 (2/3 너비):
  - 추천 슬라이드 카드 3개 (가로 배열)
    - 슬라이드 제목, 핵심 포인트 미리보기
    - "표시" 버튼 클릭 시 학생 화면에 전송
    - 현재 표시 중인 슬라이드 하이라이트
  - 현재 표시 중인 슬라이드 미리보기
- 중앙 우측 (1/3 너비):
  - 실시간 STT 자막 (스크롤)
  - 에이전트 메시지 알림 (배지 형태)
  - 웨이크워드 감지 표시등 (녹색/빨간 점)
- 하단: 목차 진도바 (섹션별 세그먼트, 현재 위치 표시)

**탭 3: 지식베이스 (📚 자료)**
- 좌측 패널 (1/3): 대/중/소 분류 트리 (접기/펼치기)
- 우측 패널 (2/3):
  - 선택한 분류의 청크 카드 목록
  - 각 카드: 소분류명, 키워드 태그, 내용 미리보기 (100자)
  - 카드 클릭 시 전체 내용 모달 표시
  - 이미지 청크는 이미지 썸네일 표시
  - 상단 검색창

---

### 19. frontend/display/index.html (학생용 디스플레이)

**요구사항:**
- 풀스크린, 검정 배경
- 3개 레이어 (CSS z-index로 분리):
  ```html
  <!-- Layer 1: 슬라이드 -->
  <div id="slide-layer" style="z-index:10">
    <h1 id="slide-title"></h1>
    <ul id="slide-bullets"></ul>
    <img id="slide-image" />
    <div id="slide-progress-bar"></div>  <!-- 하단 얇은 진도바 -->
  </div>
  <!-- Layer 2: 아바타 (Phase 2용, 지금 hidden) -->
  <div id="avatar-layer" style="z-index:20; display:none"></div>
  <!-- Layer 3: 인터랙션 오버레이 (Phase 2용, 지금 hidden) -->
  <div id="interaction-layer" style="z-index:30; display:none"></div>
  ```
- WebSocket `/ws/display` 연결, `slide_change` 이벤트 수신하여 화면 업데이트
- 슬라이드 전환 시 페이드 인/아웃 애니메이션
- 상단 좌측: 과목명, 현재 섹션명 (작은 글씨)
- 하단: 얇은 진도바

---

### 20. main.py

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작 시 초기화
    await init_db()
    load_stt_engine()        # faster-whisper 모델 로드 (시간 걸림)
    load_embedding_model()   # sentence-transformers 로드
    init_chroma()            # ChromaDB 연결
    init_agent()             # 에이전트 초기화
    yield
    # 종료 시 정리

app = FastAPI(title="Lecture Copilot", lifespan=lifespan)

# 정적 파일
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")
app.mount("/chunks", StaticFiles(directory="lecture_data/chunks"), name="chunks")

# 라우터 등록
app.include_router(ingest_router)
app.include_router(lecture_router)
app.include_router(slide_router)
app.include_router(knowledge_router)
app.include_router(websocket_router)

@app.get("/")
def root():
    return {"status": "ok", "instructor": "/instructor", "display": "/display"}

@app.get("/instructor")
def instructor():
    return FileResponse("frontend/instructor/index.html")

@app.get("/display")
def display():
    return FileResponse("frontend/display/index.html")
```

---

### 21. requirements.txt

```
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
python-multipart
aiosqlite
faster-whisper>=1.0.0
sentence-transformers>=2.6.0
chromadb>=0.4.22
pymupdf>=1.23.0
google-generativeai>=0.5.0
Pillow>=10.0.0
aiofiles
sse-starlette
```

---

## 실행 방법

```bash
# 설치
pip install -r requirements.txt

# 실행
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 접속
# 강사 (스마트폰): http://<N100_IP>:8000/instructor
# 학생 (프로젝터): http://localhost:8000/display
```

N100 IP 확인: `ip addr show` 또는 `hostname -I`

---

## Phase 2 구현 시 추가할 것 (참고용)

- `/ws/student` WebSocket 엔드포인트 활성화
- QR 코드 생성 API (`/api/session/qr`)
- 학습자 닉네임/아바타 등록 (`POST /api/student/join`)
- 투표 생성/집계 (`POST /api/quiz/create`, `POST /api/quiz/answer`)
- 학생 화면 avatar-layer, interaction-layer 활성화
- 점수 집계 및 리더보드 (`GET /api/session/scores`)

---

## UI 한국어 텍스트 명세

**모든 UI 텍스트는 예외 없이 한국어로 작성한다.** 영어 라벨, 버튼, 안내문구, 에러 메시지를 절대 사용하지 말 것.

### 강사 UI 탭 명칭
```
탭 1: ⚙️ 설정
탭 2: 🎙️ 강의
탭 3: 📚 자료
```

### 탭 1 (설정) 한국어 텍스트
```
[AI 설정]
  라벨: "Gemini API 키"
  라벨: "웨이크워드"
  플레이스홀더: "예: 클로드야"
  라벨: "Whisper 모델"
  옵션: "빠름 (tiny)", "보통 (small)", "정확 (medium)"
  버튼: "설정 저장"

[강의 정보]
  라벨: "과목명"
  라벨: "강의 대상"
  플레이스홀더: "예: 공학과 2학년"
  라벨: "학습 목표"
  플레이스홀더: "목표를 한 줄씩 입력하세요"
  라벨: "총 차시 수"
  라벨: "차시당 시간 (분)"
  라벨: "학습 목차"
  버튼: "+ 섹션 추가"
  버튼: "삭제"
  버튼: "강의 정보 저장"

[자료 관리]
  안내문: "PDF 파일을 여기에 끌어다 놓거나 클릭하여 업로드하세요"
  안내문: "※ HWP, PPT 파일은 PDF로 변환 후 업로드하세요"
  버튼: "AI 분석 시작"
  버튼: "삭제"
  진행상태: "PDF 파싱 중..."
  진행상태: "청크 분해 중... (45/120)"
  진행상태: "AI 분류 중... (45/120)"
  진행상태: "임베딩 생성 중..."
  진행상태: "✅ 분석 완료"
```

### 탭 2 (강의) 한국어 텍스트
```
  버튼: "강의 시작"
  버튼: "강의 종료"
  라벨: "경과 시간"
  라벨: "현재 섹션"
  라벨: "AI 추천 슬라이드"
  버튼: "화면에 표시"        ← 학생 화면으로 전송
  버튼: "더 자세히"          ← 원문 표시 요청
  라벨: "현재 표시 중"
  라벨: "실시간 자막"
  라벨: "AI 메시지"
  상태표시: "🔴 대기 중"
  상태표시: "🟢 웨이크워드 감지됨"
  라벨: "강의 진도"
  안내문: "강의를 시작하면 AI가 슬라이드를 추천합니다"

에이전트 메시지 예시:
  "다음 섹션으로 넘어가실 때가 된 것 같습니다."
  "현재 섹션 진도율: 80%"
  "관련 이미지 자료가 있습니다."
```

### 탭 3 (자료) 한국어 텍스트
```
  플레이스홀더: "자료 검색..."
  라벨: "분류 트리"
  라벨: "대분류"
  라벨: "중분류"
  라벨: "소분류"
  라벨: "청크 목록"
  라벨: "키워드"
  버튼: "원문 보기"
  안내문: "왼쪽 트리에서 분류를 선택하세요"
  안내문: "분석된 자료가 없습니다. 설정 탭에서 자료를 업로드하세요."
```

### 학생용 디스플레이 한국어 텍스트
```
  상단 좌측: "{과목명} | {현재 섹션명}"
  하단 진도바 툴팁: "{현재 섹션} ({진도율}%)"
```

### 공통 에러/안내 메시지
```
  "Gemini API 키를 설정 탭에서 먼저 입력해주세요."
  "마이크 접근 권한이 필요합니다."
  "서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요."
  "파일 업로드에 실패했습니다."
  "분석 중 오류가 발생했습니다. 다시 시도해주세요."
  "저장되었습니다."
  "삭제하시겠습니까?"
  "확인"
  "취소"
```

---

## Gemini API 토큰 사용량 및 무료 한도 안내

### 청크 1개당 토큰 소비
```
입력: 시스템 프롬프트(150) + 청크 내용(400) = 약 550 토큰
출력: JSON 응답 = 약 100 토큰
청크 1개 합계: 약 650 토큰
```

### 자료 규모별 예상 토큰
```
강의 1과목  (PDF 50쪽)   → 청크 75개   → 약 49,000 토큰  → 당일 처리 가능
강의 5과목  (PDF 250쪽)  → 청크 375개  → 약 244,000 토큰 → 당일 처리 가능
강의 20과목 (PDF 1,000쪽)→ 청크 1,500개→ 약 975,000 토큰 → 2~3일 분산 처리
```

### Gemini 1.5 Flash 무료 티어 한도
```
일일 요청 한도:   1,500회
분당 요청 한도:   15회
일일 토큰 한도:   1,000,000 토큰
```

### 파이프라인 구현 시 반드시 지킬 것
- 청크당 **0.5초 딜레이** 필수 (분당 15회 한도 준수)
- API 호출 실패 시 **최대 2회 재시도** 후 빈 분류로 처리하고 계속 진행 (중단 금지)
- 이미지 청크는 텍스트보다 토큰 소비가 2~3배 많을 수 있음을 고려
- 파이프라인은 **중단 후 재시작 가능**하도록 구현 (이미 처리된 청크는 건너뜀)
  - SQLite chunks 테이블에 처리 완료 여부 컬럼(`is_processed BOOLEAN DEFAULT FALSE`) 추가
  - 파이프라인 시작 시 `is_processed = FALSE` 인 청크만 처리

---

## 주의사항 및 N100 성능 최적화

1. faster-whisper는 앱 시작 시 1회만 로드, 싱글톤 유지
2. sentence-transformers 임베딩 모델도 싱글톤 유지
3. Gemini API 호출은 비동기(async)로 처리, 절대 블로킹하지 말 것
4. ChromaDB persist_directory 사용으로 재시작 시 재구축 불필요
5. STT는 백그라운드 태스크로 처리, 메인 스레드 블로킹 금지
6. 이미지 파일은 원본 저장 후 썸네일(200px)도 별도 생성하여 UI 성능 확보
7. 앱 시작 시 모델 로딩에 30~60초 소요될 수 있음 — 시작 화면에 "모델 로딩 중..." 안내 표시
8. N100은 멀티스레드 성능이 낮으므로 CPU 집약 작업(임베딩 생성)은 `asyncio.run_in_executor`로 처리
