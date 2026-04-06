"""
User database service for storing user profiles, interview history, and progress.
Uses SQLite for simplicity - can be swapped for PostgreSQL in production.
"""

import sqlite3
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
import hashlib
import secrets
import uuid

from server.config import settings


# Database path
DB_PATH = Path(settings.USER_DB_PATH).expanduser()


class UserDatabase:
    """Manages user data, interview history, and progress tracking."""
    
    def __init__(self, db_path: str = str(DB_PATH)):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
    
    def _get_connection(self):
        """Get database connection."""
        return sqlite3.connect(self.db_path)
    
    def _init_schema(self):
        """Initialize database schema."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                username TEXT NOT NULL,
                password_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                profile_data TEXT  -- JSON: job_title, target_companies, experience_level
            )
        """)
        
        # Interview sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS interview_sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                started_at TIMESTAMP NOT NULL,
                completed_at TIMESTAMP,
                job_title TEXT,
                mode TEXT,  -- 'practice' or 'coaching'
                total_questions INTEGER,
                answered_questions INTEGER,
                skipped_questions INTEGER,
                average_score REAL,
                summary_data TEXT,  -- JSON: full summary from generate_interview_summary
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Question-level answers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS interview_answers (
                answer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                question_number INTEGER NOT NULL,
                question_text TEXT NOT NULL,
                question_category TEXT,
                question_difficulty TEXT,
                user_answer TEXT NOT NULL,
                evaluation_data TEXT,  -- JSON: score, breakdown, strengths, improvements
                duration_seconds REAL,
                skipped BOOLEAN DEFAULT 0,
                answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES interview_sessions(session_id)
            )
        """)

        # Retry attempts table (report-driven iterative improvement)
        cursor.execute("""
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
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_answer_retries_session_question_attempt
            ON answer_retries(session_id, question_number, attempt_number)
        """)
        
        # User progress tracking (aggregated metrics)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_progress (
                user_id TEXT PRIMARY KEY,
                total_sessions INTEGER DEFAULT 0,
                total_questions_answered INTEGER DEFAULT 0,
                average_score REAL DEFAULT 0.0,
                skill_scores TEXT,  -- JSON: {"Python": 7.5, "System Design": 6.2, ...}
                weak_areas TEXT,  -- JSON: ["concurrency", "caching strategies", ...]
                strong_areas TEXT,  -- JSON: ["algorithms", "data structures", ...]
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Career analysis history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS career_analyses (
                analysis_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                job_title TEXT NOT NULL,
                company TEXT,
                job_description TEXT,
                readiness_score REAL,
                skill_gaps TEXT,  -- JSON array
                bridge_roles TEXT,  -- JSON array
                suggested_sessions TEXT,  -- JSON array
                analysis_data TEXT,  -- JSON: full analysis result
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Check if suggested_sessions column exists (for migration)
        cursor.execute("PRAGMA table_info(career_analyses)")
        columns = [info[1] for info in cursor.fetchall()]
        if "suggested_sessions" not in columns:
            print("📦 Migrating database: Adding suggested_sessions to career_analyses")
            cursor.execute("ALTER TABLE career_analyses ADD COLUMN suggested_sessions TEXT")
        if "job_description" not in columns:
            print("📦 Migrating database: Adding job_description to career_analyses")
            cursor.execute("ALTER TABLE career_analyses ADD COLUMN job_description TEXT")

        # Check if user_progress has action_queue column (for migration)
        cursor.execute("PRAGMA table_info(user_progress)")
        progress_columns = [info[1] for info in cursor.fetchall()]
        if "action_queue" not in progress_columns:
            print("📦 Migrating database: Adding action_queue to user_progress")
            cursor.execute("ALTER TABLE user_progress ADD COLUMN action_queue TEXT")
        
        # User preferences table (onboarding data, resume, focus areas)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id TEXT PRIMARY KEY,
                resume_text TEXT,
                resume_filename TEXT,
                target_role TEXT,
                target_company TEXT,
                job_description TEXT,
                question_count_override INTEGER,
                interviewer_persona TEXT DEFAULT 'friendly',
                piper_style TEXT DEFAULT 'interviewer',
                tts_provider TEXT DEFAULT 'piper',
                evaluation_thresholds TEXT,  -- JSON object for strictness tuning
                recording_thresholds TEXT,  -- JSON object for recording/silence tuning
                focus_areas TEXT,  -- JSON array
                onboarding_complete BOOLEAN DEFAULT 0,
                mic_permission_granted BOOLEAN DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        # Check if user_preferences has job_description column (for migration)
        cursor.execute("PRAGMA table_info(user_preferences)")
        pref_columns = [info[1] for info in cursor.fetchall()]
        if "job_description" not in pref_columns:
            print("📦 Migrating database: Adding job_description to user_preferences")
            cursor.execute("ALTER TABLE user_preferences ADD COLUMN job_description TEXT")
        if "question_count_override" not in pref_columns:
            print("📦 Migrating database: Adding question_count_override to user_preferences")
            cursor.execute("ALTER TABLE user_preferences ADD COLUMN question_count_override INTEGER")
        if "interviewer_persona" not in pref_columns:
            print("📦 Migrating database: Adding interviewer_persona to user_preferences")
            cursor.execute("ALTER TABLE user_preferences ADD COLUMN interviewer_persona TEXT DEFAULT 'friendly'")
        if "piper_style" not in pref_columns:
            print("📦 Migrating database: Adding piper_style to user_preferences")
            cursor.execute("ALTER TABLE user_preferences ADD COLUMN piper_style TEXT DEFAULT 'interviewer'")
        if "tts_provider" not in pref_columns:
            print("📦 Migrating database: Adding tts_provider to user_preferences")
            cursor.execute("ALTER TABLE user_preferences ADD COLUMN tts_provider TEXT DEFAULT 'piper'")
        if "evaluation_thresholds" not in pref_columns:
            print("📦 Migrating database: Adding evaluation_thresholds to user_preferences")
            cursor.execute("ALTER TABLE user_preferences ADD COLUMN evaluation_thresholds TEXT")
        if "recording_thresholds" not in pref_columns:
            print("📦 Migrating database: Adding recording_thresholds to user_preferences")
            cursor.execute("ALTER TABLE user_preferences ADD COLUMN recording_thresholds TEXT")
        
        # Cached questions table (persistent question cache)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cached_questions (
                cache_key TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                job_title TEXT,
                session_id TEXT,
                questions_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        # Auth session tokens table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS auth_sessions (
                session_token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_used_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        conn.commit()
        conn.close()
        print("✅ User database schema initialized")

    # ============== Auth Session Tokens ==============

    def create_session_token(self, user_id: str, ttl_days: int = 30) -> str:
        """Create and persist a new session token for a user."""
        token = secrets.token_urlsafe(48)
        now = datetime.utcnow()
        expires_at = now + timedelta(days=ttl_days)

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO auth_sessions (session_token, user_id, created_at, last_used_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
        """, (token, user_id, now.isoformat(), now.isoformat(), expires_at.isoformat()))
        conn.commit()
        conn.close()
        return token

    def validate_session_token(self, token: Optional[str]) -> Optional[str]:
        """Validate session token and return associated user_id if active."""
        if not token:
            return None

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_id, expires_at
            FROM auth_sessions
            WHERE session_token = ?
        """, (token,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            return None

        user_id, expires_at_raw = row
        try:
            expires_at = datetime.fromisoformat(expires_at_raw)
        except Exception:
            expires_at = datetime.utcnow() - timedelta(seconds=1)

        if expires_at <= datetime.utcnow():
            cursor.execute("DELETE FROM auth_sessions WHERE session_token = ?", (token,))
            conn.commit()
            conn.close()
            return None

        cursor.execute("""
            UPDATE auth_sessions
            SET last_used_at = ?
            WHERE session_token = ?
        """, (datetime.utcnow().isoformat(), token))
        conn.commit()
        conn.close()
        return user_id

    def revoke_session_token(self, token: Optional[str]) -> None:
        """Invalidate a session token."""
        if not token:
            return
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM auth_sessions WHERE session_token = ?", (token,))
        conn.commit()
        conn.close()
    
    # ============== User Management ==============
    
    def create_user(self, email: str, username: str, password: Optional[str] = None,
                    profile_data: Optional[dict] = None) -> str:
        """
        Create a new user account.
        
        Args:
            email: User email (unique identifier)
            username: Display name
            password: Optional password (will be hashed)
            profile_data: Optional dict with job_title, target_companies, etc.
            
        Returns:
            user_id
        """
        user_id = hashlib.sha256(email.encode()).hexdigest()[:16]
        password_hash = hashlib.sha256(password.encode()).hexdigest() if password else None
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO users (user_id, email, username, password_hash, profile_data)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, email, username, password_hash, json.dumps(profile_data or {})))
            
            # Initialize progress tracking
            cursor.execute("""
                INSERT INTO user_progress (user_id, skill_scores, weak_areas, strong_areas)
                VALUES (?, '{}', '[]', '[]')
            """, (user_id,))
            
            conn.commit()
            print(f"✅ Created user: {email} (ID: {user_id})")
            return user_id
            
        except sqlite3.IntegrityError:
            print(f"⚠️ User already exists: {email}")
            # Return existing user_id
            cursor.execute("SELECT user_id FROM users WHERE email = ?", (email,))
            return cursor.fetchone()[0]
        finally:
            conn.close()
    
    def get_user(self, user_id: str) -> Optional[dict]:
        """Get user profile by ID."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT user_id, email, username, created_at, last_login, profile_data, password_hash
            FROM users WHERE user_id = ?
        """, (user_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return {
            "user_id": row[0],
            "email": row[1],
            "username": row[2],
            "created_at": row[3],
            "last_login": row[4],
            "profile": json.loads(row[5]) if row[5] else {},
            "password_hash": row[6]
        }
    
    def get_user_by_email(self, email: str) -> Optional[dict]:
        """Get user by email."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT user_id FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return self.get_user(row[0])
        return None
    
    def update_last_login(self, user_id: str):
        """Update user's last login timestamp."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE user_id = ?
        """, (user_id,))
        conn.commit()
        conn.close()
    
    # ============== Interview Session Management ==============
    
    def create_session(self, user_id: str, session_id: str, job_title: str, mode: str,
                      total_questions: int, plan_node_id: Optional[str] = None) -> str:
        """
        Create a new interview session.
        
        Args:
            user_id: User ID
            session_id: Unique session ID (UUID)
            job_title: Target job title
            mode: 'practice' or 'coaching'
            total_questions: Number of questions in session
            plan_node_id: Optional reference to the plan node (e.g., "s1")
        
        Returns:
            session_id
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO interview_sessions 
            (session_id, user_id, started_at, job_title, mode, total_questions)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session_id, user_id, datetime.now().isoformat(), job_title, mode, total_questions))
        
        conn.commit()
        conn.close()
        
        print(f"📝 Created session {session_id[:8]}... for user {user_id}" + (f" (plan: {plan_node_id})" if plan_node_id else ""))
        return session_id
    
    def save_answer(self, session_id: str, question_number: int, question_text: str,
                   question_category: str, question_difficulty: str, user_answer: str,
                   evaluation: dict, duration_seconds: float, skipped: bool = False):
        """Save a single question answer and evaluation."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO interview_answers
            (session_id, question_number, question_text, question_category, 
             question_difficulty, user_answer, evaluation_data, duration_seconds, skipped)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_id, question_number, question_text, question_category,
              question_difficulty, user_answer, json.dumps(evaluation), duration_seconds, skipped))
        
        conn.commit()
        conn.close()

    def get_session_owner(self, session_id: str) -> Optional[str]:
        """Return the user_id owner of a session."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM interview_sessions WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    def get_answer_record(self, session_id: str, question_number: int) -> Optional[dict]:
        """Get the canonical answer record for a session question number."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT answer_id, question_text, question_category, question_difficulty,
                   user_answer, evaluation_data, duration_seconds, answered_at
            FROM interview_answers
            WHERE session_id = ? AND question_number = ?
            ORDER BY answer_id ASC
            LIMIT 1
        """, (session_id, question_number))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        evaluation = {}
        try:
            evaluation = json.loads(row[5]) if row[5] else {}
        except Exception:
            evaluation = {}
        return {
            "answer_id": row[0],
            "question_text": row[1] or "",
            "question_category": row[2] or "General",
            "question_difficulty": row[3] or "medium",
            "user_answer": row[4] or "",
            "evaluation": evaluation,
            "duration_seconds": row[6] or 0,
            "answered_at": row[7],
        }

    def ensure_original_retry_snapshot(self, session_id: str, question_number: int) -> Optional[dict]:
        """
        Ensure attempt_number=0 exists in answer_retries as immutable original snapshot.
        Returns snapshot payload when created/found, None when canonical answer is missing.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT retry_id, attempt_number, answer_text, input_mode, duration_seconds,
                   evaluation_data, baseline_score, delta_score, created_at
            FROM answer_retries
            WHERE session_id = ? AND question_number = ? AND attempt_number = 0
            LIMIT 1
        """, (session_id, question_number))
        existing = cursor.fetchone()
        if existing:
            conn.close()
            evaluation = {}
            try:
                evaluation = json.loads(existing[5]) if existing[5] else {}
            except Exception:
                evaluation = {}
            return {
                "retry_id": existing[0],
                "attempt_number": existing[1],
                "answer_text": existing[2],
                "input_mode": existing[3] or "original",
                "duration_seconds": existing[4] or 0,
                "evaluation": evaluation,
                "baseline_score": existing[6] or 0,
                "delta_score": existing[7] or 0,
                "created_at": existing[8],
            }

        cursor.execute("""
            SELECT user_answer, evaluation_data, duration_seconds, answered_at
            FROM interview_answers
            WHERE session_id = ? AND question_number = ?
            ORDER BY answer_id ASC
            LIMIT 1
        """, (session_id, question_number))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None

        answer_text = row[0] or ""
        try:
            evaluation = json.loads(row[1]) if row[1] else {}
        except Exception:
            evaluation = {}
        baseline = float((evaluation or {}).get("score", 0) or 0)
        created_at = row[3] or datetime.now(timezone.utc).isoformat()
        retry_id = uuid.uuid4().hex
        cursor.execute("""
            INSERT INTO answer_retries (
                retry_id, session_id, question_number, attempt_number, answer_text,
                input_mode, duration_seconds, evaluation_data, baseline_score, delta_score, created_at
            )
            VALUES (?, ?, ?, 0, ?, 'original', ?, ?, ?, 0, ?)
        """, (
            retry_id,
            session_id,
            question_number,
            answer_text,
            row[2] or 0,
            json.dumps(evaluation or {}),
            baseline,
            created_at,
        ))
        conn.commit()
        conn.close()
        return {
            "retry_id": retry_id,
            "attempt_number": 0,
            "answer_text": answer_text,
            "input_mode": "original",
            "duration_seconds": row[2] or 0,
            "evaluation": evaluation or {},
            "baseline_score": round(baseline, 2),
            "delta_score": 0,
            "created_at": created_at,
        }

    def save_retry_attempt(
        self,
        session_id: str,
        question_number: int,
        answer_text: str,
        input_mode: str,
        duration_seconds: float,
        evaluation: dict,
        baseline_score: float
    ) -> dict:
        """Persist a retry attempt and return normalized attempt payload."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COALESCE(MAX(attempt_number), 0)
            FROM answer_retries
            WHERE session_id = ? AND question_number = ?
        """, (session_id, question_number))
        row = cursor.fetchone()
        attempt_number = (row[0] or 0) + 1

        score = float((evaluation or {}).get("score", 0) or 0)
        baseline = float(baseline_score or 0)
        delta = round(score - baseline, 2)
        retry_id = uuid.uuid4().hex
        created_at = datetime.now(timezone.utc).isoformat()

        cursor.execute("""
            INSERT INTO answer_retries (
                retry_id, session_id, question_number, attempt_number, answer_text,
                input_mode, duration_seconds, evaluation_data, baseline_score, delta_score, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            retry_id,
            session_id,
            question_number,
            attempt_number,
            answer_text,
            input_mode or "text",
            duration_seconds,
            json.dumps(evaluation or {}),
            baseline,
            delta,
            created_at,
        ))
        conn.commit()
        conn.close()

        return {
            "retry_id": retry_id,
            "session_id": session_id,
            "question_number": question_number,
            "attempt_number": attempt_number,
            "answer_text": answer_text,
            "input_mode": input_mode or "text",
            "duration_seconds": duration_seconds,
            "evaluation": evaluation or {},
            "baseline_score": round(baseline, 2),
            "delta_score": delta,
            "created_at": created_at,
        }

    def get_retry_attempts(self, session_id: str, question_number: int) -> list:
        """Return all retry attempts ordered oldest -> newest for a question."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT retry_id, attempt_number, answer_text, input_mode, duration_seconds,
                   evaluation_data, baseline_score, delta_score, created_at
            FROM answer_retries
            WHERE session_id = ? AND question_number = ?
            ORDER BY attempt_number ASC
        """, (session_id, question_number))
        rows = cursor.fetchall()
        conn.close()

        attempts = []
        for row in rows:
            try:
                evaluation = json.loads(row[5]) if row[5] else {}
            except Exception:
                evaluation = {}
            attempts.append({
                "retry_id": row[0],
                "attempt_number": row[1],
                "answer_text": row[2],
                "input_mode": row[3] or "text",
                "duration_seconds": row[4] or 0,
                "evaluation": evaluation,
                "baseline_score": row[6] or 0,
                "delta_score": row[7] or 0,
                "created_at": row[8],
            })

        return attempts

    def get_latest_retry_delta(self, session_id: str, question_number: int) -> Optional[float]:
        """Return delta score for latest retry attempt if any."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT delta_score
            FROM answer_retries
            WHERE session_id = ? AND question_number = ?
            ORDER BY attempt_number DESC
            LIMIT 1
        """, (session_id, question_number))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        try:
            return float(row[0])
        except Exception:
            return None

    def promote_retry_if_higher(self, session_id: str, question_number: int, attempt: dict) -> dict:
        """
        Promote retry evaluation into canonical interview_answers row only when score is higher.
        Returns promotion metadata including updated session average.
        """
        attempt_eval = (attempt or {}).get("evaluation") or {}
        new_score = float((attempt_eval or {}).get("score", 0) or 0)
        result = {
            "promoted": False,
            "previous_score": 0.0,
            "primary_score": new_score,
            "session_average_score": None,
        }

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT answer_id, evaluation_data
            FROM interview_answers
            WHERE session_id = ? AND question_number = ?
            ORDER BY answer_id ASC
            LIMIT 1
        """, (session_id, question_number))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return result

        answer_id = row[0]
        current_eval = {}
        try:
            current_eval = json.loads(row[1]) if row[1] else {}
        except Exception:
            current_eval = {}
        current_score = float((current_eval or {}).get("score", 0) or 0)
        result["previous_score"] = round(current_score, 2)
        result["primary_score"] = round(current_score, 2)

        if new_score <= current_score:
            conn.close()
            return result

        cursor.execute("""
            UPDATE interview_answers
            SET user_answer = ?,
                evaluation_data = ?,
                duration_seconds = ?,
                skipped = 0,
                answered_at = CURRENT_TIMESTAMP
            WHERE answer_id = ?
        """, (
            str((attempt or {}).get("answer_text") or ""),
            json.dumps(attempt_eval or {}),
            float((attempt or {}).get("duration_seconds") or 0),
            answer_id,
        ))

        cursor.execute("""
            SELECT AVG(CASE
                        WHEN json_extract(evaluation_data, '$.score') IS NULL THEN 0
                        ELSE json_extract(evaluation_data, '$.score')
                       END),
                   SUM(CASE WHEN skipped = 0 THEN 1 ELSE 0 END)
            FROM interview_answers
            WHERE session_id = ?
        """, (session_id,))
        agg_row = cursor.fetchone() or (None, None)
        session_avg = float(agg_row[0] or 0)
        answered_count = int(agg_row[1] or 0)

        cursor.execute("""
            SELECT user_id, summary_data
            FROM interview_sessions
            WHERE session_id = ?
            LIMIT 1
        """, (session_id,))
        sess_row = cursor.fetchone()
        user_id = sess_row[0] if sess_row else None
        summary_json = {}
        try:
            summary_json = json.loads(sess_row[1]) if sess_row and sess_row[1] else {}
        except Exception:
            summary_json = {}
        if isinstance(summary_json, dict):
            summary_json["average_score"] = round(session_avg, 1)
            summary_json["answered_questions"] = answered_count

        cursor.execute("""
            UPDATE interview_sessions
            SET average_score = ?,
                answered_questions = ?,
                summary_data = ?
            WHERE session_id = ?
        """, (
            round(session_avg, 1),
            answered_count,
            json.dumps(summary_json) if isinstance(summary_json, dict) else None,
            session_id,
        ))
        conn.commit()
        conn.close()

        if user_id:
            self._update_user_progress(user_id)

        result.update({
            "promoted": True,
            "primary_score": round(new_score, 2),
            "session_average_score": round(session_avg, 1),
        })
        return result

    def update_session_total_questions(self, session_id: str, total_questions: int) -> None:
        """Update total question count for an in-progress/completed session."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE interview_sessions
            SET total_questions = ?
            WHERE session_id = ?
        """, (max(0, int(total_questions or 0)), session_id))
        conn.commit()
        conn.close()
    
    def complete_session(self, session_id: str, summary: dict):
        """
        Mark session as complete and save summary.
        
        Args:
            session_id: Session ID
            summary: Result from generate_interview_summary()
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Prefer explicit counts from summary (skip-aware); fallback to score buckets.
        total_q = max(0, int(summary.get("total_questions", 0) or 0))
        answered_raw = summary.get("answered_questions")
        skipped_raw = summary.get("skipped_questions")

        if answered_raw is None and skipped_raw is None:
            performance = summary.get("performance_breakdown", {}) or {}
            answered = int(performance.get("excellent", 0) or 0) + int(performance.get("good", 0) or 0) + int(performance.get("needs_work", 0) or 0)
            skipped = max(0, total_q - answered)
        else:
            answered = max(0, int(answered_raw or 0))
            skipped = max(0, int(skipped_raw or 0)) if skipped_raw is not None else max(0, total_q - answered)

            # Normalize inconsistent totals defensively.
            if answered > total_q:
                answered = total_q
            if answered + skipped > total_q:
                skipped = max(0, total_q - answered)
            elif answered + skipped < total_q:
                skipped = max(0, total_q - answered)

        cursor.execute("""
            UPDATE interview_sessions
            SET completed_at = ?,
                total_questions = ?,
                answered_questions = ?,
                skipped_questions = ?,
                average_score = ?,
                summary_data = ?
            WHERE session_id = ?
        """, (
            datetime.now().isoformat(),
            total_q,
            answered,
            skipped,
            summary.get("average_score", 0.0),
            json.dumps(summary),
            session_id
        ))
        
        conn.commit()
        
        # Get user_id for this session
        cursor.execute("SELECT user_id FROM interview_sessions WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            user_id = row[0]
            self._update_user_progress(user_id)
        
        print(f"✅ Completed session {session_id}")
    
    def _update_user_progress(self, user_id: str):
        """Recalculate and update user's aggregate progress metrics."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Get all completed sessions for this user
        cursor.execute("""
            SELECT average_score, answered_questions, summary_data
            FROM interview_sessions
            WHERE user_id = ? AND completed_at IS NOT NULL
        """, (user_id,))
        
        sessions = cursor.fetchall()
        
        if not sessions:
            conn.close()
            return
        
        total_sessions = len(sessions)
        total_questions = sum(s[1] or 0 for s in sessions)
        scores = [s[0] for s in sessions if s[0] is not None]
        avg_score = sum(scores) / len(scores) if scores else 0.0
        
        # Aggregate skill scores by category
        skill_scores = {}
        all_weak_areas = []
        all_strong_areas = []
        
        for session in sessions:
            if session[2]:  # summary_data exists
                try:
                    summary = json.loads(session[2])
                    all_weak_areas.extend(summary.get("areas_to_improve", []))
                    all_strong_areas.extend(summary.get("strengths", []))
                except json.JSONDecodeError:
                    pass
        
        # Get category-level scores
        cursor.execute("""
            SELECT ia.question_category, AVG(json_extract(ia.evaluation_data, '$.score'))
            FROM interview_answers ia
            JOIN interview_sessions isess ON ia.session_id = isess.session_id
            WHERE isess.user_id = ? AND ia.skipped = 0
            GROUP BY ia.question_category
            """, (user_id,))
        
        for row in cursor.fetchall():
            if row[0] and row[1]:
                skill_scores[row[0]] = round(row[1], 1)
        
        # Update progress
        cursor.execute("""
            UPDATE user_progress
            SET total_sessions = ?,
                total_questions_answered = ?,
                average_score = ?,
                skill_scores = ?,
                weak_areas = ?,
                strong_areas = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (
            total_sessions,
            total_questions,
            round(avg_score, 1),
            json.dumps(skill_scores),
            json.dumps(list(set(all_weak_areas))[:10]),  # Top 10 unique weak areas
            json.dumps(list(set(all_strong_areas))[:10]),  # Top 10 unique strengths
            user_id
        ))
        
        conn.commit()
        conn.close()
        
        print(f"📊 Updated progress for user {user_id}")
    
    # ============== Query Methods ==============
    
    def get_user_progress(self, user_id: str) -> dict:
        """Get aggregated progress metrics for a user."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT total_sessions, total_questions_answered, average_score,
                   skill_scores, weak_areas, strong_areas, last_updated
            FROM user_progress WHERE user_id = ?
        """, (user_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return {}
        
        return {
            "total_sessions": row[0],
            "total_questions_answered": row[1],
            "average_score": row[2],
            "skill_scores": json.loads(row[3]) if row[3] else {},
            "weak_areas": json.loads(row[4]) if row[4] else [],
            "strong_areas": json.loads(row[5]) if row[5] else [],
            "last_updated": row[6]
        }
    
    def get_session_history(self, user_id: str, limit: int = 10) -> list:
        """Get recent interview sessions for a user."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT session_id, started_at, completed_at, job_title, mode,
                   total_questions, answered_questions, average_score, summary_data
            FROM interview_sessions
            WHERE user_id = ?
            ORDER BY started_at DESC
            LIMIT ?
        """, (user_id, limit))
        
        sessions = []
        for row in cursor.fetchall():
            sessions.append({
                "session_id": row[0],
                "started_at": row[1],
                "completed_at": row[2],
                "job_title": row[3],
                "mode": row[4],
                "total_questions": row[5],
                "answered_questions": row[6],
                "average_score": row[7],
                "summary": json.loads(row[8]) if row[8] else None
            })
        
        conn.close()
        return sessions
    
    def get_session_details(self, session_id: str) -> Optional[dict]:
        """Get full details of a specific session including all answers."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Get session info
        cursor.execute("""
            SELECT session_id, user_id, started_at, completed_at, job_title, mode,
                   total_questions, answered_questions, average_score, summary_data
            FROM interview_sessions WHERE session_id = ?
        """, (session_id,))
        
        session_row = cursor.fetchone()
        if not session_row:
            conn.close()
            return None
        
        # Get all answers
        cursor.execute("""
            SELECT question_number, question_text, question_category, question_difficulty,
                   user_answer, evaluation_data, duration_seconds, skipped, answered_at
            FROM interview_answers
            WHERE session_id = ?
            ORDER BY question_number
        """, (session_id,))
        
        answers = []
        for row in cursor.fetchall():
            answers.append({
                "question_number": row[0],
                "question_text": row[1],
                "category": row[2],
                "difficulty": row[3],
                "user_answer": row[4],
                "evaluation": json.loads(row[5]) if row[5] else None,
                "duration_seconds": row[6],
                "skipped": bool(row[7]),
                "answered_at": row[8]
            })
        
        conn.close()
        
        return {
            "session_id": session_row[0],
            "user_id": session_row[1],
            "started_at": session_row[2],
            "completed_at": session_row[3],
            "job_title": session_row[4],
            "mode": session_row[5],
            "total_questions": session_row[6],
            "answered_questions": session_row[7],
            "average_score": session_row[8],
            "summary": json.loads(session_row[9]) if session_row[9] else None,
            "answers": answers
        }
    
    # ============== Career Analysis ==============
    
    def save_career_analysis(
        self,
        user_id: str,
        job_title: str,
        company: str,
        analysis_result: dict,
        job_description: str = ""
    ):
        """Save career analysis result for future reference."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO career_analyses
            (user_id, job_title, company, job_description, readiness_score, skill_gaps, bridge_roles, suggested_sessions, analysis_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            job_title,
            company,
            job_description,
            analysis_result.get("readiness_score", 0.0),
            json.dumps(analysis_result.get("skill_gaps", [])),
            json.dumps(analysis_result.get("bridge_roles", [])),
            json.dumps(analysis_result.get("suggested_sessions", [])),
            json.dumps(analysis_result)
        ))
        
        conn.commit()
        conn.close()
        
        print(f"💼 Saved career analysis for {user_id}: {job_title} at {company}")
    
    def get_career_analyses(self, user_id: str, limit: int = 5) -> list:
        """Get recent career analyses for a user."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT job_title, company, job_description, readiness_score, skill_gaps, bridge_roles,
                   analysis_data, created_at, suggested_sessions
            FROM career_analyses
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (user_id, limit))
        
        analyses = []
        for row in cursor.fetchall():
            analyses.append({
                "job_title": row[0],
                "company": row[1],
                "job_description": row[2],
                "readiness_score": row[3],
                "skill_gaps": json.loads(row[4]) if row[4] else [],
                "bridge_roles": json.loads(row[5]) if row[5] else [],
                "analysis": json.loads(row[6]) if row[6] else {},
                "created_at": row[7],
                "suggested_sessions": json.loads(row[8]) if row[8] else (json.loads(row[6]).get("suggested_sessions", []) if row[6] else [])
            })
        
        conn.close()
        return analyses

    # ============== User Preferences ==============
    
    def save_user_preferences(self, user_id: str, preferences: dict) -> None:
        """
        Save or update user preferences (onboarding data, resume, focus areas).
        
        Args:
            user_id: User ID
            preferences: Dict with keys:
                - resume_text: Extracted resume text
                - resume_filename: Original filename
                - target_role: Target job role
                - target_company: Target company
                - job_description: Job description text
                - question_count_override: Optional per-session question count override
                - interviewer_persona: Interviewer behavior style
                - piper_style: Question/response voice style preset (interviewer|balanced|fast)
                - tts_provider: Question voice engine (piper|qwen3_tts)
                - focus_areas: List of focus topics
                - onboarding_complete: bool
                - mic_permission_granted: bool
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        focus_areas_json = json.dumps(preferences.get("focus_areas", []))
        question_count_override = preferences.get("question_count_override")
        if question_count_override in ("", None):
            question_count_override = None
        else:
            try:
                question_count_override = int(question_count_override)
            except Exception:
                question_count_override = None
        interviewer_persona = str(preferences.get("interviewer_persona") or "friendly").strip().lower()
        if interviewer_persona not in {"friendly", "strict"}:
            interviewer_persona = "friendly"
        piper_style = str(preferences.get("piper_style") or "interviewer").strip().lower()
        if piper_style not in {"interviewer", "balanced", "fast"}:
            piper_style = "interviewer"
        tts_provider = str(preferences.get("tts_provider") or "piper").strip().lower()
        if tts_provider == "qwen3_tts_mlx":
            tts_provider = "qwen3_tts"
        if tts_provider not in ["piper", "neutts", "kokoro", "qwen3_tts"]:
            tts_provider = "piper"
        
        cursor.execute("""
            INSERT OR REPLACE INTO user_preferences 
            (user_id, resume_text, resume_filename, target_role, target_company, job_description, question_count_override, interviewer_persona, piper_style, tts_provider, evaluation_thresholds, recording_thresholds,
             focus_areas, onboarding_complete, mic_permission_granted, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            user_id,
            preferences.get("resume_text"),
            preferences.get("resume_filename"),
            preferences.get("target_role"),
            preferences.get("target_company"),
            preferences.get("job_description"),
            question_count_override,
            interviewer_persona,
            piper_style,
            tts_provider,
            json.dumps(preferences.get("evaluation_thresholds")) if isinstance(preferences.get("evaluation_thresholds"), dict) else None,
            json.dumps(preferences.get("recording_thresholds")) if isinstance(preferences.get("recording_thresholds"), dict) else None,
            focus_areas_json,
            preferences.get("onboarding_complete", False),
            preferences.get("mic_permission_granted", False)
        ))
        
        conn.commit()
        conn.close()
        print(f"✅ Saved preferences for user {user_id}")
    
    def get_user_preferences(self, user_id: str) -> Optional[dict]:
        """Get user preferences by user ID."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT resume_text, resume_filename, target_role, target_company, job_description, question_count_override, interviewer_persona,
                   piper_style, tts_provider, evaluation_thresholds, recording_thresholds,
                   focus_areas, onboarding_complete, mic_permission_granted, updated_at
            FROM user_preferences
            WHERE user_id = ?
        """, (user_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            thresholds = {}
            recording_thresholds = {}
            try:
                thresholds = json.loads(row[9]) if row[9] else {}
            except Exception:
                thresholds = {}
            try:
                recording_thresholds = json.loads(row[10]) if row[10] else {}
            except Exception:
                recording_thresholds = {}
            return {
                "resume_text": row[0],
                "resume_filename": row[1],
                "target_role": row[2],
                "target_company": row[3],
                "job_description": row[4],
                "question_count_override": int(row[5]) if row[5] is not None else None,
                "interviewer_persona": str(row[6] or "friendly").strip().lower() or "friendly",
                "piper_style": str(row[7] or "interviewer").strip().lower() or "interviewer",
                "tts_provider": (
                    "qwen3_tts"
                    if str(row[8] or "piper").strip().lower() == "qwen3_tts_mlx"
                    else (str(row[8] or "piper").strip().lower() or "piper")
                ),
                "evaluation_thresholds": thresholds if isinstance(thresholds, dict) else {},
                "recording_thresholds": recording_thresholds if isinstance(recording_thresholds, dict) else {},
                "focus_areas": json.loads(row[11]) if row[11] else [],
                "onboarding_complete": bool(row[12]),
                "mic_permission_granted": bool(row[13]),
                "updated_at": row[14]
            }
        return None

    def reset_analysis_workspace(self, user_id: str) -> None:
        """
        Reset analysis workspace data while preserving account + interview history.
        Removes analysis artifacts, cached drills/questions, and resume/JD preference text.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Remove analysis snapshots and cached generated data
        cursor.execute("DELETE FROM career_analyses WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM cached_questions WHERE user_id = ?", (user_id,))

        # Clear action/drill queue and active plan if those columns exist
        cursor.execute("PRAGMA table_info(user_progress)")
        cols = [c[1] for c in cursor.fetchall()]
        if "active_plan" in cols and "action_queue" in cols:
            cursor.execute("""
                UPDATE user_progress
                SET active_plan = NULL,
                    action_queue = '[]',
                    last_updated = CURRENT_TIMESTAMP
                WHERE user_id = ?
            """, (user_id,))
        elif "active_plan" in cols:
            cursor.execute("""
                UPDATE user_progress
                SET active_plan = NULL,
                    last_updated = CURRENT_TIMESTAMP
                WHERE user_id = ?
            """, (user_id,))
        elif "action_queue" in cols:
            cursor.execute("""
                UPDATE user_progress
                SET action_queue = '[]',
                    last_updated = CURRENT_TIMESTAMP
                WHERE user_id = ?
            """, (user_id,))

        # Clear uploaded resume/JD text but keep target role/company as convenience
        cursor.execute("""
            UPDATE user_preferences
            SET resume_text = NULL,
                resume_filename = NULL,
                job_description = NULL,
                focus_areas = '[]',
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (user_id,))

        conn.commit()
        conn.close()

    def clear_user_configuration(self, user_id: str) -> None:
        """
        Clear saved onboarding/configuration values while preserving interview history and settings thresholds.
        Also clears analysis artifacts because they are configuration-dependent.
        """
        # Reuse workspace cleanup for analysis snapshots/caches/action queue + resume/JD text.
        self.reset_analysis_workspace(user_id)

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE user_preferences
            SET target_role = NULL,
                target_company = NULL,
                question_count_override = NULL,
                interviewer_persona = 'friendly',
                piper_style = 'interviewer',
                tts_provider = 'piper',
                focus_areas = '[]',
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (user_id,))
        conn.commit()
        conn.close()

    def _reset_user_progress_aggregates(self, cursor, user_id: str) -> None:
        """Reset aggregate progress metrics while preserving additional columns like action_queue/active_plan."""
        cursor.execute("""
            INSERT INTO user_progress (
                user_id, total_sessions, total_questions_answered, average_score,
                skill_scores, weak_areas, strong_areas, last_updated
            )
            VALUES (?, 0, 0, 0.0, '{}', '[]', '[]', CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                total_sessions = 0,
                total_questions_answered = 0,
                average_score = 0.0,
                skill_scores = '{}',
                weak_areas = '[]',
                strong_areas = '[]',
                last_updated = CURRENT_TIMESTAMP
        """, (user_id,))

    def delete_interview_session(self, user_id: str, session_id: str) -> bool:
        """Delete one interview session and related answers/retries for the owning user."""
        clean_session_id = str(session_id or "").strip()
        if not clean_session_id:
            return False

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT completed_at
            FROM interview_sessions
            WHERE session_id = ? AND user_id = ?
            LIMIT 1
        """, (clean_session_id, user_id))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False

        cursor.execute("DELETE FROM answer_retries WHERE session_id = ?", (clean_session_id,))
        cursor.execute("DELETE FROM interview_answers WHERE session_id = ?", (clean_session_id,))
        cursor.execute("DELETE FROM interview_sessions WHERE session_id = ? AND user_id = ?", (clean_session_id, user_id))

        cursor.execute("""
            SELECT COUNT(*)
            FROM interview_sessions
            WHERE user_id = ? AND completed_at IS NOT NULL
        """, (user_id,))
        remaining_completed = int((cursor.fetchone() or [0])[0] or 0)

        if remaining_completed == 0:
            self._reset_user_progress_aggregates(cursor, user_id)

        conn.commit()
        conn.close()

        if remaining_completed > 0:
            self._update_user_progress(user_id)

        return True

    def delete_interview_history(self, user_id: str) -> None:
        """Delete all interview sessions and answer history for a user."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT session_id FROM interview_sessions WHERE user_id = ?", (user_id,))
        session_ids = [row[0] for row in cursor.fetchall() if row and row[0]]
        if session_ids:
            placeholders = ",".join(["?"] * len(session_ids))
            cursor.execute(
                f"DELETE FROM answer_retries WHERE session_id IN ({placeholders})",
                session_ids
            )
            cursor.execute(
                f"DELETE FROM interview_answers WHERE session_id IN ({placeholders})",
                session_ids
            )

        cursor.execute("DELETE FROM interview_sessions WHERE user_id = ?", (user_id,))

        # Reset aggregate progress stats but preserve action queue / active plan fields.
        self._reset_user_progress_aggregates(cursor, user_id)

        conn.commit()
        conn.close()

    def reset_all_user_data(self, user_id: str) -> None:
        """
        Full destructive reset for a user workspace:
        - interview history
        - analysis artifacts
        - saved configuration/onboarding fields
        """
        self.delete_interview_history(user_id)
        self.clear_user_configuration(user_id)
    
    def get_interview_history(self, user_id: str, limit: int = 20) -> list:
        """
        Get interview session history with summary stats for dashboard display.
        
        Returns list of sessions with:
        - session_id, job_title, mode, started_at, completed_at
        - total_questions, answered_questions, average_score
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT session_id, job_title, mode, started_at, completed_at,
                   total_questions, answered_questions, skipped_questions, average_score
            FROM interview_sessions
            WHERE user_id = ?
            ORDER BY started_at DESC
            LIMIT ?
        """, (user_id, limit))
        
        history = []
        for row in cursor.fetchall():
            history.append({
                "session_id": row[0],
                "job_title": row[1],
                "mode": row[2],
                "started_at": row[3],
                "completed_at": row[4],
                "total_questions": row[5],
                "answered_questions": row[6],
                "skipped_questions": row[7],
                "average_score": row[8]
            })
        
        conn.close()
        return history
    
    def get_user_stats(self, user_id: str) -> dict:
        """Get aggregate stats for user dashboard."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Get total sessions and questions
        cursor.execute("""
            SELECT COUNT(*), SUM(answered_questions), AVG(average_score)
            FROM interview_sessions
            WHERE user_id = ? AND completed_at IS NOT NULL
        """, (user_id,))
        
        row = cursor.fetchone()
        total_sessions = row[0] or 0
        total_questions = row[1] or 0
        avg_score = row[2] or 0
        
        # Get best and worst categories
        cursor.execute("""
            SELECT question_category, AVG(
                CAST(json_extract(evaluation_data, '$.score') AS REAL)
            ) as avg_score
            FROM interview_answers
            WHERE session_id IN (SELECT session_id FROM interview_sessions WHERE user_id = ?)
            GROUP BY question_category
            ORDER BY avg_score DESC
        """, (user_id,))
        
        category_scores = {}
        for row in cursor.fetchall():
            if row[0] and row[1]:
                category_scores[row[0]] = round(row[1], 1)
        
        conn.close()
        
        return {
            "total_sessions": total_sessions,
            "total_questions": total_questions,
            "average_score": round(avg_score, 1) if avg_score else 0,
            "category_scores": category_scores
        }

    # ============== Persistent Action Queue ==============

    def get_action_queue(self, user_id: str) -> list:
        """Get persisted dashboard action queue for a user."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT action_queue FROM user_progress WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if not row or not row[0]:
                return []
            data = json.loads(row[0])
            return data if isinstance(data, list) else []
        except Exception:
            return []
        finally:
            conn.close()

    def save_action_queue(self, user_id: str, actions: list) -> None:
        """Persist dashboard action queue for a user."""
        safe_actions = actions if isinstance(actions, list) else []
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO user_progress (user_id, action_queue, last_updated)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                action_queue = excluded.action_queue,
                last_updated = CURRENT_TIMESTAMP
        """, (user_id, json.dumps(safe_actions)))
        conn.commit()
        conn.close()

    def append_report_actions(self, user_id: str, summary: dict, session_id: Optional[str] = None) -> list:
        """
        Generate and persist actionable drills from interview summary feedback.
        Returns the updated action queue.
        """
        summary = summary or {}
        now_iso = datetime.utcnow().isoformat()
        existing = self.get_action_queue(user_id)
        pending = [a for a in existing if isinstance(a, dict)]
        existing_titles = {str(a.get("title", "")).strip().lower() for a in pending}

        raw_items = []
        raw_items.extend(summary.get("action_items", []) or [])
        for area in (summary.get("areas_to_improve", []) or [])[:3]:
            raw_items.append(f"Improve: {area}")

        new_actions = []
        for idx, item in enumerate(raw_items):
            text = str(item).strip()
            if not text:
                continue
            normalized = text.lower()
            if normalized in existing_titles:
                continue
            existing_titles.add(normalized)

            focus_topic = text.replace("Improve:", "").strip() if text.lower().startswith("improve:") else text
            new_actions.append({
                "id": f"act_{uuid.uuid4().hex[:10]}",
                "title": text,
                "description": "Targeted drill generated from your latest interview report.",
                "type": "drill",
                "focus_topic": focus_topic,
                "duration_minutes": 12 if idx == 0 else 10,
                "priority": "high" if idx == 0 else "medium",
                "status": "pending",
                "source": "report",
                "source_session_id": session_id,
                "created_at": now_iso,
            })

        merged = (new_actions + pending)[:30]
        self.save_action_queue(user_id, merged)
        return merged

    # ============== Active Interview Plan ==============
    
    def save_active_plan(self, user_id: str, plan: dict) -> None:
        """Save the current Interview Loop structure for a user."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Ensure column exists
        cursor.execute("PRAGMA table_info(user_progress)")
        cols = [c[1] for c in cursor.fetchall()]
        if "active_plan" not in cols:
            cursor.execute("ALTER TABLE user_progress ADD COLUMN active_plan TEXT")
        
        cursor.execute("""
            UPDATE user_progress 
            SET active_plan = ?, last_updated = CURRENT_TIMESTAMP 
            WHERE user_id = ?
        """, (json.dumps(plan), user_id))
        
        # If no row exists, insert
        if cursor.rowcount == 0:
            cursor.execute("""
                INSERT INTO user_progress (user_id, active_plan, last_updated)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """, (user_id, json.dumps(plan)))
        
        conn.commit()
        conn.close()
        print(f"💾 Saved active plan for {user_id}")

    def update_latest_analysis_plan(self, user_id: str, practice_plan: dict) -> None:
        """Update the practice_plan (analysis_data) of the most recent analysis."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Get latest analysis ID
            cursor.execute("""
                SELECT analysis_id, analysis_data 
                FROM career_analyses 
                WHERE user_id = ? 
                ORDER BY created_at DESC LIMIT 1
            """, (user_id,))
            row = cursor.fetchone()
            
            if row:
                analysis_id = row[0]
                current_data = json.loads(row[1]) if row[1] else {}
                
                # Update plan
                current_data["practice_plan"] = practice_plan
                
                cursor.execute("""
                    UPDATE career_analyses
                    SET analysis_data = ?
                    WHERE analysis_id = ?
                """, (json.dumps(current_data), analysis_id))
                conn.commit()
                print(f"💾 Updated plan questions for analysis {analysis_id}")
        except Exception as e:
            print(f"❌ Failed to update analysis plan: {e}")
        finally:
            conn.close()

    def get_active_plan(self, user_id: str) -> Optional[dict]:
        """Retrieve the active Interview Loop for a user."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT active_plan FROM user_progress WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row and row[0]:
                return json.loads(row[0])
        except Exception:
            pass
        finally:
            conn.close()
        return None

    def get_analysis_session_questions(
        self,
        user_id: str,
        session_id: str,
        interviewer_persona: str = "friendly"
    ) -> Optional[list]:
        """Retrieve persona-aware questions for a session from the latest analysis plan."""
        conn = self._get_connection()
        cursor = conn.cursor()
        persona = str(interviewer_persona or "friendly").strip().lower()
        if persona not in {"friendly", "strict"}:
            persona = "friendly"

        try:
            # Get latest analysis
            cursor.execute("""
                SELECT analysis_data
                FROM career_analyses
                WHERE user_id = ? 
                ORDER BY created_at DESC LIMIT 1
            """, (user_id,))
            row = cursor.fetchone()
            
            if row and row[0]:
                data = json.loads(row[0])
                practice_plan = data.get("practice_plan", {})
                
                if practice_plan and "rounds" in practice_plan:
                    for round_ in practice_plan["rounds"]:
                        for s in round_.get("sessions", []):
                            if s.get("id") != session_id:
                                continue

                            # New schema: persona-keyed question bank.
                            by_persona = s.get("questions_by_persona", {})
                            if isinstance(by_persona, dict):
                                persona_questions = by_persona.get(persona)
                                if isinstance(persona_questions, list) and persona_questions:
                                    return persona_questions
                                # Allow fallback only for friendly.
                                if persona == "friendly":
                                    friendly_questions = by_persona.get("friendly")
                                    if isinstance(friendly_questions, list) and friendly_questions:
                                        return friendly_questions

                            # Legacy schema (single list) should only serve friendly persona.
                            if persona == "friendly" and s.get("questions"):
                                return s["questions"]
        except Exception as e:
            print(f"⚠️ Failed to fetch session questions from DB: {e}")
        finally:
            conn.close()
        return None

    def set_latest_analysis_session_questions(
        self,
        user_id: str,
        session_id: str,
        questions: list,
        interviewer_persona: str = "friendly"
    ) -> None:
        """Persist persona-specific questions for a session on the latest analysis plan."""
        if not isinstance(questions, list) or not questions:
            return

        persona = str(interviewer_persona or "friendly").strip().lower()
        if persona not in {"friendly", "strict"}:
            persona = "friendly"

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT analysis_id, analysis_data
                FROM career_analyses
                WHERE user_id = ?
                ORDER BY created_at DESC LIMIT 1
            """, (user_id,))
            row = cursor.fetchone()
            if not row:
                return

            analysis_id = row[0]
            data = json.loads(row[1]) if row[1] else {}
            practice_plan = data.get("practice_plan")
            if not isinstance(practice_plan, dict):
                return

            updated = False
            rounds = practice_plan.get("rounds")
            if isinstance(rounds, list):
                for round_obj in rounds:
                    if not isinstance(round_obj, dict):
                        continue
                    sessions = round_obj.get("sessions")
                    if not isinstance(sessions, list):
                        continue
                    for sess in sessions:
                        if not isinstance(sess, dict):
                            continue
                        if sess.get("id") != session_id:
                            continue
                        by_persona = sess.get("questions_by_persona")
                        if not isinstance(by_persona, dict):
                            by_persona = {}
                        by_persona[persona] = questions
                        sess["questions_by_persona"] = by_persona
                        if persona == "friendly":
                            sess["questions"] = questions
                        updated = True
                        break
                    if updated:
                        break

            if not updated:
                return

            data["practice_plan"] = practice_plan
            cursor.execute("""
                UPDATE career_analyses
                SET analysis_data = ?
                WHERE analysis_id = ?
            """, (json.dumps(data), analysis_id))
            conn.commit()
        except Exception as e:
            print(f"⚠️ Failed to persist persona session questions: {e}")
        finally:
            conn.close()

    # ============== Cached Questions ==============
    
    def save_cached_questions(self, cache_key: str, user_id: str, job_title: str, 
                              session_id: str, questions: list) -> None:
        """
        Save generated questions to database cache.
        
        Args:
            cache_key: Unique cache key (e.g., user_id_job_title_session_id)
            user_id: User ID
            job_title: Target job title
            session_id: Session ID (e.g., "s1", "s2")
            questions: List of question dicts
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO cached_questions 
                (cache_key, user_id, job_title, session_id, questions_json, created_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (cache_key, user_id, job_title, session_id, json.dumps(questions)))
            
            conn.commit()
            print(f"💾 DB: Cached {len(questions)} questions for {cache_key}")
        except Exception as e:
            print(f"❌ DB cache save failed: {e}")
        finally:
            conn.close()
    
    def get_cached_questions(self, cache_key: str) -> Optional[list]:
        """
        Retrieve cached questions from database.
        
        Args:
            cache_key: Unique cache key
            
        Returns:
            List of question dicts or None if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT questions_json FROM cached_questions WHERE cache_key = ?
            """, (cache_key,))
            
            row = cursor.fetchone()
            if row and row[0]:
                questions = json.loads(row[0])
                print(f"✅ DB: Cache hit for {cache_key}")
                return questions
            else:
                print(f"❌ DB: Cache miss for {cache_key}")
                return None
        except Exception as e:
            print(f"⚠️ DB cache get failed: {e}")
            return None
        finally:
            conn.close()
    
    def delete_cached_questions(self, cache_key: str) -> None:
        """Delete cached questions by key."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("DELETE FROM cached_questions WHERE cache_key = ?", (cache_key,))
            conn.commit()
        except Exception as e:
            print(f"⚠️ DB cache delete failed: {e}")
        finally:
            conn.close()

    def delete_cached_questions_for_user(self, user_id: str) -> None:
        """Delete all cached questions for a user."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM cached_questions WHERE user_id = ?", (user_id,))
            conn.commit()
            print(f"🧹 DB: Cleared cached questions for {user_id}")
        except Exception as e:
            print(f"⚠️ DB user cache clear failed: {e}")
        finally:
            conn.close()


# ============== Singleton ==============

_user_db: Optional[UserDatabase] = None


def get_user_db() -> UserDatabase:
    """Get or create the user database singleton."""
    global _user_db
    if _user_db is None:
        _user_db = UserDatabase()
    return _user_db
