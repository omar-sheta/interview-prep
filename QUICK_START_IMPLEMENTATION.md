# InterviewIQ - Quick Start Implementation Guide
## Get Production-Ready in 2 Days

---

## 📍 Where You Are Now

✅ **What's Already Fixed (Just Completed):**
1. CommandCenter now uses saved preferences (no re-upload needed)
2. Session persistence works correctly
3. JSON parse errors in mindmap generation are handled gracefully

✅ **What's Working:**
- User signup/login
- Resume upload & analysis
- Career gap visualization
- Interview sessions with voice transcription
- Real-time coaching hints
- Answer evaluation
- Session history

---

## 🎯 What You Need to Do (Priority Order)

### CRITICAL PATH (Must-Have for Launch)

#### 1. Multi-Session Intelligence (2-3 hours)
**Why:** Makes questions actually personalized to user's weak areas

**Files to Modify:**
```
/server/services/user_database.py  (Add 2 new methods)
/server/agents/interview_nodes.py   (Modify question generation)
/server/main.py                     (Pass user history to question gen)
```

**Quick Implementation:**
```python
# In user_database.py, add:
def get_recent_sessions_analysis(self, user_id, limit=5):
    """Returns weak_skills, strong_skills, stagnant_skills, overall_trend"""
    # Query last 5 sessions
    # Aggregate scores by skill
    # Calculate trends
    # Return dict

# In interview_nodes.py, modify generate_interview_questions():
# Add parameter: user_history=None
# If user_history has stagnant_skills:
#     system_prompt += "User keeps failing X, approach differently"
# If user_history has weak_skills:
#     system_prompt += "Focus 60% questions on: " + weak_skills

# In main.py start_interview event:
user_history = user_db.get_recent_sessions_analysis(user_id)
questions = await generate_interview_questions(state, user_history=user_history)
```

---

#### 2. Follow-Up Questions (1-2 hours)
**Why:** AI can clarify misunderstandings in real-time

**Files to Modify:**
```
/server/agents/interview_nodes.py  (Add should_generate_followup function)
/server/main.py                    (Call after answer evaluation)
```

**Quick Implementation:**
```python
# In interview_nodes.py:
async def should_generate_followup(question, user_answer, evaluation):
    score = evaluation["score"]
    if score >= 7:
        return None  # Good answer, no follow-up

    if score < 5:
        prompt = "Generate simpler question on same concept"
    else:
        prompt = "Generate deeper question on missing concepts"

    followup = await llm.ainvoke(prompt)
    return parse_json_safely(followup.content)

# In main.py submit_interview_answer event (after evaluation):
followup = await should_generate_followup(current_question, answer, evaluation)
if followup:
    session_state.questions.insert(next_index, followup)
    await sio.emit("follow_up_added", {"message": "AI preparing follow-up"}, room=sid)
```

---

#### 3. Role-Specific Question Generation (1-2 hours)
**Why:** Makes it work for non-tech jobs too

**Files to Modify:**
```
/server/agents/interview_nodes.py  (Add role type detection + templates)
```

**Quick Implementation:**
```python
# In interview_nodes.py:
def detect_role_type(job_title):
    tech_keywords = ["engineer", "developer", "programmer", "architect"]
    business_keywords = ["manager", "analyst", "consultant", "coordinator"]
    healthcare_keywords = ["nurse", "doctor", "medical", "clinical"]
    # ... check keywords, return "tech", "business", "healthcare", "creative", "other"

# In generate_interview_questions():
role_type = detect_role_type(job_title)

if role_type == "tech":
    question_distribution = {"technical": 0.5, "system_design": 0.3, "behavioral": 0.2}
elif role_type == "business":
    question_distribution = {"role_specific": 0.4, "behavioral": 0.35, "case_study": 0.25}
elif role_type == "healthcare":
    question_distribution = {"clinical": 0.45, "situational": 0.35, "ethics": 0.2}
# ... add to prompt
```

---

#### 4. Error Handling & Reconnection (1 hour)
**Why:** Prevents data loss and bad user experience

**Files to Modify:**
```
/server/main.py                      (Add error decorator)
/client/src/store/useInterviewStore.js  (Add reconnection config)
```

**Quick Implementation:**
```python
# In main.py:
def handle_socket_errors(func):
    @wraps(func)
    async def wrapper(sid, data=None):
        try:
            return await func(sid, data)
        except Exception as e:
            print(f"Error in {func.__name__}: {e}")
            await sio.emit("error", {"message": str(e)}, room=sid)
    return wrapper

# Apply to all @sio.event handlers:
@sio.event
@handle_socket_errors
async def start_interview(sid, data):
    # existing code...
```

