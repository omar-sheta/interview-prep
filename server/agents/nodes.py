"""
Agent Nodes for Career Analysis LangGraph.
Contains skill mapping, mindmap generation, and analysis nodes.
"""

import asyncio
import json
import re
from datetime import datetime
from typing import Any, Callable, Optional, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage

from server.agents.state import InterviewState
from server.services.llm_factory import get_chat_model
# CHANGED: Updated imports to match the new resume_tool function names
from server.tools.resume_tool import get_all_skills, parse_resume_node, extract_text_from_pdf_bytes
from server.tools.job_tool import get_bridge_role_suggestions, estimate_role_level


# ============== Career Analysis State ==============

class CareerAnalysisState(TypedDict):
    """State for the career analysis LangGraph."""
    resume_data: dict
    job_requirements: dict
    skill_mapping: dict
    readiness_score: float
    mindmap: str
    bridge_roles: list
    suggested_sessions: list[dict]
    error: str | None


# ============== Helper Functions ==============

def sanitize_mermaid_text(text: str, max_length: int = 50) -> str:
    """
    Sanitize text for Mermaid.js while preserving technical characters.
    Keeps: letters, numbers, spaces, +, #, ., /, -
    """
    if not text:
        return ""
    # Preserve common tech chars: C++, C#, Node.js, CI/CD
    safe_text = re.sub(r'[^a-zA-Z0-9\s\+\#\.\-\/]', '', str(text)).strip()
    # Truncate if strictly longer than max_length
    if len(safe_text) > max_length:
        safe_text = safe_text[:max_length-3] + "..."
    return safe_text or "Unknown"


def group_skills_by_type(skills: list) -> dict:
    """
    Group skills into categories using keyword matching.
    Returns: {"Languages": [...], "Frameworks": [...], "Cloud & DevOps": [...], "Databases": [...], "Other": [...]}
    """
    categories = {
        "Languages": [],
        "Frameworks": [],
        "Cloud & DevOps": [],
        "Databases": [],
        "Other": []
    }
    
    # Keyword patterns for categorization
    language_keywords = ['python', 'java', 'javascript', 'typescript', 'c++', 'c#', 'go', 'rust', 'ruby', 'php', 'swift', 'kotlin', 'scala', 'r', 'sql']
    framework_keywords = ['react', 'angular', 'vue', 'django', 'flask', 'fastapi', 'spring', 'node', 'express', 'rails', 'laravel', 'next', 'nuxt', 'svelte', 'pytorch', 'tensorflow', 'pandas']
    cloud_keywords = ['aws', 'azure', 'gcp', 'docker', 'kubernetes', 'k8s', 'ci/cd', 'jenkins', 'terraform', 'ansible', 'linux', 'devops', 'cloud', 'serverless', 'lambda']
    db_keywords = ['mysql', 'postgres', 'mongodb', 'redis', 'elasticsearch', 'dynamodb', 'cassandra', 'oracle', 'sqlite', 'nosql', 'database', 'sql']
    
    for skill in skills:
        skill_lower = str(skill).lower()
        if any(kw in skill_lower for kw in language_keywords):
            categories["Languages"].append(skill)
        elif any(kw in skill_lower for kw in framework_keywords):
            categories["Frameworks"].append(skill)
        elif any(kw in skill_lower for kw in cloud_keywords):
            categories["Cloud & DevOps"].append(skill)
        elif any(kw in skill_lower for kw in db_keywords):
            categories["Databases"].append(skill)
        else:
            categories["Other"].append(skill)
    
    return categories


# ============== Skill Mapping Node (LLM-Based) ==============

