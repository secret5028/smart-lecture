from __future__ import annotations

SETTINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

DEFAULT_SETTINGS_SQL = [
    "INSERT OR IGNORE INTO settings VALUES ('wake_word', '코덱스야', CURRENT_TIMESTAMP);",
    "INSERT OR IGNORE INTO settings VALUES ('gemini_api_key', '', CURRENT_TIMESTAMP);",
    "INSERT OR IGNORE INTO settings VALUES ('whisper_model', 'small', CURRENT_TIMESTAMP);",
    "INSERT OR IGNORE INTO settings VALUES ('upload_dir', '', CURRENT_TIMESTAMP);",
]

LECTURE_PLAN_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS lecture_plan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT NOT NULL,
    target_audience TEXT,
    learning_objectives TEXT,
    total_sessions INTEGER,
    minutes_per_session INTEGER,
    toc TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

CHUNKS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    source_file TEXT NOT NULL,
    page_number INTEGER,
    chunk_index INTEGER,
    content_type TEXT NOT NULL,
    content TEXT,
    image_path TEXT,
    category_large TEXT,
    category_medium TEXT,
    category_small TEXT,
    keywords TEXT,
    embedding_id TEXT,
    is_processed BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

LECTURE_SESSIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS lecture_sessions (
    id TEXT PRIMARY KEY,
    plan_id INTEGER,
    started_at DATETIME,
    ended_at DATETIME,
    current_section_id TEXT,
    shown_slide_ids TEXT,
    transcript TEXT
);
"""

PARTICIPANTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS participants (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    nickname TEXT,
    avatar_emoji TEXT,
    score INTEGER DEFAULT 0,
    joined_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

ALL_TABLES_SQL = [
    SETTINGS_TABLE_SQL,
    LECTURE_PLAN_TABLE_SQL,
    CHUNKS_TABLE_SQL,
    LECTURE_SESSIONS_TABLE_SQL,
    PARTICIPANTS_TABLE_SQL,
]