```javascript
// In useInterviewStore.js connect():
const newSocket = io(SOCKET_URL, {
    transports: ['websocket'],
    reconnection: true,
    reconnectionDelay: 1000,
    reconnectionAttempts: 5
});

newSocket.on('reconnect', () => {
    console.log('Reconnected!');
    // Restore session
    const { userId } = get();
    newSocket.emit('restore_session', { user_id: userId });
});
```

---

#### 5. Security - Bcrypt Passwords (30 mins)
**Why:** SHA256 is not secure for passwords

**Files to Modify:**
```
/server/services/user_database.py  (Replace hashlib with bcrypt)
requirements.txt                   (Add bcrypt)
```

**Quick Implementation:**
```bash
# Add to requirements.txt:
bcrypt==4.1.2
```

```python
# In user_database.py:
import bcrypt

# In create_user():
password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

# In authenticate_user():
is_valid = bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8'))
return user if is_valid else None
```

---

#### 6. Rate Limiting (30 mins)
**Why:** Prevent abuse (users spamming sessions)

**Files to Modify:**
```
/server/main.py  (Add rate limit checker)
```

**Quick Implementation:**
```python
# In main.py (top level):
from collections import defaultdict
from time import time

rate_limits = defaultdict(list)
RATE_LIMIT = 5  # sessions per hour

def is_rate_limited(user_id, action):
    key = f"{user_id}:{action}"
    now = time()
    # Clean old entries
    rate_limits[key] = [t for t in rate_limits[key] if now - t < 3600]

    if len(rate_limits[key]) >= RATE_LIMIT:
        return True

    rate_limits[key].append(now)
    return False

# In start_interview event:
if is_rate_limited(user_id, "start_interview"):
    await sio.emit("error", {"message": "Rate limit exceeded. Please wait."}, room=sid)
    return
```

---

#### 7. UI Polish (1-2 hours)

**A. Add Loading Skeletons:**
```jsx
// client/src/components/LoadingSkeleton.jsx
export function QuestionSkeleton() {
    return (
        <div className="animate-pulse space-y-4">
            <div className="h-4 bg-white/10 rounded w-3/4"></div>
            <div className="h-20 bg-white/10 rounded w-full"></div>
        </div>
    );
}

// Use in InterviewView.jsx:
{isLoading ? <QuestionSkeleton /> : <QuestionDisplay question={currentQuestion} />}
```

**B. Improve Error Display:**
```jsx
// In InterviewView.jsx:
const [error, setError] = useState(null);

useEffect(() => {
    socket.on('error', (data) => {
        setError(data.message);
    });
}, []);

if (error) {
    return (
        <div className="min-h-screen flex items-center justify-center">
            <div className="text-center p-8 bg-red-500/10 border border-red-500/20 rounded-2xl">
                <h2 className="text-xl font-bold mb-2">Error</h2>
                <p className="text-gray-400 mb-4">{error}</p>
                <button onClick={() => window.location.reload()}>Reload</button>
            </div>
        </div>
    );
}
```

---

#### 8. Progress Dashboard (1-2 hours)

**Add Session Comparison:**
```jsx
// In Dashboard.jsx:
function SessionHistory({ sessions }) {
    return (
        <div className="bg-[#161b22] p-6 rounded-2xl">
            <h3 className="text-lg font-bold mb-4">Recent Sessions</h3>
            <table className="w-full">
                <thead>
                    <tr className="text-left text-gray-400 text-sm">
                        <th>Date</th>
                        <th>Score</th>
                        <th>Trend</th>
                    </tr>
                </thead>
                <tbody>
                    {sessions.map((s, i) => {
                        const prev = i > 0 ? sessions[i-1].average_score : null;
                        const trend = prev ? (s.average_score > prev ? '↑' : '↓') : '—';
                        return (
                            <tr key={s.session_id}>
                                <td>{formatDate(s.completed_at)}</td>
                                <td className="font-bold">{s.average_score.toFixed(1)}/10</td>
                                <td className={trend === '↑' ? 'text-green-400' : 'text-red-400'}>
                                    {trend}
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
}
```

---

### OPTIONAL (Nice-to-Have)

#### 9. Caching Career Analysis (30 mins)
```python
# In main.py:
analysis_cache = {}

@sio.event
async def start_career_analysis(sid, data=None):
    cache_key = f"{user_id}:{target_role}"
    if cache_key in analysis_cache:
        cached = analysis_cache[cache_key]
        if (datetime.now() - cached["timestamp"]).seconds < 86400:  # 24 hours
            await sio.emit("career_analysis", {"analysis": cached["data"]}, room=sid)
            return

    # Run analysis...
    analysis_cache[cache_key] = {"data": result, "timestamp": datetime.now()}
```

---