async def map_skills_node(state: CareerAnalysisState) -> CareerAnalysisState:
    """
    Use the LLM to act as a Senior Recruiter and semantically match the candidate.
    This replaces brittle string matching with "Semantic Analysis".
    """
    import json
    from server.services.llm_factory import get_chat_model
    from langchain_core.messages import SystemMessage, HumanMessage
    
    resume_data = state.get("resume_data", {})
    job_reqs = state.get("job_requirements", {})
    
    if not resume_data or not job_reqs:
        return {
            **state,
            "skill_mapping": {"matched": [], "partial": [], "missing": []},
            "readiness_score": 0.0,
            "error": "Missing resume or job data"
        }

    # 1. Prepare Context for the Brain
    candidate_skills = get_all_skills(resume_data)
    candidate_skills_list = list(candidate_skills) if candidate_skills else []
    
    # Get experience for context
    experience = resume_data.get("experience", [])
    experience_summary = []
    for exp in experience[:3]:  # Limit to 3 experiences
        if isinstance(exp, dict):
            title = exp.get("title", "")
            company = exp.get("company", "")
            if title:
                experience_summary.append(f"{title} at {company}" if company else title)
    
    candidate_summary = f"""
Skills: {', '.join(candidate_skills_list)}
Experience: {', '.join(experience_summary)}
"""
    
    job_title = job_reqs.get("job_title", "Unknown Role")
    must_have = job_reqs.get("must_have_skills", [])
    nice_to_have = job_reqs.get("nice_to_have_skills", [])
    
    jd_summary = f"""
Role: {job_title}
Must-Haves: {', '.join(must_have)}
Nice-to-Haves: {', '.join(nice_to_have)}
"""

    print(f"🔍 Matching {len(candidate_skills_list)} candidate skills against {len(must_have)} requirements")

    # 2. The "AI Recruiter" Prompt
    system_prompt = """You are a Senior Technical Recruiter. Evaluate this candidate against the job requirements.
    
CRITICAL RULES:
1. Use SEMANTIC MATCHING. (e.g., If candidate has "FastAPI", that counts as "Python Frameworks" or "REST APIs").
2. If candidate has "PyTorch" or "TensorFlow", that matches "Machine Learning".
3. If candidate has "MongoDB", that matches "NoSQL" or "Databases".
4. Be generous. If they have 60%+ of the skills, give them a fair score.
5. Output JSON ONLY. No markdown, no explanations.

Output Format:
{
  "matched": [
    {"name": "Skill Name", "reason": "Briefly why this is a strong match (1 sentence)"}
  ],
  "missing": [
    {"name": "Skill Name", "reason": "Why this is critical for the role", "learning_tip": "One specific resource or project idea to learn this"}
  ],
  "score": 0.0 to 1.0,
  "analysis": "1 sentence explanation"
}"""

    user_msg = f"CANDIDATE:\n{candidate_summary}\n\nJOB:\n{jd_summary}"

    # 3. Call LLM with streaming to show output
    try:
        chat_model = get_chat_model()
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_msg)
        ]
        
        print("\n🤖 LLM Thinking (streaming):")
        print("-" * 50)
        
        # Stream the response and collect it
        raw_content = ""
        async for chunk in chat_model.astream(messages):
            token = chunk.content
            if token:
                print(token, end="", flush=True)
                raw_content += token
        
        print("\n" + "-" * 50)
        
        # 4. Parse Response - Robust clean
        clean_content = raw_content.strip()
        
        # Remove markdown code blocks if present
        if "```" in clean_content:
            import re
            match = re.search(r'```(?:json)?\s*(.*?)```', clean_content, re.DOTALL)
            if match:
                clean_content = match.group(1).strip()
        
        # Additional cleaning
        clean_content = clean_content.replace("\n", " ").replace("\r", "")
        
        try:
            result = json.loads(clean_content)
        except json.JSONDecodeError:
            import re
            clean_content = re.sub(r',(\s*[\}\]])', r'\1', clean_content)
            try:
                result = json.loads(clean_content)
            except:
                 try:
                     from json_repair import repair_json
                     result = json.loads(repair_json(clean_content))
                 except Exception:
                     result = {"matched": [], "missing": [], "score": 0.5}

        matched = result.get("matched", [])
        missing = result.get("missing", [])
        score = result.get("score", 0.5)
        
        if isinstance(score, str):
            try:
                score = float(score)
            except:
                score = 0.5
        score = min(1.0, max(0.0, score))
        
        return {
            **state,
            "skill_mapping": {
                "matched": matched,
                "missing": missing,
                "partial": [],
                "candidate_extra_skills": candidate_skills_list[:5]
            },
            "readiness_score": round(score, 2)
        }
        
    except Exception as e:
        print(f"⚠️ LLM Matching Failed: {e}")
        return {
            **state,
            "skill_mapping": {
                "matched": [{"name": s, "reason": "Detected in resume"} for s in candidate_skills_list[:3]],
                "missing": [{"name": s, "reason": "Required by job"} for s in must_have[:3]],
                "partial": [],
                "candidate_extra_skills": []
            },
            "readiness_score": 0.5,
            "error": f"AI Matching failed: {e}"
        }


