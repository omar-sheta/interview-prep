"""
User database service for storing user profiles, interview history, and progress.
Uses SQLite for simplicity - can be swapped for PostgreSQL in production.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional
import hashlib


# Database path
DB_PATH = Path("./user_data/interview_app.db")


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
        
        # User preferences table (onboarding data, resume, focus areas)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id TEXT PRIMARY KEY,
                resume_text TEXT,
                resume_filename TEXT,
                target_role TEXT,
                target_company TEXT,
                focus_areas TEXT,  -- JSON array
                onboarding_complete BOOLEAN DEFAULT 0,
                mic_permission_granted BOOLEAN DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
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
        
        conn.commit()
        conn.close()
        print("✅ User database schema initialized")
    
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
    
    def complete_session(self, session_id: str, summary: dict):
        """
        Mark session as complete and save summary.
        
        Args:
            session_id: Session ID
            summary: Result from generate_interview_summary()
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Calculate answered/skipped from total and performance breakdown
        total_q = summary.get("total_questions", 0)
        performance = summary.get("performance_breakdown", {})
        answered = performance.get("excellent", 0) + performance.get("good", 0) + performance.get("needs_work", 0)
        skipped = total_q - answered if total_q > answered else 0

        cursor.execute("""
            UPDATE interview_sessions
            SET completed_at = ?,
                answered_questions = ?,
                skipped_questions = ?,
                average_score = ?,
                summary_data = ?
            WHERE session_id = ?
        """, (
            datetime.now().isoformat(),
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
    
    def save_career_analysis(self, user_id: str, job_title: str, company: str,
                            analysis_result: dict):
        """Save career analysis result for future reference."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO career_analyses
            (user_id, job_title, company, readiness_score, skill_gaps, bridge_roles, suggested_sessions, analysis_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            job_title,
            company,
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
            SELECT job_title, company, readiness_score, skill_gaps, bridge_roles,
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
                "readiness_score": row[2],
                "skill_gaps": json.loads(row[3]) if row[3] else [],
                "bridge_roles": json.loads(row[4]) if row[4] else [],
                "analysis": json.loads(row[5]) if row[5] else {},
                "created_at": row[6],
                "suggested_sessions": json.loads(row[7]) if row[7] else (json.loads(row[5]).get("suggested_sessions", []) if row[5] else [])
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
                - focus_areas: List of focus topics
                - onboarding_complete: bool
                - mic_permission_granted: bool
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        focus_areas_json = json.dumps(preferences.get("focus_areas", []))
        
        cursor.execute("""
            INSERT OR REPLACE INTO user_preferences 
            (user_id, resume_text, resume_filename, target_role, target_company, 
             focus_areas, onboarding_complete, mic_permission_granted, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            user_id,
            preferences.get("resume_text"),
            preferences.get("resume_filename"),
            preferences.get("target_role"),
            preferences.get("target_company"),
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
            SELECT resume_text, resume_filename, target_role, target_company,
                   focus_areas, onboarding_complete, mic_permission_granted, updated_at
            FROM user_preferences
            WHERE user_id = ?
        """, (user_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "resume_text": row[0],
                "resume_filename": row[1],
                "target_role": row[2],
                "target_company": row[3],
                "focus_areas": json.loads(row[4]) if row[4] else [],
                "onboarding_complete": bool(row[5]),
                "mic_permission_granted": bool(row[6]),
                "updated_at": row[7]
            }
        return None
    
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

    def get_analysis_session_questions(self, user_id: str, session_id: str) -> Optional[list]:
        """Retrieve questions for a specific session from the latest analysis plan."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
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
                            if s.get("id") == session_id and s.get("questions"):
                                return s["questions"]
        except Exception as e:
            print(f"⚠️ Failed to fetch session questions from DB: {e}")
        finally:
            conn.close()
        return None

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


# ============== Singleton ==============

_user_db: Optional[UserDatabase] = None


def get_user_db() -> UserDatabase:
    """Get or create the user database singleton."""
    global _user_db
    if _user_db is None:
        _user_db = UserDatabase()
    return _user_db