## 🚀 Deployment Steps (Day 2 Evening)

### 1. Backend Deployment (Render.com - Free Tier)

```bash
# Create Dockerfile
cat > Dockerfile << 'EOF'
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY server/ ./server/
COPY .env .env
RUN mkdir -p user_data qdrant_data
EXPOSE 8000
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF

# Push to GitHub
git add .
git commit -m "Production ready"
git push origin main

# On Render.com:
# 1. Create new Web Service
# 2. Connect GitHub repo
# 3. Set environment variables (LLM_MODEL_ID, CORS_ORIGINS)
# 4. Deploy
```

---

### 2. Frontend Deployment (Vercel - Free Tier)

```bash
cd client

# Update API URL for production
cat > src/config.js << 'EOF'
export const API_URL = import.meta.env.PROD
    ? 'https://your-backend.onrender.com'
    : 'http://localhost:8000';

export const SOCKET_URL = API_URL;
EOF

# Build
npm run build

# Deploy to Vercel
npx vercel --prod

# Or push to GitHub and connect Vercel to auto-deploy
```

---

## ✅ Testing Checklist

### Before Launch
- [ ] Signup new user (test@example.com)
- [ ] Upload resume PDF
- [ ] Career analysis completes
- [ ] Mindmap displays correctly
- [ ] Start interview
- [ ] Speak answer (mic works)
- [ ] Transcript appears
- [ ] Request hint
- [ ] Submit answer
- [ ] Evaluation streams
- [ ] Complete session
- [ ] View in history
- [ ] Start 2nd session (verify adaptive questions)

### Cross-Browser
- [ ] Chrome (desktop + mobile)
- [ ] Firefox
- [ ] Safari (Mac + iOS)

### Error Scenarios
- [ ] Bad resume upload (corrupted PDF)
- [ ] Disconnect during interview (reconnect works)
- [ ] Rate limit exceeded (shows error)
- [ ] Invalid login credentials

---

## 📝 Launch Day Tasks

### Morning (Launch Prep)
1. Final production test
2. Monitor logs for 30 minutes
3. Fix any critical bugs
4. Prepare social media posts

### Afternoon (Soft Launch)
1. Share with 10-20 friends/network
2. Post on LinkedIn
3. Post on Twitter
4. Submit to BetaList
5. Monitor feedback closely

### Evening (Iterate)
1. Collect all feedback
2. Identify top 3 issues
3. Fix critical bugs
4. Plan improvements for Week 2

---

## 💡 Pro Tips

### Development
- Use `ThinkingTerminal` component to debug in real-time
- Check browser console for Socket.IO events
- Use `curl` to test backend endpoints
- Keep Ollama running (`ollama serve`)

### Debugging
```bash
# Check if backend is running
curl http://localhost:8000/health

# Check Socket.IO connection
node -e "const io = require('socket.io-client'); const s = io('http://localhost:8000'); s.on('connect', () => console.log('OK'));"

# Check Ollama
curl http://localhost:11434/api/tags
```

### Performance
- Keep audio chunks small (256ms)
- Limit mindmap to 50 nodes max
- Cache analysis results
- Lazy load dashboard charts

---

## 🎯 Success Criteria

By end of Day 2, you should have:
- ✅ Multi-session adaptive questions working
- ✅ Follow-up questions implemented
- ✅ Error handling everywhere
- ✅ Secure password hashing (bcrypt)
- ✅ Rate limiting in place
- ✅ Production deployment done
- ✅ User guide written
- ✅ Full flow tested

**You're ready to launch! 🚀**

---

## 📞 Quick Reference

### Important Files
```
Backend:
  /server/main.py                      - Socket events
  /server/agents/interview_nodes.py    - Question generation
  /server/services/user_database.py    - Database operations
  /server/config.py                    - Settings

Frontend:
  /client/src/App.jsx                  - Router
  /client/src/store/useInterviewStore.js  - State management
  /client/src/components/InterviewView.jsx - Main interview UI
  /client/src/components/Dashboard.jsx     - Progress tracking
```

### Socket Events (Backend → Frontend)
```
connected              - Initial connection
auth_success           - Login successful
career_analysis        - Analysis results
interview_question     - New question
transcript             - Live transcription
answer_evaluated       - Evaluation result
interview_complete     - Session done
error                  - Something went wrong
```

### Socket Events (Frontend → Backend)
```
signup                 - Create account
login                  - Authenticate
start_career_analysis  - Analyze resume
start_interview        - Begin session
user_audio_chunk       - Send audio
submit_interview_answer - Submit answer
request_hint           - Ask for help
end_interview_early    - Stop session
```

---

Good luck! You've got everything you need to launch a production-ready product in 2 days! 💪