# ---------------------------------------------------------
# NEW: The Architect Node (Replaces generate_dynamic_suggestions)
# ---------------------------------------------------------
async def generate_interview_loop_node(state: CareerAnalysisState) -> CareerAnalysisState:
    """
    Uses LLM to generate a custom 3-Round Interview Cycle based on
    Resume, Job Description, and Company Culture.
    """
    print("🏗️  Architecting custom interview loop...")
    
    resume_summary = state.get("resume_data", {}).get("summary", "Candidate")
    job_reqs = state.get("job_requirements", {})
    target_role = job_reqs.get("job_title", "Professional")
    company = job_reqs.get("target_company", "the company")
    
    # Get top gaps for context
    missing = state.get("skill_mapping", {}).get("missing", [])
    gaps_text = ', '.join([s['name'] for s in missing[:3]])
    
    system_prompt = """You are an Expert Hiring Manager designing an interview loop.
    Create a 3-Round Interview Cycle for this specific candidate and role.
    
    STRUCTURE:
    1. Round 1 (The Screen): Behavioral/Fit check specific to this company.
    2. Round 2 (The Skill Check): A hard technical or practical drill focusing on the candidate's WEAKNESSES.
    3. Round 3 (The Final Loop): A realistic onsite scenario (System Design, Case Study, or Role Play).

    OUTPUT JSON ONLY:
    {
      "goal": "Role Name",
      "rounds": [
        {
          "id": "r1", "name": "Round 1: [Creative Title]", "description": "...", "status": "active",
          "sessions": [{"id": "s1", "title": "...", "type": "behavioral", "duration": "15m", "status": "pending"}]
        },
        {
          "id": "r2", "name": "Round 2: [Creative Title]", "description": "...", "status": "active",
          "sessions": [{"id": "s2", "title": "...", "type": "technical", "duration": "45m", "status": "pending"}]
        },
        {
          "id": "r3", "name": "Round 3: [Creative Title]", "description": "...", "status": "active",
          "sessions": [...]
        }
      ]
    }
    """
    
    user_msg = f"ROLE: {target_role} at {company}\nCANDIDATE GAPS: {gaps_text}"

    try:
        from server.services.llm_factory import get_chat_model
        chat_model = get_chat_model()
        response = await chat_model.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_msg)
        ])
        
        # Parse JSON safely
        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1]
            
        loop_plan = json.loads(content)
        loop_plan["created_at"] = str(datetime.now())
        
        # --- ENFORCE STABLE IDs (Fix for Caching) ---
        # Regardless of what LLM output, force s1, s2, s3...
        try:
             session_count = 1
             if "rounds" in loop_plan:
                 for round_ in loop_plan["rounds"]:
                     if "sessions" in round_:
                         for sess in round_["sessions"]:
                             sess["id"] = f"s{session_count}"
                             session_count += 1
        except Exception as e:
            print(f"⚠️ Failed to re-index session IDs: {e}")
            
        # Save to state
        return {**state, "practice_plan": loop_plan}

    except Exception as e:
        print(f"❌ Architect Failed: {e}")
        return {**state, "practice_plan": _fallback_loop(target_role)}

