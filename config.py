from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "lecture_data"
UPLOAD_DIR = DATA_DIR / "uploads"
CHUNK_IMAGE_DIR = DATA_DIR / "chunks"
CHROMA_DIR = DATA_DIR / "chroma_db"
DB_FILE = DATA_DIR / "lecture.db"

for d in [UPLOAD_DIR, CHUNK_IMAGE_DIR, CHROMA_DIR]:
    d.mkdir(parents=True, exist_ok=True)

WHISPER_MODEL = "small"
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
GEMINI_MODEL = "gemini-1.5-flash"

DEFAULT_WAKE_WORD = "코덱스야"
CHUNK_SIZE = 600
CHUNK_OVERLAP = 100
TOP_K_RETRIEVAL = 5
RECOMMEND_COUNT = 3
STT_CHUNK_SECONDS = 4
