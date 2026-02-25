-- InterviewIQ Database Schema
-- SQLite (swap for PostgreSQL in production)

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    username TEXT NOT NULL,
    password_hash TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    profile_data TEXT  -- JSON: job_title, target_companies, experience_level
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    session_token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_used_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id TEXT PRIMARY KEY,
    resume_text TEXT,
    resume_filename TEXT,
    target_role TEXT,
    target_company TEXT,
    focus_areas TEXT,                -- JSON array
    onboarding_complete BOOLEAN DEFAULT 0,
    mic_permission_granted BOOLEAN DEFAULT 0,
    job_description TEXT,
    question_count_override INTEGER,
    evaluation_thresholds TEXT,
    recording_thresholds TEXT,
    interviewer_persona TEXT DEFAULT 'friendly',
    piper_style TEXT DEFAULT 'interviewer',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS user_progress (
    user_id TEXT PRIMARY KEY,
    total_sessions INTEGER DEFAULT 0,
    total_questions_answered INTEGER DEFAULT 0,
    average_score REAL DEFAULT 0.0,
    skill_scores TEXT,              -- JSON: {"Python": 7.5, "System Design": 6.2, ...}
    weak_areas TEXT,                -- JSON: ["concurrency", "caching strategies", ...]
    strong_areas TEXT,              -- JSON: ["algorithms", "data structures", ...]
    action_queue TEXT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS career_analyses (
    analysis_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    job_title TEXT NOT NULL,
    company TEXT,
    readiness_score REAL,
    skill_gaps TEXT,                 -- JSON array
    bridge_roles TEXT,              -- JSON array
    analysis_data TEXT,             -- JSON: full analysis result
    suggested_sessions TEXT,
    job_description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS interview_sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    job_title TEXT,
    mode TEXT,                      -- 'practice' or 'coaching'
    total_questions INTEGER,
    answered_questions INTEGER,
    skipped_questions INTEGER,
    average_score REAL,
    summary_data TEXT,              -- JSON: full summary from generate_interview_summary
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS interview_answers (
    answer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    question_number INTEGER NOT NULL,
    question_text TEXT NOT NULL,
    question_category TEXT,
    question_difficulty TEXT,
    user_answer TEXT NOT NULL,
    evaluation_data TEXT,           -- JSON: score, breakdown, strengths, improvements
    duration_seconds REAL,
    skipped BOOLEAN DEFAULT 0,
    answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES interview_sessions(session_id)
);

CREATE TABLE IF NOT EXISTS answer_retries (
    retry_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    question_number INTEGER NOT NULL,
    attempt_number INTEGER NOT NULL,
    answer_text TEXT NOT NULL,
    input_mode TEXT DEFAULT 'text',
    duration_seconds REAL,
    evaluation_data TEXT,
    baseline_score REAL,
    delta_score REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES interview_sessions(session_id)
);

CREATE INDEX IF NOT EXISTS idx_answer_retries_session_question_attempt
    ON answer_retries(session_id, question_number, attempt_number);

CREATE TABLE IF NOT EXISTS cached_questions (
    cache_key TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    job_title TEXT,
    session_id TEXT,
    questions_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