def _fallback_loop(role):
    """Fallback if LLM fails."""
    return {
        "goal": role,
        "rounds": [
            {
                "id": "r1", "name": "Round 1: Screening", "status": "active",
                "sessions": [{"id": "s1", "title": "Resume Review (Fallback)", "type": "behavioral", "duration": "15m", "status": "pending"}]
            },
            {
                "id": "r2", "name": "Round 2: Technical", "status": "active",
                "sessions": [{"id": "s2", "title": "Core Skills (Fallback)", "type": "technical", "duration": "30m", "status": "pending"}]
            },
            {
                "id": "r3", "name": "Round 3: Final", "status": "active",
                "sessions": [{"id": "s3", "title": "Scenario (Fallback)", "type": "technical", "duration": "45m", "status": "pending"}]
            }
        ]
    }


# Track active background generation tasks to prevent duplicates
_active_background_tasks: set[str] = set()
# Time-based cooldown: user_id -> last trigger timestamp
_generation_cooldowns: dict[str, float] = {}
# Cooldown period in seconds
_GENERATION_COOLDOWN_SECONDS = 60

def trigger_background_generation(user_id: str, state: CareerAnalysisState):
    """
    Fire-and-forget task to pre-generate questions for all sessions.
    Handles both practice_plan (new) and suggested_sessions (legacy) formats.
    Includes deduplication and time-based cooldown.
    """
    import time
    from server.services.cache import get_question_cache

    # Cooldown check
    now = time.time()
    last_trigger = _generation_cooldowns.get(user_id, 0)
    if now - last_trigger < _GENERATION_COOLDOWN_SECONDS:
        return

    # Active task check
    if user_id in _active_background_tasks:
        return

    cache = get_question_cache()
    uncached_sessions = []

    # Collect sessions from practice_plan (new format)
    practice_plan = state.get("practice_plan", {})
    if practice_plan and "rounds" in practice_plan:
        for round_obj in practice_plan["rounds"]:
            for sess in round_obj.get("sessions", []):
                cache_key = f"{user_id}_{sess['id']}"
                if not cache.get(cache_key):
                    uncached_sessions.append(sess)

    # Also collect from suggested_sessions (legacy format)
    suggestions = state.get("suggested_sessions", [])
    if suggestions:
        for sess in suggestions:
            job_title = state.get("job_requirements", {}).get("job_title", "generic")
            safe_title = re.sub(r'[^a-zA-Z0-9]', '_', job_title).lower()
            cache_key = f"{user_id}_{safe_title}_{sess['id']}"
            if not cache.get(cache_key):
                # Avoid duplicates if same session exists in both formats
                existing_ids = {s.get("id") for s in uncached_sessions}
                if sess.get("id") not in existing_ids:
                    uncached_sessions.append(sess)

    if not uncached_sessions:
        _generation_cooldowns[user_id] = now
        return

    # Mark as active and update cooldown
    _active_background_tasks.add(user_id)
    _generation_cooldowns[user_id] = now

    async def _generate_task():
        from server.agents.interview_nodes import generate_interview_questions

        try:
            print(f"🚀 Generating questions for {len(uncached_sessions)} session(s)...")

            for sess in uncached_sessions:
                try:
                    job_title = state.get("job_requirements", {}).get("job_title", "Professional")

                    # Determine focus based on session type
                    focus = []
                    if sess.get("type") == "behavioral":
                        focus = [{"name": "Behavioral Questions"}]
                    elif sess.get("focus_topic"):
                        focus = [{"name": sess["focus_topic"]}]

                    interview_state = {
                        "job_title": job_title,
                        "skill_gaps": focus or state.get("skill_mapping", {}).get("missing", []),
                        "readiness_score": state.get("readiness_score", 0.5),
                        "mode": "practice",
                        "questions": [],
                        "current_question_index": 0
                    }

                    print(f"⚡ Pre-generating for [{sess.get('title', sess.get('id'))}]...")
                    result_state = await generate_interview_questions(interview_state)

                    questions = result_state.get("questions", [])
                    if questions:
                        # Cache with both key formats for compatibility
                        simple_key = f"{user_id}_{sess['id']}"
                        cache.set(simple_key, questions)

                        safe_title = re.sub(r'[^a-zA-Z0-9]', '_', job_title).lower()
                        full_key = f"{user_id}_{safe_title}_{sess['id']}"
                        if full_key != simple_key:
                            cache.set(full_key, questions)

                        print(f"💾 Cached {len(questions)} Qs for {sess['id']}")

                        # Persist to DB plan if applicable
                        try:
                            from server.services.user_database import get_user_db
                            user_db = get_user_db()
                            if practice_plan and "rounds" in practice_plan:
                                for round_ in practice_plan["rounds"]:
                                    for s in round_.get("sessions", []):
                                        if s.get("id") == sess["id"]:
                                            s["questions"] = questions
                                user_db.update_latest_analysis_plan(user_id, practice_plan)
                        except Exception as e:
                            print(f"⚠️ Failed to persist questions to DB: {e}")

                except Exception as e:
                    print(f"⚠️ Failed to pre-generate for session {sess.get('id')}: {e}")

            print("✅ Background generation complete.")
        except Exception as e:
            print(f"❌ Background generation error: {e}")
        finally:
            _active_background_tasks.discard(user_id)

    # Launch in background
    import asyncio
    asyncio.create_task(_generate_task())


