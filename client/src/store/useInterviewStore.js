/**
 * Zustand Store for Interview Agent
 * Manages global state for Socket.IO, app phases, and real-time data
 * With localStorage persistence for session data
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { io } from 'socket.io-client';

// App states flow: IDLE -> ANALYZING -> MAP_READY -> INTERVIEWING -> FEEDBACK
const APP_STATES = {
    IDLE: 'IDLE',
    ANALYZING: 'ANALYZING',
    MAP_READY: 'MAP_READY',
    INTERVIEWING: 'INTERVIEWING',
    FEEDBACK: 'FEEDBACK',
    COMPLETE: 'COMPLETE',
};

// Socket.IO instance managed in state
const useInterviewStore = create(
    persist(
        (set, get) => ({
            // Connection state (not persisted)
            socket: null,
            isConnected: false,
            connectionError: null,
            userId: null,  // User ID from server
            userEmail: null,  // User email for authentication

            // App state
            appState: APP_STATES.IDLE,
            onboardingComplete: false, // Tracks if user has logged in/completed onboarding

            // Career Analysis (PERSISTED)
            mindmap: '',
            readinessScore: 0,
            skillMapping: null,
            bridgeRoles: [],
            jobRequirements: null,
            resumeData: null,
            analysisProgress: '',

            // Last analysis metadata (PERSISTED)
            targetRole: '',
            targetCompany: '',
            focusAreas: [],
            lastAnalysisTime: null,
            suggestedSessions: [],
            practicePlan: null,

            // Interview (not persisted - live session)
            transcript: '',
            lastTranscript: '', // New: For tracking latest speech chunk
            currentTokens: '',
            ttsAudioQueue: [],
            isRecording: false,
            interviewPhase: 'warmup',

            // Interview Practice State (not persisted)
            interviewActive: false,
            interviewMode: 'practice', // 'practice' | 'coaching'
            currentQuestion: null,
            questionNumber: 0,
            totalQuestions: 0,
            answerEvaluation: null,
            coachingEnabled: true,
            coachingHint: null,
            allEvaluations: [],
            interviewSummary: null,

            // Thinking terminal (not persisted)
            thinkingLog: [],

            // ============== Actions ==============

            // Connect to Socket.IO Server
            connect: () => {
                let { socket, userId } = get();
                // Prevent multiple socket instances - check if socket exists AND is either connected or connecting
                if (socket && (socket.connected || socket.io.engine)) return;

                // Clean up any existing disconnected socket
                if (socket && !socket.connected) {
                    console.log('🧹 Cleaning up disconnected socket');
                    socket.removeAllListeners();
                    socket.close();
                    set({ socket: null });
                }

                // Bootstrap userId from localStorage if not in store (bridges legacy flows)
                if (!userId || userId === 'anonymous') {
                    const fallbackId = localStorage.getItem('user_id');
                    if (fallbackId && fallbackId !== 'anonymous') {
                        console.log('🔌 Bootstrapped userId from localStorage:', fallbackId);
                        set({ userId: fallbackId });
                        userId = fallbackId;
                    }
                }

                console.log('🔌 Connecting with userId:', userId);

                const newSocket = io('http://localhost:8000', {
                    transports: ['websocket'],
                    query: userId && userId !== 'anonymous' ? { user_id: userId } : {}
                });

                // Security Guard Helper
                const onSafe = (event, callback) => {
                    newSocket.on(event, (data) => {
                        const currentId = get().userId;
                        if (data && data.user_id && currentId && currentId !== 'anonymous' && data.user_id !== currentId) {
                            console.warn(`🛡️ Security Block: Dropped packet '${event}' for user ${data.user_id}`);
                            return;
                        }
                        callback(data);
                    });
                };

                set({ socket: newSocket });
                newSocket.on('connect', () => {
                    set({ isConnected: true, connectionError: null });
                    get().addThinking('🔌 Connected to Interview Agent');

                    // Restore session if we have a user ID
                    const { userId } = get();
                    if (userId) {
                        get().addThinking(`🔄 Restoring session for ${userId}...`);
                        newSocket.emit('restore_session', { user_id: userId });
                    }
                });

                newSocket.on('connected', (data) => {
                    if (data.user_id && data.user_id !== 'anonymous') {
                        set({ userId: data.user_id });
                        get().addThinking(`👤 User ID: ${data.user_id}`);
                    }
                });

                newSocket.on('auth_success', (data) => {
                    if (data.user?.user_id) {
                        set({ userId: data.user.user_id });
                        get().addThinking(`✅ Authenticated as ${data.user.email}`);
                    }
                });

                newSocket.on('session_restored', (data) => {
                    get().addThinking(`✅ Session restored for ${data.user.email}`);
                    const prefs = data.preferences || {};
                    set({
                        targetRole: prefs.target_role || '',
                        targetCompany: prefs.target_company || '',
                        focusAreas: prefs.focus_areas || []
                    });
                });

                newSocket.on('disconnect', () => {
                    set({ isConnected: false });
                    get().addThinking('🔌 Disconnected from server');
                });

                newSocket.on('connect_error', (error) => {
                    set({ connectionError: error.message });
                    get().addThinking(`❌ Connection error: ${error.message}`);
                });

                // Career Analysis events
                onSafe('analysis_progress', (data) => {
                    set({ analysisProgress: data.message });
                    get().addThinking(`📊 ${data.message}`);
                });

                // Handle career analysis (both fresh and loaded from DB)
                onSafe('career_analysis', (data) => {
                    const analysis = data.analysis;
                    if (analysis) {
                        get().addThinking('✅ Career analysis loaded');
                        set({
                            mindmap: analysis.analysis_data?.mindmap || analysis.analysis_data?.mindmap_code,
                            readinessScore: analysis.readiness_score,
                            skillMapping: analysis.skill_gaps ? {
                                missing: analysis.skill_gaps,
                                ...analysis.analysis_data?.skill_mapping
                            } : analysis.analysis_data?.skill_mapping,
                            bridgeRoles: analysis.bridge_roles,
                            jobRequirements: analysis.analysis_data?.job_requirements,
                            resumeData: analysis.analysis_data?.resume_data,
                            suggestedSessions: analysis.suggested_sessions || analysis.analysis_data?.suggested_sessions || [],
                            practicePlan: analysis.practice_plan || analysis.analysis_data?.practice_plan || null,
                            targetRole: analysis.job_title,
                            targetCompany: analysis.company,
                            lastAnalysisTime: analysis.created_at || Date.now(),
                            analysisProgress: 'Analysis Complete!',
                            appState: APP_STATES.MAP_READY
                        });
                    }
                });

                // Note: analysis_complete was removed - career_analysis handler above handles all cases

                onSafe('analysis_error', (data) => {
                    set({ analysisProgress: `Error: ${data.error}`, appState: APP_STATES.IDLE });
                    get().addThinking(`❌ Analysis failed: ${data.error}`);
                });

                // Interview events
                onSafe('interview_started', (data) => {
                    set({
                        interviewActive: true,
                        totalQuestions: data.total_questions,
                        currentQuestionIndex: 0,
                        interviewMode: data.mode,
                        appState: APP_STATES.INTERVIEWING
                    });
                });

                onSafe('interview_question', (data) => {
                    set({
                        currentQuestion: data.question,
                        questionNumber: data.question_number,
                        totalQuestions: data.total_questions || get().totalQuestions,
                        transcript: '',
                        answerEvaluation: null,
                        coachingHint: null
                    });
                    get().addThinking(`❓ Question ${data.question_number}: ${data.question.text}`);

                    // TTS for question
                    // get().queueTTS(data.question.text);
                });

                onSafe('transcript', (data) => {
                    set({
                        transcript: data.full || (get().transcript + ' ' + data.text),
                        lastTranscript: data.text
                    });
                });

                onSafe('coaching_hint', (data) => {
                    set({ coachingHint: data });
                    get().addThinking(`💡 Hint: ${data.message}`);
                });

                onSafe('answer_evaluated', (data) => {
                    set({ answerEvaluation: data.evaluation });
                    get().addThinking(`📝 Evaluation: ${data.evaluation.score}/10`);
                });

                onSafe('evaluation_token', (data) => {
                    set({ currentTokens: get().currentTokens + data.token });
                });

                onSafe('interview_complete', (data) => {
                    set({
                        interviewActive: false,
                        interviewSummary: data.summary,
                        allEvaluations: data.evaluations,
                        appState: APP_STATES.COMPLETE
                    });
                    get().addThinking('🏁 Interview session complete');
                });

                set({ socket: newSocket });
            },

            disconnect: () => {
                const { socket } = get();
                if (socket) {
                    socket.disconnect();
                    // We keep the socket instance in state but disconnected?
                    // Or set to null? Setting to null ensures full reset on next connect.
                    set({ socket: null, isConnected: false });
                }
            },

            // Start career analysis
            startCareerAnalysis: (resumeBase64, jobTitle, company = '') => {
                console.log('🚀 Starting career analysis...', { jobTitle, company });

                // Clear old data before starting new analysis
                get().resetForNewAnalysis();

                const { socket } = get();
                if (!socket?.connected) {
                    console.log('⏳ Socket not connected, connecting first...');
                    get().connect();
                    // Wait slightly for connection, then emit
                    setTimeout(() => {
                        const s = get().socket;
                        if (s?.connected) {
                            console.log('✅ Socket connected, emitting start_career_analysis');
                            s.emit('start_career_analysis', {
                                resume: resumeBase64,  // Backend expects 'resume'
                                job_title: jobTitle,   // Backend expects 'job_title'
                                company: company
                            });
                        } else {
                            console.error('❌ Socket still not connected after timeout');
                        }
                    }, 500);
                    return;
                }

                console.log('✅ Socket already connected, emitting start_career_analysis');
                socket.emit('start_career_analysis', {
                    resume: resumeBase64,  // Backend expects 'resume'
                    job_title: jobTitle,   // Backend expects 'job_title'
                    company: company
                });
            },

            // Start interview mode
            startInterview: (params) => {
                const { socket } = get();
                if (!socket?.connected) return;
                socket.emit('start_interview', params);
            },

            // Send audio chunk
            sendAudioChunk: (audioBase64) => {
                const { socket } = get();
                if (!socket?.connected) return;
                socket.emit('user_audio_chunk', {
                    audio: audioBase64,
                    sample_rate: 16000,
                });
            },

            // Request a manual hint
            requestHint: () => {
                const { socket } = get();
                if (socket?.connected) {
                    socket.emit('request_hint');
                }
            },

            // Send text message (for testing)
            sendTextMessage: (text) => {
                const { socket } = get();
                if (!socket?.connected) return;
                socket.emit('text_message', { text });
                set((state) => ({
                    transcript: state.transcript + '\n\nYou: ' + text,
                }));
            },

            // Force transcribe
            forceTranscribe: () => {
                const { socket } = get();
                if (!socket?.connected) return;
                socket.emit('force_transcribe');
            },

            // Pop audio from queue
            popAudio: () => {
                const { ttsAudioQueue } = get();
                if (ttsAudioQueue.length === 0) return null;

                const [first, ...rest] = ttsAudioQueue;
                set({ ttsAudioQueue: rest });
                return first;
            },

            // Set recording state
            setRecording: (isRecording) => set({ isRecording }),

            // Add thinking log entry
            addThinking: (message) => {
                set((state) => ({
                    thinkingLog: [...state.thinkingLog.slice(-50), {
                        time: new Date().toLocaleTimeString(),
                        message,
                    }],
                }));
            },

            // Reset to idle (clears ALL data including persisted)
            reset: () => set({
                appState: APP_STATES.IDLE,
                mindmap: '',
                readinessScore: 0,
                skillMapping: null,
                bridgeRoles: [],
                jobRequirements: null,
                resumeData: null,
                transcript: '',
                lastTranscript: '',
                currentTokens: '',
                ttsAudioQueue: [],
                analysisProgress: '',
                targetRole: '',
                targetCompany: '',
                lastAnalysisTime: null,
                suggestedSessions: [],
                practicePlan: null,
                // Interview state
                interviewActive: false,
                currentQuestion: null,
                questionNumber: 0,
                totalQuestions: 0,
                answerEvaluation: null,
                coachingHint: null,
                allEvaluations: [],
                interviewSummary: null,
                thinkingLog: [],
            }),

            // Reset for new analysis (clears old CV/job data before new upload)
            resetForNewAnalysis: () => {
                console.log('🔄 Resetting for new analysis...');
                set({
                    appState: APP_STATES.ANALYZING,
                    mindmap: '',
                    readinessScore: 0,
                    skillMapping: null,
                    bridgeRoles: [],
                    jobRequirements: null,
                    resumeData: null,
                    analysisProgress: 'Starting new analysis...',
                    targetRole: '',
                    targetCompany: '',
                    lastAnalysisTime: null,
                    suggestedSessions: [],
                    practicePlan: null,
                    // Also clear any interview state
                    interviewActive: false,
                    currentQuestion: null,
                    questionNumber: 0,
                    answerEvaluation: null,
                    coachingHint: null,
                    allEvaluations: [],
                    interviewSummary: null,
                });
            },

            // Clear only interview data (keep analysis)
            clearInterview: () => set({
                transcript: '',
                lastTranscript: '',
                currentTokens: '',
                ttsAudioQueue: [],
                isRecording: false,
                interviewActive: false,
                currentQuestion: null,
                questionNumber: 0,
                answerEvaluation: null,
                coachingHint: null,
                allEvaluations: [],
                interviewSummary: null,
            }),

            // Alias for reset - used by SessionReport
            resetSession: () => get().reset(),

            // Mark onboarding as complete (login success)
            completeOnboarding: () => set({ onboardingComplete: true }),

            // Real Login Action
            login: (email, password) => {
                let { socket } = get();

                // Auto-connect if socket doesn't exist
                if (!socket) {
                    get().connect();
                    socket = get().socket;
                }

                if (!socket) return Promise.reject(new Error("Failed to create connection"));

                // Wait for connection if not connected
                return new Promise((resolve, reject) => {
                    const attemptLogin = () => {
                        socket.emit('login', { email, password });

                        const handleSuccess = (data) => {
                            socket.off('auth_success', handleSuccess);
                            socket.off('auth_error', handleError);
                            // Update state
                            set({
                                userId: data.user.user_id,
                                userEmail: data.user.email,
                                onboardingComplete: true
                            });
                            // Persist basic auth
                            localStorage.setItem('user_id', data.user.user_id);
                            localStorage.setItem('onboarding_complete', 'true');
                            resolve(data);
                        };

                        const handleError = (data) => {
                            socket.off('auth_success', handleSuccess);
                            socket.off('auth_error', handleError);
                            reject(new Error(data.error));
                        };

                        socket.on('auth_success', handleSuccess);
                        socket.on('auth_error', handleError);
                    };

                    if (socket.connected) {
                        attemptLogin();
                    } else {
                        // Wait for connection
                        const onConnect = () => {
                            socket.off('connect', onConnect);
                            socket.off('connect_error', onConnectError);
                            attemptLogin();
                        };
                        const onConnectError = (err) => {
                            socket.off('connect', onConnect);
                            socket.off('connect_error', onConnectError);
                            reject(new Error(`Connection failed: ${err.message}`));
                        };
                        socket.on('connect', onConnect);
                        socket.on('connect_error', onConnectError);
                        socket.connect();
                    }
                });
            },

            // Real Signup Action
            signup: (name, email, password) => {
                let { socket } = get();

                // Auto-connect if socket doesn't exist
                if (!socket) {
                    get().connect();
                    socket = get().socket;
                }

                if (!socket) return Promise.reject(new Error("Failed to create connection"));

                // Wait for connection if not connected
                return new Promise((resolve, reject) => {
                    const attemptSignup = () => {
                        socket.emit('signup', { username: name, email, password });

                        const handleSuccess = (data) => {
                            socket.off('auth_success', handleSuccess);
                            socket.off('auth_error', handleError);
                            // Update state
                            set({
                                userId: data.user.user_id,
                                userEmail: data.user.email,
                                onboardingComplete: true
                            });
                            // Persist basic auth
                            localStorage.setItem('user_id', data.user.user_id);
                            localStorage.setItem('onboarding_complete', 'true');
                            localStorage.setItem('user_name', data.user.username);
                            resolve(data);
                        };

                        const handleError = (data) => {
                            socket.off('auth_success', handleSuccess);
                            socket.off('auth_error', handleError);
                            reject(new Error(data.error));
                        };

                        socket.on('auth_success', handleSuccess);
                        socket.on('auth_error', handleError);
                    };

                    if (socket.connected) {
                        attemptSignup();
                    } else {
                        // Wait for connection
                        const onConnect = () => {
                            socket.off('connect', onConnect);
                            socket.off('connect_error', onConnectError);
                            attemptSignup();
                        };
                        const onConnectError = (err) => {
                            socket.off('connect', onConnect);
                            socket.off('connect_error', onConnectError);
                            reject(new Error(`Connection failed: ${err.message}`));
                        };
                        socket.on('connect', onConnect);
                        socket.on('connect_error', onConnectError);
                        socket.connect();
                    }
                });
            },

            // Full Logout Action
            logout: () => {
                console.log('👋 Logging out...');
                const { socket } = get();

                // 1. Disconnect socket
                if (socket) {
                    socket.disconnect();
                }

                // 2. Clear LocalStorage
                localStorage.removeItem('user_id');
                localStorage.removeItem('onboarding_complete');
                localStorage.removeItem('user_name');
                localStorage.removeItem('interview-agent-storage'); // Clear zustand persist

                // 3. Reset Store State completely
                set({
                    userId: null,
                    userEmail: null,
                    socket: null,
                    isConnected: false,
                    onboardingComplete: false,
                    appState: APP_STATES.IDLE,

                    // Clear persisted analysis
                    mindmap: '',
                    readinessScore: 0,
                    skillMapping: null,
                    bridgeRoles: [],
                    jobRequirements: null,
                    resumeData: null,
                    analysisProgress: '',
                    targetRole: '',
                    targetCompany: '',
                    focusAreas: [],
                    lastAnalysisTime: null,

                    // Clear interview state
                    transcript: '',
                    lastTranscript: '',
                    currentTokens: '',
                    ttsAudioQueue: [],
                    isRecording: false,
                    interviewActive: false,
                    currentQuestion: null,
                    questionNumber: 0,
                    totalQuestions: 0,
                    answerEvaluation: null,
                    coachingHint: null,
                    allEvaluations: [],
                    interviewSummary: null,
                    thinkingLog: []
                });

                console.log('✅ Logout complete');
            },

            // ============== Interview Practice Actions ==============

            // Start interview with context from analysis
            startInterviewPractice: (mode = 'practice') => {
                const { skillMapping, jobRequirements, readinessScore, focusAreas } = get();

                const { socket } = get();
                if (!socket?.connected) {
                    console.error('Socket not connected');
                    return;
                }

                const skillGaps = skillMapping?.missing || [];
                const jobTitle = jobRequirements?.job_title || 'Software Engineer';

                socket.emit('start_interview', {
                    job_title: jobTitle,
                    skill_gaps: skillGaps,
                    focus_areas: focusAreas,
                    readiness_score: readinessScore,
                    mode: mode
                });

                set({ appState: APP_STATES.INTERVIEWING });
                get().addThinking(`🎙️ Starting ${mode} mode...`);
            },

            // Submit answer to current question
            submitInterviewAnswer: (answerText, durationSeconds) => {
                const { socket } = get();
                if (!socket?.connected) return;

                socket.emit('submit_interview_answer', {
                    answer: answerText,
                    duration_seconds: durationSeconds
                });
            },

            // Toggle coaching mode
            toggleCoaching: (enabled) => {
                const { socket } = get();
                if (!socket?.connected) return;

                socket.emit('toggle_coaching', { enabled });
                set({ coachingEnabled: enabled });
            },

            // Skip current question
            skipQuestion: () => {
                const { socket } = get();
                if (!socket?.connected) return;
                socket.emit('skip_question', {});
            },

            // End interview early
            endInterviewEarly: () => {
                const { socket } = get();
                if (!socket?.connected) return;
                socket.emit('end_interview_early', {});
            },

            // End interview and return to analysis view
            endInterview: () => {
                const { socket } = get();
                if (socket?.connected) {
                    socket.emit('end_interview_early', {});
                }
                // Immediately set app state to go back to map view
                set({
                    interviewActive: false,
                    appState: APP_STATES.MAP_READY
                });
            },

            // Audio Handling
            submitAudio: (base64Audio) => {
                const { socket } = get();
                if (!socket?.connected) return;
                set({ transcript: 'Processing speech...' }); // Removed aiThinking
                socket.emit('submit_audio', {
                    audio: base64Audio,
                    sample_rate: 16000
                });
            },

            // Check if user is struggling (called periodically)
            checkStruggle: (transcript, silenceDuration) => {
                const { socket } = get();
                if (!socket?.connected || !get().coachingEnabled) return;

                socket.emit('check_struggle', {
                    transcript,
                    silence_duration: silenceDuration
                });
            },

            // Clear current coaching hint
            clearCoachingHint: () => set({ coachingHint: null }),

            // Set target job role
            setTargetJob: (job) => set({ targetRole: job }),

            // Set target company
            setTargetCompany: (company) => set({ targetCompany: company }),

            // Set focus areas
            setFocusAreas: (areas) => set({ focusAreas: areas }),

            // Save user preferences to backend
            savePreferences: (preferences) => {
                const { socket } = get();
                if (socket?.connected) {
                    socket.emit('save_preferences', preferences);
                }
            },

            // Load user preferences from backend
            loadPreferences: () => {
                const { socket } = get();
                if (socket?.connected) {
                    socket.emit('get_preferences');
                }
            },

            // Load interview history from backend
            loadInterviewHistory: () => {
                const { socket } = get();
                if (socket?.connected) {
                    socket.emit('get_interview_history', { limit: 20 });
                }
            },
        }),

        {
            name: 'interview-agent-storage', // localStorage key
            partialize: (state) => ({
                // Only persist these fields:
                userId: state.userId,
                appState: state.appState,
                onboardingComplete: state.onboardingComplete,
                mindmap: state.mindmap,
                readinessScore: state.readinessScore,
                skillMapping: state.skillMapping,
                bridgeRoles: state.bridgeRoles,
                jobRequirements: state.jobRequirements,
                resumeData: state.resumeData,
                targetRole: state.targetRole,
                targetCompany: state.targetCompany,
                focusAreas: state.focusAreas,
                lastAnalysisTime: state.lastAnalysisTime,
                suggestedSessions: state.suggestedSessions,
                practicePlan: state.practicePlan,
            }),
        }
    )
);

// Selector to convert isConnected boolean to connectionStatus string
// This is used by Layout component to show connection indicator
export const useConnectionStatus = () => {
    return useInterviewStore((state) =>
        state.isConnected ? 'connected' : 'disconnected'
    );
};

export { APP_STATES };
export default useInterviewStore;