# ============== Mindmap Generator Node ==============

async def generate_mindmap_node(state: CareerAnalysisState) -> CareerAnalysisState:
    """Generate a Mermaid.js flowchart visualization of skill gaps with adaptive layout."""
    skill_mapping = state.get("skill_mapping", {})
    job_requirements = state.get("job_requirements", {})
    readiness_score = state.get("readiness_score", 0.0)
    
    job_title = job_requirements.get("job_title", "Target Role")
    safe_title = sanitize_mermaid_text(job_title, max_length=40)
    
    def get_skill_name(skill_obj):
        if isinstance(skill_obj, dict):
            return skill_obj.get("name", "Unknown")
        return str(skill_obj)

    matched = skill_mapping.get("matched", [])[:10]
    partial = skill_mapping.get("partial", [])[:10]
    missing = skill_mapping.get("missing", [])[:10]
    extra = skill_mapping.get("candidate_extra_skills", [])[:5]
    
    total_skills = len(matched) + len(partial) + len(missing) + len(extra)
    layout = "TD" if total_skills > 15 else "LR"
    
    lines = [
        f"flowchart {layout}",
        "",
        "    classDef green fill:#065f46,stroke:#10b981,stroke-width:2px,color:#fff",
        "    classDef yellow fill:#854d0e,stroke:#eab308,stroke-width:2px,color:#fff",
        "    classDef red fill:#7f1d1d,stroke:#ef4444,stroke-width:2px,color:#fff",
        "    classDef blue fill:#1e3a5f,stroke:#3b82f6,stroke-width:2px,color:#fff",
        "    classDef root fill:#4c1d95,stroke:#8b5cf6,stroke-width:3px,color:#fff",
        "",
        f"    ROOT[({safe_title}<br/>Score: {int(readiness_score * 100)}%)]:::root",
    ]
    
    node_id = 0
    
    if matched:
        lines.append(f"    ROOT --> STRENGTHS[✓ Strengths]:::green")
        for skill in matched:
            safe_skill = sanitize_mermaid_text(get_skill_name(skill))
            if safe_skill and safe_skill != "Unknown":
                lines.append(f"    STRENGTHS --> S{node_id}[{safe_skill}]:::green")
                node_id += 1
    
    if partial:
        lines.append(f"    ROOT --> DEVELOPING[◐ Developing]:::yellow")
        for skill in partial:
            safe_skill = sanitize_mermaid_text(get_skill_name(skill))
            if safe_skill and safe_skill != "Unknown":
                lines.append(f"    DEVELOPING --> D{node_id}[{safe_skill}]:::yellow")
                node_id += 1
    
    if missing:
        lines.append(f"    ROOT --> GAPS[✗ Gaps]:::red")
        for skill in missing:
            safe_skill = sanitize_mermaid_text(get_skill_name(skill))
            if safe_skill and safe_skill != "Unknown":
                lines.append(f"    GAPS --> G{node_id}[{safe_skill}]:::red")
                node_id += 1
    
    if extra:
        lines.append(f"    ROOT --> BONUS[★ Bonus]:::blue")
        for skill in extra:
            safe_skill = sanitize_mermaid_text(get_skill_name(skill))
            if safe_skill and safe_skill != "Unknown":
                lines.append(f"    BONUS --> B{node_id}[{safe_skill}]:::blue")
                node_id += 1
    
    diagram = "\n".join(lines)
    
    return {
        **state,
        "mindmap": diagram
    }


# ============== Bridge Role Suggester Node ==============

async def suggest_bridge_roles_node(state: CareerAnalysisState) -> CareerAnalysisState:
    """Suggest bridge roles if readiness score < 0.6."""
    readiness_score = state.get("readiness_score", 0.0)
    job_requirements = state.get("job_requirements", {})
    resume_data = state.get("resume_data", {})
    
    bridge_roles = []
    
    if readiness_score < 0.6:
        job_title = job_requirements.get("job_title", "")
        target_level = job_requirements.get("career_level", estimate_role_level(job_title))
        current_skills = get_all_skills(resume_data)
        
        bridge_roles = get_bridge_role_suggestions(
            job_title,
            target_level,
            current_skills
        )
        
        missing_skills = state.get("skill_mapping", {}).get("missing", [])
        for role in bridge_roles:
            role["skills_to_develop"] = missing_skills[:3]
    
    return {
        **state,
        "bridge_roles": bridge_roles
    }


# ============== Full Analysis Pipeline with Progress Callbacks ==============

async def analyze_career_path(
    resume_text: str | bytes,
    target_role: str,
    target_company: str = "a top tech company",
    emit_progress: Optional[Callable[[str, str], Any]] = None
) -> CareerAnalysisState:
    """
    OPTIMIZED Career Analysis Pipeline with Parallel Execution.
    
    Pipeline: 
    1. Extract PDF text (if needed)
    2. PARALLEL: Parse resume (LLM) + Infer job requirements (LLM)
    3. Map skills with streaming (LLM)
    4. Generate mindmap (rule-based)
    5. Suggest bridge roles (rule-based)
    """
    from server.tools.job_tool import infer_job_requirements
    # CHANGED: Use the correct function name here
    from server.tools.resume_tool import parse_resume_node, extract_text_from_pdf_bytes
    
    async def _emit(stage: str, message: str):
        if emit_progress:
            await emit_progress(stage, message)
        print(f"📊 [{stage}] {message}")
    
    # Initialize state
    state: CareerAnalysisState = {
        "resume_data": {},
        "job_requirements": {},
        "skill_mapping": {},
        "readiness_score": 0.0,
        "mindmap": "",
        "bridge_roles": [],
        "error": None
    }
    
    try:
        # ========== Step 1: Prepare Resume Text ==========
        await _emit("step_1", "📄 Processing resume...")
        
        final_resume_text = ""
        if isinstance(resume_text, bytes):
             await _emit("step_1", "📄 Extracting text from resume PDF...")
             # CHANGED: Call the correct function
             final_resume_text = extract_text_from_pdf_bytes(resume_text)
        else:
             final_resume_text = resume_text

        if not final_resume_text.strip():
            state["error"] = "Could not extract text from resume"
            return state
        
        await _emit("step_1_done", f"✅ Processed {len(final_resume_text)} characters")
        
        # ========== Step 2: PARALLEL - Parse resume + Infer job requirements ==========
        await _emit("step_2", f"🚀 Parallel processing: parsing resume AND analyzing {target_role} requirements...")
        
        resume_bytes_for_parsing = final_resume_text.encode('utf-8')
        resume_task = parse_resume_node(resume_bytes_for_parsing, mime_type="text/plain")
        job_task = infer_job_requirements(target_role, target_company)
        
        resume_data, job_requirements = await asyncio.gather(
            resume_task,
            job_task,
            return_exceptions=True
        )
        
        if isinstance(resume_data, Exception):
            await _emit("error", f"❌ Resume parsing failed: {resume_data}")
            resume_data = {"skills": {}, "experience": []}
        
        state["resume_data"] = resume_data
        
        if isinstance(job_requirements, Exception):
            await _emit("error", f"❌ Job inference failed: {job_requirements}")
            job_requirements = {
                "job_title": target_role, 
                "must_have_skills": [], 
                "nice_to_have_skills": []
            }
        
        state["job_requirements"] = job_requirements
        
        # ========== Step 3: Map skills with streaming ==========
        await _emit("step_3", "🎯 AI matching skills to requirements (streaming)...")
        state = await map_skills_node(state)
        await _emit("step_3_done", "✅ Skill mapping complete")
        
        # ========== Step 4: Generate mindmap ==========
        await _emit("step_4", "🗺️ Generating visual mindmap...")
        state = await generate_mindmap_node(state)
        await _emit("step_4_done", "✅ Mindmap generated")
        
        # ========== Step 5: Suggest bridge roles ==========
        if state["readiness_score"] < 0.6:
            await _emit("step_5", "🌉 Analyzing career path options...")
            state = await suggest_bridge_roles_node(state)

        # ========== Step 6: Generate Interview Loop (LLM-Driven) ==========
        await _emit("step_6", "🏗️ Architecting your interview loop...")
        state = await generate_interview_loop_node(state)
        
        # Also generate legacy suggestions for backwards compatibility
        missing_skills = state["skill_mapping"].get("missing", [])
        suggestions = generate_dynamic_suggestions(target_role, target_company, missing_skills)
        state["suggested_sessions"] = suggestions
        
        # ========== Done! ==========
        score = int(state["readiness_score"] * 100)
        await _emit("complete", f"🎉 Analysis complete! Readiness: {score}%")
        
        return state
        
    except Exception as e:
        await _emit("error", f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        state["error"] = str(e)
        return state


# ============== Regeneration & Background Logic ==============

async def regenerate_suggestions(
    old_state: CareerAnalysisState,
    user_prompt: str
) -> list[dict]:
    """
    Regenerate interview suggestions based on user prompt.
    E.g. "Give me harder system design questions" or "Focus on Python only".
    """
    resume_data = old_state.get("resume_data", {})
    job_requirements = old_state.get("job_requirements", {})
    skill_mapping = old_state.get("skill_mapping", {})
    
    job_title = job_requirements.get("job_title", "Software Engineer")
    company = job_requirements.get("target_company", "a top tech company")
    
    # Extract skills
    missing = [s.get("name") for s in skill_mapping.get("missing", [])[:5]]
    matched = [s.get("name") for s in skill_mapping.get("matched", [])[:5]]
    
    system_prompt = f"""You are an expert interview coach for {job_title} roles at {company}.
    
    CONTEXT:
    - User Strengths: {', '.join(matched)}
    - User Gaps: {', '.join(missing)}
    
    CURRENT TASK:
    Generate 3 NEW, distinct interview session suggestions based on this user request:
    "{user_prompt}"
    
    OUTPUT JSON ONLY (List of 3 objects):
    [
      {{
        "id": "s1",  // ALWAYS use s1, s2, s3 for the 3 items
        "title": "Short Title",
        "subtitle": "Subtitle",
        "description": "1 sentence description",
        "icon": "Material Icon Name (e.g. Code, Storage, Security, Psychology)",
        "color": "blue|red|green|orange|purple",
        "duration": "15 min",
        "type": "technical|behavioral|drill",
        "focus_topic": "Specific topic if drill/technical"
      }}
    ]
    """
    
    try:
        from server.services.llm_factory import get_chat_model
        chat_model = get_chat_model()
        
        response = await chat_model.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content="Generate new suggestions.")
        ])
        
        from server.tools.resume_tool import parse_json_safely
        new_suggestions = parse_json_safely(response.content)
        
        if not new_suggestions or not isinstance(new_suggestions, list):
            raise ValueError("Invalid suggestion format")
            
        return new_suggestions
        
    except Exception as e:
        print(f"❌ Regeneration failed: {e}")
        # Fallback to defaults
        return generate_dynamic_suggestions(job_title, company, skill_mapping.get("missing", []))


# NOTE: Duplicate trigger_background_generation and globals removed.
# The unified version above (using shared _active_background_tasks, _generation_cooldowns)
# handles both practice_plan (new) and suggested_sessions (legacy) formats.


# ============== Legacy Session Generator (Kept for backwards compatibility) ==============

def generate_dynamic_suggestions(target_role: str, company: str, missing_skills: list) -> list[dict]:
    """
    Generate 3 personalized session cards based on role and gaps.
    DEPRECATED: Use generate_interview_loop_node instead.
    """
    suggestions = []
    role_lower = target_role.lower()

    # --- Card 1: Resume Deep Dive (Always valuable) ---
    suggestions.append({
        "id": "resume",
        "title": "Resume Deep Dive",
        "subtitle": "Based on your experience",
        "description": "AI will quiz you on specific projects and claims found in your resume.",
        "icon": "Description",
        "color": "purple",
        "duration": "15 min",
        "type": "resume"
    })

    # --- Card 2: Role-Specific Core ---
    if any(x in role_lower for x in ["nurse", "medical", "doctor", "clinical"]):
        # Healthcare
        suggestions.append({
            "id": "clinical_core",
            "title": "Clinical Scenarios",
            "subtitle": f"Core {target_role} Skills",
            "description": "Patient triage, bedside manner, and situational judgement questions.",
            "icon": "LocalHospital",
            "color": "red",
            "duration": "20 min",
            "type": "technical"
        })
    elif any(x in role_lower for x in ["sales", "account", "business", "marketing"]):
        # Business
        suggestions.append({
            "id": "business_case",
            "title": "Mock Pitch & Strategy",
            "subtitle": f"For {company}",
            "description": "Value proposition, objection handling, and strategic thinking.",
            "icon": "TrendingUp",
            "color": "green",
            "duration": "20 min",
            "type": "technical"
        })
    elif any(x in role_lower for x in ["engineer", "developer", "data", "scientist"]):
        # Tech
        suggestions.append({
            "id": "tech_core",
            "title": "Technical Core",
            "subtitle": f"{target_role} Fundamentals",
            "description": "Algorithms, system design, and technical concepts for this role.",
            "icon": "Code",
            "color": "blue",
            "duration": "20 min",
            "type": "technical"
        })
    else:
        # General / Universal
        suggestions.append({
            "id": "role_core",
            "title": f"{target_role} Core",
            "subtitle": "Role Competencies",
            "description": f"Standard interview questions tailored for {target_role} positions.",
            "icon": "Work",
            "color": "blue",
            "duration": "20 min",
            "type": "technical"
        })

    # --- Card 3: Targeted Weakness Drill ---
    if missing_skills:
        # Pick the first major gap
        try:
            gap_name = missing_skills[0].get("name", "General") if isinstance(missing_skills[0], dict) else str(missing_skills[0])
        except (IndexError, AttributeError):
            gap_name = "General"
            
        suggestions.append({
            "id": "gap_drill",
            "title": f"Drill: {gap_name}",
            "subtitle": "Focus on your Gap",
            "description": f"Intensive practice session to improve your knowledge of {gap_name}.",
            "icon": "Warning",
            "color": "orange",
            "duration": "15 min",
            "type": "drill",
            "focus_topic": gap_name
        })
    else:
        # Fallback if no gaps (Behavioral)
        suggestions.append({
            "id": "behavioral",
            "title": "Behavioral Fit",
            "subtitle": f"Culture at {company}",
            "description": "STAR method practice and culture-fit questions.",
            "icon": "EmojiPeople",
            "color": "orange",
            "duration": "15 min",
            "type": "behavioral"
        })

    return suggestions