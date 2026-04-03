/**
 * Zustand Store for BeePrepared
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

const formatInterviewLaunchStatus = (stage) => {
    const normalized = String(stage || '').trim();
    if (!normalized) return '';

    const knownStages = {
        generating_questions: 'Generating interview questions...',
        questions_ready: 'Questions ready. Starting interview...',
    };

    return knownStages[normalized] || normalized;
};

const ALLOWED_PIPER_STYLES = new Set(['interviewer', 'balanced', 'fast']);
const normalizePiperStyle = (style, fallback = 'interviewer') => {
    const fallbackNormalized = ALLOWED_PIPER_STYLES.has(String(fallback || '').trim().toLowerCase())
        ? String(fallback || '').trim().toLowerCase()
        : 'interviewer';
    const normalized = String(style || '').trim().toLowerCase();
    return ALLOWED_PIPER_STYLES.has(normalized) ? normalized : fallbackNormalized;
};

const ALLOWED_TTS_PROVIDERS = new Set(['piper', 'qwen3_tts', 'qwen3_tts_mlx']);
const normalizeTtsProvider = (provider, fallback = 'piper') => {
    const normalizeLegacy = (value) => {
        const normalizedValue = String(value || '').trim().toLowerCase();
        return normalizedValue === 'qwen3_tts_mlx' ? 'qwen3_tts' : normalizedValue;
    };
    const fallbackNormalized = ALLOWED_TTS_PROVIDERS.has(String(fallback || '').trim().toLowerCase())
        ? normalizeLegacy(fallback)
        : 'piper';
    const normalized = normalizeLegacy(provider);
    return ALLOWED_TTS_PROVIDERS.has(normalized) ? normalized : fallbackNormalized;
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
            sessionToken: null, // Server-issued auth token

            // App state
            appState: APP_STATES.IDLE,
            onboardingComplete: false, // Tracks if user has logged in/completed onboarding
            darkMode: false,

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
            jobDescription: '',
            questionCountOverride: null,
            interviewerPersona: 'friendly',
            piperStyle: 'interviewer',
            ttsProvider: 'piper',
            evaluationThresholds: {},
            recordingThresholds: {},
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
            interviewFeedbackTiming: 'end_only', // 'end_only' | 'live'
            currentQuestion: null,
            questionNumber: 0,
            totalQuestions: 0,
            answerEvaluation: null,
            coachingEnabled: false,
            coachingHint: null,
            allEvaluations: [],
            interviewSummary: null,
            answerSubmitPending: false,
            generatingReport: false,

            // Thinking terminal (not persisted)
            thinkingLog: [],

            // History (not persisted)
            interviewHistory: [],
            historyLoading: false,
            deletingSessionIds: {},
            selectedSession: null,
            selectedSessionLoading: false,
            currentSessionId: null,
            retryAttemptsByQuestion: {},
            retrySubmitting: {},
            retryErrors: {},

            // ============== Actions ==============
            toggleDarkMode: () => set((state) => ({ darkMode: !state.darkMode })),
            setDarkMode: (enabled) => set({ darkMode: Boolean(enabled) }),

            // Connect to Socket.IO Server
            connect: () => {
                let { socket, userId, sessionToken } = get();
                // Prevent multiple socket instances - check if socket exists AND is either connected or connecting
                if (socket && (socket.connected || socket.io.engine)) return;

                // Clean up any existing disconnected socket
                if (socket && !socket.connected) {
                    console.log('🧹 Cleaning up disconnected socket');
                    socket.removeAllListeners();
                    socket.close();
                    set({ socket: null });
                }

                // Bootstrap userId/sessionToken from localStorage if not in store (bridges legacy flows)
                if (!userId || userId === 'anonymous') {
                    const fallbackId = localStorage.getItem('user_id');
                    if (fallbackId && fallbackId !== 'anonymous') {
                        console.log('🔌 Bootstrapped userId from localStorage:', fallbackId);
                        set({ userId: fallbackId });
                        userId = fallbackId;
                    }
                }

                if (!sessionToken) {
                    const fallbackToken = localStorage.getItem('session_token');
                    if (fallbackToken) {
                        console.log('🔐 Bootstrapped session token from localStorage');
                        set({ sessionToken: fallbackToken });
                        sessionToken = fallbackToken;
                    }
                }

                // Prevent stale user binding when no valid token is available.
                if (!sessionToken && userId && userId !== 'anonymous') {
                    set({ userId: null, onboardingComplete: false });
                    userId = null;
                }

                // Direct backend socket by default for local dev reliability.
                // Override with VITE_SOCKET_URL when needed.
                const socketUrl = (import.meta.env.VITE_SOCKET_URL || '').trim();
                const socketEndpoint = socketUrl || '';
                const newSocket = io(socketEndpoint, {
                    path: '/socket.io',
                    transports: ['websocket'],
                    upgrade: false,
                    timeout: 10000,
                    auth: sessionToken ? { session_token: sessionToken } : {},
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
                    get().addThinking('🔌 Connected to BeePrepared');

                    // Restore authenticated session if we have a token
                    const { sessionToken } = get();
                    if (sessionToken) {
                        get().addThinking('🔄 Restoring authenticated session...');
                        newSocket.emit('restore_session', { session_token: sessionToken });
                    }
                });

                newSocket.on('connected', (data) => {
                    if (data.authenticated && data.user_id && data.user_id !== 'anonymous') {
                        set({ userId: data.user_id });
                        get().addThinking(`👤 User ID: ${data.user_id}`);
                    }
                });

                newSocket.on('auth_success', (data) => {
                    if (data.user?.user_id) {
                        const prefs = data.preferences || {};
                        const nextState = {
                            userId: data.user.user_id,
                            userEmail: data.user.email || get().userEmail,
                            onboardingComplete: true,
                            targetRole: prefs.target_role || '',
                            targetCompany: prefs.target_company || '',
                            jobDescription: prefs.job_description || '',
                            questionCountOverride:
                                prefs.question_count_override !== undefined && prefs.question_count_override !== null
                                    ? Number(prefs.question_count_override)
                                    : null,
                            interviewerPersona: String(prefs.interviewer_persona || 'friendly').trim().toLowerCase() || 'friendly',
                            piperStyle: normalizePiperStyle(prefs.piper_style, 'interviewer'),
                            ttsProvider: normalizeTtsProvider(prefs.tts_provider, 'piper'),
                            evaluationThresholds: (prefs.evaluation_thresholds && typeof prefs.evaluation_thresholds === 'object') ? prefs.evaluation_thresholds : {},
                            recordingThresholds: (prefs.recording_thresholds && typeof prefs.recording_thresholds === 'object') ? prefs.recording_thresholds : {},
                            focusAreas: prefs.focus_areas || [],
                            // Clear prior-user analysis/session state; backend will emit career_analysis if one exists.
                            mindmap: '',
                            readinessScore: 0,
                            skillMapping: null,
                            bridgeRoles: [],
                            jobRequirements: null,
                            resumeData: null,
                            suggestedSessions: [],
                            practicePlan: null,
                            lastAnalysisTime: null,
                            analysisProgress: '',
                            appState: APP_STATES.IDLE,
                            interviewActive: false,
                            currentQuestion: null,
                            questionNumber: 0,
                            totalQuestions: 0,
                            answerEvaluation: null,
                            coachingHint: null,
                            allEvaluations: [],
                            interviewSummary: null,
                            currentSessionId: null,
                            retryAttemptsByQuestion: {},
                            retrySubmitting: {},
                            retryErrors: {},
                            interviewHistory: [],
                            selectedSession: null,
                        };
                        if (data.session_token) {
                            nextState.sessionToken = data.session_token;
                            localStorage.setItem('session_token', data.session_token);
                        }
                        localStorage.setItem('user_id', data.user.user_id);
                        localStorage.setItem('onboarding_complete', 'true');
                        set(nextState);
                        get().addThinking(`✅ Authenticated as ${data.user.email}`);
                    }
                });

                newSocket.on('auth_error', (data) => {
                    const msg = data?.error || 'Authentication error';
                    if (msg.toLowerCase().includes('token')) {
                        localStorage.removeItem('session_token');
                        localStorage.removeItem('user_id');
                        localStorage.removeItem('onboarding_complete');
                        set({
                            sessionToken: null,
                            userId: null,
                            userEmail: null,
                            onboardingComplete: false,
                            historyLoading: false,
                            deletingSessionIds: {},
                            selectedSessionLoading: false,
                        });
                    } else {
                        // Ensure UI can recover from protected-event auth failures.
                        set({ historyLoading: false, deletingSessionIds: {}, selectedSessionLoading: false });
                    }
                    get().addThinking(`❌ ${msg}`);
                });

                newSocket.on('session_restored', (data) => {
                    get().addThinking(`✅ Session restored for ${data.user.email}`);
                    const prefs = data.preferences || {};
                    const nextState = {
                        userId: data.user?.user_id || get().userId,
                        userEmail: data.user?.email || get().userEmail,
                        onboardingComplete: true,
                    };
                    if (data.session_token) {
                        nextState.sessionToken = data.session_token;
                        localStorage.setItem('session_token', data.session_token);
                    }
                    if (data.user?.user_id) {
                        localStorage.setItem('user_id', data.user.user_id);
                    }
                    localStorage.setItem('onboarding_complete', 'true');

                    // If an interview is active, only update user/prefs — do NOT
                    // reset interview state, which would wipe the current question.
                    const { appState: currentAppState, interviewActive: currentlyInterviewing } = get();
                    const isInInterview = currentlyInterviewing || currentAppState === APP_STATES.INTERVIEWING;

                    if (isInInterview) {
                        set({
                            ...nextState,
                            interviewerPersona: String(prefs.interviewer_persona || 'friendly').trim().toLowerCase() || 'friendly',
                            piperStyle: normalizePiperStyle(prefs.piper_style, get().piperStyle || 'interviewer'),
                            ttsProvider: normalizeTtsProvider(prefs.tts_provider, get().ttsProvider || 'piper'),
                            recordingThresholds: (prefs.recording_thresholds && typeof prefs.recording_thresholds === 'object') ? prefs.recording_thresholds : {},
                        });
                        get().addThinking('🔄 Reconnected — interview state preserved');
                        return;
                    }

                    set({
                        ...nextState,
                        targetRole: prefs.target_role || '',
                        targetCompany: prefs.target_company || '',
                        jobDescription: prefs.job_description || '',
                        questionCountOverride:
                            prefs.question_count_override !== undefined && prefs.question_count_override !== null
                                ? Number(prefs.question_count_override)
                                : null,
                        interviewerPersona: String(prefs.interviewer_persona || 'friendly').trim().toLowerCase() || 'friendly',
                        piperStyle: normalizePiperStyle(prefs.piper_style, get().piperStyle || 'interviewer'),
                        ttsProvider: normalizeTtsProvider(prefs.tts_provider, get().ttsProvider || 'piper'),
                        evaluationThresholds: (prefs.evaluation_thresholds && typeof prefs.evaluation_thresholds === 'object') ? prefs.evaluation_thresholds : {},
                        recordingThresholds: (prefs.recording_thresholds && typeof prefs.recording_thresholds === 'object') ? prefs.recording_thresholds : {},
                        focusAreas: prefs.focus_areas || [],
                        // Reset analysis/session snapshot; server may repopulate via career_analysis.
                        mindmap: '',
                        readinessScore: 0,
                        skillMapping: null,
                        bridgeRoles: [],
                        jobRequirements: null,
                        resumeData: null,
                        suggestedSessions: [],
                        practicePlan: null,
                        lastAnalysisTime: null,
                        analysisProgress: '',
                        appState: APP_STATES.IDLE,
                        interviewActive: false,
                        currentQuestion: null,
                        questionNumber: 0,
                        totalQuestions: 0,
                        answerEvaluation: null,
                        coachingHint: null,
                        allEvaluations: [],
                        interviewSummary: null,
                        currentSessionId: null,
                        retryAttemptsByQuestion: {},
                        retrySubmitting: {},
                        retryErrors: {},
                        interviewHistory: [],
                        selectedSession: null,
                    });
                });

                newSocket.on('disconnect', () => {
                    set({
                        isConnected: false,
                        historyLoading: false,
                        deletingSessionIds: {},
                        selectedSessionLoading: false,
                    });
                    get().addThinking('🔌 Disconnected from server');
                });

                newSocket.on('connect_error', (error) => {
                    set({
                        connectionError: error.message,
                        historyLoading: false,
                        deletingSessionIds: {},
                        selectedSessionLoading: false,
                    });
                    get().addThinking(`❌ Connection error: ${error.message}`);
                });

                // Career Analysis events
                onSafe('analysis_progress', (data) => {
                    set({ analysisProgress: data.message });
                    get().addThinking(`📊 ${data.message}`);
                });

                onSafe('status', (data) => {
                    const stage = String(data?.stage || '').trim();
                    if (!stage) return;

                    const isInterviewLaunchStage =
                        stage === 'generating_questions' ||
                        stage === 'questions_ready' ||
                        stage.startsWith('Generating ') ||
                        stage.startsWith('✅ Generated');

                    if (!isInterviewLaunchStage) return;

                    const friendlyStage = formatInterviewLaunchStatus(stage);
                    set((state) => {
                        if (state.interviewActive) return state;
                        return {
                            ...state,
                            appState: APP_STATES.ANALYZING,
                            analysisProgress: friendlyStage,
                        };
                    });
                    get().addThinking(`⏳ ${friendlyStage}`);
                });

                // Handle career analysis (both fresh and loaded from DB)
                onSafe('career_analysis', (data) => {
                    const analysis = data.analysis;
                    const { appState: currentAppState, interviewActive: currentlyInterviewing } = get();
                    const isInInterview = currentlyInterviewing || currentAppState === APP_STATES.INTERVIEWING;

                    if (analysis) {
                        const topLevelSkillGaps = Array.isArray(analysis.skill_gaps) ? analysis.skill_gaps : [];
                        const analysisSkillMapping = analysis.analysis_data?.skill_mapping;
                        const mergedSkillMapping = topLevelSkillGaps.length > 0
                            ? {
                                ...(analysisSkillMapping || {}),
                                missing: topLevelSkillGaps,
                            }
                            : analysisSkillMapping;
                        get().addThinking('✅ Career analysis loaded');

                        // During an active interview, update analysis data silently
                        // but do NOT change appState — that would kill the interview.
                        const nextState = {
                            mindmap: analysis.analysis_data?.mindmap || analysis.analysis_data?.mindmap_code,
                            readinessScore: analysis.readiness_score,
                            skillMapping: mergedSkillMapping,
                            bridgeRoles: analysis.bridge_roles,
                            jobRequirements: analysis.analysis_data?.job_requirements,
                            resumeData: analysis.analysis_data?.resume_data,
                            suggestedSessions: analysis.suggested_sessions || analysis.analysis_data?.suggested_sessions || [],
                            practicePlan: analysis.practice_plan || analysis.analysis_data?.practice_plan || null,
                            targetRole: analysis.job_title,
                            targetCompany: analysis.company,
                            jobDescription: analysis.job_description || analysis.analysis_data?.job_description || get().jobDescription || '',
                            lastAnalysisTime: analysis.created_at || Date.now(),
                            analysisProgress: 'Analysis Complete!',
                        };
                        if (!isInInterview) {
                            nextState.appState = APP_STATES.MAP_READY;
                        }
                        set(nextState);
                    } else {
                        set((state) => ({
                            mindmap: '',
                            readinessScore: 0,
                            skillMapping: null,
                            bridgeRoles: [],
                            jobRequirements: null,
                            resumeData: null,
                            suggestedSessions: [],
                            practicePlan: null,
                            lastAnalysisTime: null,
                            analysisProgress: '',
                            appState: state.interviewActive ? state.appState : APP_STATES.IDLE,
                        }));
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
                        currentSessionId: data.session_id || null,
                        totalQuestions: data.total_questions,
                        currentQuestionIndex: 0,
                        interviewMode: data.mode || 'practice',
                        interviewFeedbackTiming: data.feedback_timing || 'end_only',
                        interviewerPersona: String(data.interviewer_persona || get().interviewerPersona || 'friendly').trim().toLowerCase() || 'friendly',
                        piperStyle: normalizePiperStyle(data.piper_style, get().piperStyle || 'interviewer'),
                        ttsProvider: normalizeTtsProvider(data.tts_provider, get().ttsProvider || 'piper'),
                        coachingEnabled: !!data.coaching_enabled,
                        appState: APP_STATES.INTERVIEWING,
                        analysisProgress: '',
                        answerSubmitPending: false,
                        retryAttemptsByQuestion: {},
                        retrySubmitting: {},
                        retryErrors: {},
                    });
                });

                onSafe('interview_question', (data) => {
                    set({
                        currentQuestion: data.question,
                        questionNumber: data.question_number,
                        totalQuestions: data.total_questions || get().totalQuestions,
                        transcript: '',
                        answerEvaluation: null,
                        coachingHint: null,
                        answerSubmitPending: false,
                        ttsAudioQueue: [],
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

                onSafe('coaching_toggled', (data) => {
                    const enabled = !!data?.enabled;
                    set((state) => ({
                        coachingEnabled: enabled,
                        coachingHint: enabled ? state.coachingHint : null,
                    }));
                });

                onSafe('evaluation_token', (data) => {
                    set({ currentTokens: get().currentTokens + data.token });
                });

                onSafe('generating_report', () => {
                    set({
                        generatingReport: true,
                        answerSubmitPending: false,
                    });
                    get().addThinking('📊 Generating your interview report…');
                });

                onSafe('interview_complete', (data) => {
                    set({
                        interviewActive: false,
                        generatingReport: false,
                        currentSessionId: data.session_id || get().currentSessionId,
                        interviewSummary: data.summary,
                        allEvaluations: data.evaluations,
                        appState: APP_STATES.COMPLETE,
                        answerSubmitPending: false,
                    });
                    get().addThinking('🏁 Interview session complete');
                });

                onSafe('interview_error', (data) => {
                    set((state) => {
                        if (state.interviewActive) {
                            return { answerSubmitPending: false };
                        }

                        const hasAnalysisData = Boolean(
                            state.mindmap ||
                            state.skillMapping ||
                            state.practicePlan ||
                            (Array.isArray(state.suggestedSessions) && state.suggestedSessions.length) ||
                            Number(state.readinessScore) > 0
                        );

                        return {
                            answerSubmitPending: false,
                            analysisProgress: `Error: ${data?.error || 'Unable to start interview'}`,
                            appState: hasAnalysisData ? APP_STATES.MAP_READY : APP_STATES.IDLE,
                        };
                    });
                    if (data?.error) get().addThinking(`❌ ${data.error}`);
                });

                // TTS audio for interview questions
                onSafe('tts_audio', (data) => {
                    console.log('[TTS] tts_audio received, has audio:', !!data.audio, 'audio length:', data.audio?.length || 0, 'question_index:', data.question_index);
                    if (data.audio) {
                        const qIdx = Number.isInteger(data.question_index)
                            ? Number(data.question_index)
                            : null;
                        // Ignore stale question audio that arrives for an old question.
                        if (qIdx !== null) {
                            const currentQ = Number(get().questionNumber || 0);
                            console.log('[TTS] stale check: qIdx=', qIdx, 'currentQ=', currentQ, 'pass=', !(currentQ > 0 && qIdx !== (currentQ - 1)));
                            if (currentQ > 0 && qIdx !== (currentQ - 1)) {
                                console.log('[TTS] DROPPED stale audio');
                                return;
                            }
                        }
                        set((state) => ({
                            ttsAudioQueue: [...state.ttsAudioQueue, data.audio]
                        }));
                        console.log('[TTS] Audio queued, queue length:', get().ttsAudioQueue.length);
                        get().addThinking('🔊 Playing interviewer audio');
                    }
                });

                onSafe('tts_error', (data) => {
                    const err = data?.error || 'TTS unavailable';
                    get().addThinking(`🔇 ${err}`);
                });

                // History events
                onSafe('interview_history', (data) => {
                    set({ interviewHistory: data.history || [], historyLoading: false });
                    get().addThinking(`📚 Loaded ${(data.history || []).length} past sessions`);
                });

                onSafe('session_deleted', (data) => {
                    const deletedId = String(data?.session_id || '').trim();
                    set((state) => {
                        const nextDeleting = { ...state.deletingSessionIds };
                        if (deletedId) delete nextDeleting[deletedId];
                        return {
                            historyLoading: false,
                            deletingSessionIds: nextDeleting,
                            selectedSession:
                                deletedId && state.selectedSession?.session_id === deletedId
                                    ? null
                                    : state.selectedSession,
                            currentSessionId:
                                deletedId && state.currentSessionId === deletedId
                                    ? null
                                    : state.currentSessionId,
                        };
                    });
                    get().addThinking('🗑️ Session deleted');
                });

                onSafe('session_delete_error', (data) => {
                    const failedId = String(data?.session_id || '').trim();
                    set((state) => {
                        const nextDeleting = { ...state.deletingSessionIds };
                        if (failedId) {
                            delete nextDeleting[failedId];
                        } else {
                            for (const key of Object.keys(nextDeleting)) delete nextDeleting[key];
                        }
                        return {
                            historyLoading: false,
                            deletingSessionIds: nextDeleting,
                        };
                    });
                    get().addThinking(`❌ ${data?.error || 'Failed to delete session'}`);
                });

                onSafe('session_details', (data) => {
                    set({ selectedSession: data.session, selectedSessionLoading: false });
                    get().addThinking(`📄 Loaded session details`);
                });

                onSafe('session_details_error', (data) => {
                    set({ selectedSessionLoading: false });
                    get().addThinking(`❌ ${data.error}`);
                });

                onSafe('workspace_reset', () => {
                    set((state) => ({
                        mindmap: '',
                        readinessScore: 0,
                        skillMapping: null,
                        bridgeRoles: [],
                        jobRequirements: null,
                        resumeData: null,
                        analysisProgress: '',
                        suggestedSessions: [],
                        practicePlan: null,
                        appState: state.interviewActive ? state.appState : APP_STATES.IDLE,
                    }));
                    get().addThinking('🧹 Workspace reset complete');
                });

                onSafe('configuration_cleared', () => {
                    set({
                        targetRole: '',
                        targetCompany: '',
                        jobDescription: '',
                        questionCountOverride: null,
                        interviewerPersona: 'friendly',
                        piperStyle: 'interviewer',
                        ttsProvider: 'piper',
                        focusAreas: [],
                        lastAnalysisTime: null,
                        mindmap: '',
                        readinessScore: 0,
                        skillMapping: null,
                        bridgeRoles: [],
                        jobRequirements: null,
                        resumeData: null,
                        suggestedSessions: [],
                        practicePlan: null,
                        analysisProgress: '',
                        appState: APP_STATES.IDLE,
                    });
                    get().addThinking('🧹 Configuration cleared');
                });

                onSafe('history_deleted', () => {
                    set({
                        interviewHistory: [],
                        historyLoading: false,
                        deletingSessionIds: {},
                        selectedSession: null,
                        selectedSessionLoading: false,
                    });
                    get().addThinking('🗑️ Interview history deleted');
                });

                onSafe('all_data_reset', () => {
                    set({
                        interviewHistory: [],
                        historyLoading: false,
                        deletingSessionIds: {},
                        selectedSession: null,
                        selectedSessionLoading: false,
                        currentSessionId: null,
                        retryAttemptsByQuestion: {},
                        retrySubmitting: {},
                        retryErrors: {},
                        targetRole: '',
                        targetCompany: '',
                        jobDescription: '',
                        questionCountOverride: null,
                        interviewerPersona: 'friendly',
                        piperStyle: 'interviewer',
                        ttsProvider: 'piper',
                        focusAreas: [],
                        lastAnalysisTime: null,
                        mindmap: '',
                        readinessScore: 0,
                        skillMapping: null,
                        bridgeRoles: [],
                        jobRequirements: null,
                        resumeData: null,
                        suggestedSessions: [],
                        practicePlan: null,
                        analysisProgress: '',
                        appState: APP_STATES.IDLE,
                    });
                    get().addThinking('♻️ All data reset complete');
                });

                onSafe('user_preferences', (data) => {
                    const prefs = data?.preferences || {};
                    set({
                        targetRole: prefs.target_role || '',
                        targetCompany: prefs.target_company || '',
                        jobDescription: prefs.job_description || '',
                        questionCountOverride:
                            prefs.question_count_override !== undefined && prefs.question_count_override !== null
                                ? Number(prefs.question_count_override)
                                : null,
                        interviewerPersona: String(prefs.interviewer_persona || 'friendly').trim().toLowerCase() || 'friendly',
                        piperStyle: normalizePiperStyle(prefs.piper_style, get().piperStyle || 'interviewer'),
                        ttsProvider: normalizeTtsProvider(prefs.tts_provider, get().ttsProvider || 'piper'),
                        evaluationThresholds: (prefs.evaluation_thresholds && typeof prefs.evaluation_thresholds === 'object') ? prefs.evaluation_thresholds : {},
                        recordingThresholds: (prefs.recording_thresholds && typeof prefs.recording_thresholds === 'object') ? prefs.recording_thresholds : {},
                        focusAreas: prefs.focus_areas || [],
                    });
                });

                onSafe('retry_attempts', (data) => {
                    const sessionId = data?.session_id;
                    const questionNumber = Number(data?.question_number);
                    if (!sessionId || !questionNumber) return;
                    const key = `${sessionId}:${questionNumber}`;
                    set((state) => ({
                        retryAttemptsByQuestion: {
                            ...state.retryAttemptsByQuestion,
                            [key]: Array.isArray(data.attempts) ? data.attempts : [],
                        },
                    }));
                });

                onSafe('retry_evaluated', (data) => {
                    const sessionId = data?.session_id;
                    const questionNumber = Number(data?.question_number);
                    if (!sessionId || !questionNumber) return;
                    const key = `${sessionId}:${questionNumber}`;
                    const attempt = data?.attempt;
                    const promoted = Boolean(data?.promoted_to_primary);
                    set((state) => {
                        const currentAttempts = state.retryAttemptsByQuestion[key] || [];
                        const nextAttempts = attempt
                            ? [...currentAttempts.filter((a) => a?.retry_id !== attempt.retry_id), attempt]
                            : currentAttempts;
                        const nextEvaluations = Array.isArray(state.allEvaluations)
                            ? [...state.allEvaluations]
                            : [];
                        const qIndex = questionNumber - 1;
                        if (
                            promoted &&
                            attempt &&
                            qIndex >= 0 &&
                            qIndex < nextEvaluations.length &&
                            nextEvaluations[qIndex]
                        ) {
                            nextEvaluations[qIndex] = {
                                ...nextEvaluations[qIndex],
                                answer: attempt.answer_text || nextEvaluations[qIndex].answer,
                                evaluation: attempt.evaluation || nextEvaluations[qIndex].evaluation,
                            };
                        }

                        const nextSummary = state.interviewSummary
                            ? { ...state.interviewSummary }
                            : null;
                        if (nextSummary && typeof data?.session_average_score === 'number') {
                            nextSummary.average_score = data.session_average_score;
                        }

                        return {
                            retryAttemptsByQuestion: {
                                ...state.retryAttemptsByQuestion,
                                [key]: nextAttempts.sort(
                                    (a, b) => Number(a?.attempt_number || 0) - Number(b?.attempt_number || 0)
                                ),
                            },
                            allEvaluations: nextEvaluations,
                            interviewSummary: nextSummary,
                            retrySubmitting: { ...state.retrySubmitting, [key]: false },
                            retryErrors: { ...state.retryErrors, [key]: '' },
                        };
                    });
                });

                onSafe('retry_error', (data) => {
                    const sessionId = data?.session_id;
                    const questionNumber = Number(data?.question_number);
                    const error = data?.error || 'Retry request failed';
                    if (!sessionId || !questionNumber) {
                        get().addThinking(`❌ ${error}`);
                        return;
                    }
                    const key = `${sessionId}:${questionNumber}`;
                    set((state) => ({
                        retrySubmitting: { ...state.retrySubmitting, [key]: false },
                        retryErrors: { ...state.retryErrors, [key]: error },
                    }));
                    get().addThinking(`❌ ${error}`);
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
            startCareerAnalysis: (resumeBase64, jobTitle, company = '', jobDescription = '') => {
                console.log('🚀 Starting career analysis...', { jobTitle, company });

                // Clear old data before starting new analysis
                get().resetForNewAnalysis();

                // Store job description in state for interview use
                set({ jobDescription: jobDescription || '' });

                const payload = {
                    resume: resumeBase64,
                    job_title: jobTitle,
                    company: company,
                    job_description: jobDescription
                };

                const emitStart = () => {
                    const s = get().socket;
                    if (!s?.connected) return false;
                    s.emit('start_career_analysis', payload);
                    return true;
                };

                if (emitStart()) {
                    console.log('✅ Socket connected, emitting start_career_analysis');
                    return;
                }

                console.log('⏳ Socket not connected, connecting and retrying...');
                get().connect();
                const startedAt = Date.now();
                const maxWaitMs = 8000;

                const waitForSocket = () => {
                    if (emitStart()) {
                        console.log('✅ Socket connected, emitting start_career_analysis');
                        return;
                    }
                    if (Date.now() - startedAt >= maxWaitMs) {
                        console.error('❌ Failed to start analysis: socket connection timeout');
                        set({
                            analysisProgress: 'Error: Unable to connect to server. Please try again.',
                            appState: APP_STATES.IDLE
                        });
                        get().addThinking('❌ Failed to start analysis: connection timeout');
                        return;
                    }
                    setTimeout(waitForSocket, 250);
                };

                waitForSocket();
            },

            // Start interview mode
            startInterview: (params) => {
                const { socket } = get();
                if (!socket?.connected) return;
                set({
                    appState: APP_STATES.ANALYZING,
                    analysisProgress: 'Generating interview questions...',
                    interviewActive: false,
                    currentQuestion: null,
                    questionNumber: 0,
                    totalQuestions: 0,
                    answerEvaluation: null,
                    coachingHint: null,
                    answerSubmitPending: false,
                    currentSessionId: null,
                    ttsAudioQueue: [],
                });
                get().addThinking('⏳ Generating interview questions...');
                socket.emit('start_interview', params);
            },

            // Send audio chunk
            sendAudioChunk: (audioBase64, sampleRate = 16000) => {
                const { socket } = get();
                if (!socket?.connected) return;
                socket.emit('user_audio_chunk', {
                    audio: audioBase64,
                    sample_rate: sampleRate,
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

            // Set recording state and sync to server so backend can gate audio chunks.
            setRecording: (isRecording) => {
                const { socket } = get();
                if (socket?.connected) {
                    socket.emit('set_recording_state', { recording: !!isRecording });
                }
                set({ isRecording: !!isRecording });
            },

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
                jobDescription: '',
                questionCountOverride: null,
                interviewerPersona: 'friendly',
                piperStyle: 'interviewer',
                ttsProvider: 'piper',
                evaluationThresholds: {},
                recordingThresholds: {},
                lastAnalysisTime: null,
                suggestedSessions: [],
                practicePlan: null,
                // Interview state
                interviewActive: false,
                interviewMode: 'practice',
                interviewFeedbackTiming: 'end_only',
                currentQuestion: null,
                questionNumber: 0,
                totalQuestions: 0,
                answerEvaluation: null,
                coachingEnabled: false,
                coachingHint: null,
                allEvaluations: [],
                interviewSummary: null,
                answerSubmitPending: false,
                selectedSession: null,
                currentSessionId: null,
                retryAttemptsByQuestion: {},
                retrySubmitting: {},
                retryErrors: {},
                thinkingLog: [],
            }),

            // Reset for new analysis (clears old CV/job data before new upload)
            resetForNewAnalysis: () => {
                console.log('🔄 Resetting for new analysis...');
                const { targetRole, targetCompany, jobDescription, questionCountOverride, interviewerPersona, piperStyle, ttsProvider } = get();
                set({
                    appState: APP_STATES.ANALYZING,
                    mindmap: '',
                    readinessScore: 0,
                    skillMapping: null,
                    bridgeRoles: [],
                    jobRequirements: null,
                    resumeData: null,
                    analysisProgress: 'Starting new analysis...',
                    // Keep configuration fields stable while regenerating analysis.
                    targetRole: targetRole || '',
                    targetCompany: targetCompany || '',
                    jobDescription: jobDescription || '',
                    questionCountOverride: questionCountOverride ?? null,
                    interviewerPersona: interviewerPersona || 'friendly',
                    piperStyle: normalizePiperStyle(piperStyle, 'interviewer'),
                    ttsProvider: normalizeTtsProvider(ttsProvider, 'piper'),
                    evaluationThresholds: {},
                    recordingThresholds: {},
                    lastAnalysisTime: null,
                    suggestedSessions: [],
                    practicePlan: null,
                    // Also clear any interview state
                    interviewActive: false,
                    interviewMode: 'practice',
                    interviewFeedbackTiming: 'end_only',
                    currentQuestion: null,
                    questionNumber: 0,
                    answerEvaluation: null,
                    coachingEnabled: false,
                    coachingHint: null,
                    allEvaluations: [],
                    interviewSummary: null,
                    answerSubmitPending: false,
                    selectedSession: null,
                    currentSessionId: null,
                    retryAttemptsByQuestion: {},
                    retrySubmitting: {},
                    retryErrors: {},
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
                interviewMode: 'practice',
                interviewFeedbackTiming: 'end_only',
                currentQuestion: null,
                questionNumber: 0,
                answerEvaluation: null,
                coachingEnabled: false,
                coachingHint: null,
                allEvaluations: [],
                interviewSummary: null,
                answerSubmitPending: false,
                selectedSession: null,
                currentSessionId: null,
                retryAttemptsByQuestion: {},
                retrySubmitting: {},
                retryErrors: {},
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
                                onboardingComplete: true,
                                sessionToken: data.session_token || get().sessionToken
                            });
                            // Persist basic auth
                            localStorage.setItem('user_id', data.user.user_id);
                            localStorage.setItem('onboarding_complete', 'true');
                            if (data.session_token) {
                                localStorage.setItem('session_token', data.session_token);
                            }
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
                                onboardingComplete: true,
                                sessionToken: data.session_token || get().sessionToken
                            });
                            // Persist basic auth
                            localStorage.setItem('user_id', data.user.user_id);
                            localStorage.setItem('onboarding_complete', 'true');
                            localStorage.setItem('user_name', data.user.username);
                            if (data.session_token) {
                                localStorage.setItem('session_token', data.session_token);
                            }
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
                const { socket, sessionToken } = get();

                // 1. Revoke server-side session token before disconnect (best effort)
                // Small delay improves chance the logout packet is sent before transport closes.
                if (socket?.connected && sessionToken) {
                    try {
                        socket.emit('logout', { session_token: sessionToken });
                    } catch (err) {
                        console.warn('⚠️ Failed to emit logout revoke event:', err);
                    }
                    setTimeout(() => {
                        try {
                            socket.disconnect();
                        } catch (_) { }
                    }, 120);
                } else if (socket) {
                    socket.disconnect();
                }

                // 2. Clear LocalStorage
                localStorage.removeItem('user_id');
                localStorage.removeItem('onboarding_complete');
                localStorage.removeItem('user_name');
                localStorage.removeItem('session_token');
                localStorage.removeItem('interview-agent-storage'); // Clear zustand persist

                // 3. Reset Store State completely
                set({
                    userId: null,
                    userEmail: null,
                    sessionToken: null,
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
                    jobDescription: '',
                    questionCountOverride: null,
                    interviewerPersona: 'friendly',
                    piperStyle: 'interviewer',
                    ttsProvider: 'piper',
                    evaluationThresholds: {},
                    recordingThresholds: {},
                    focusAreas: [],
                    lastAnalysisTime: null,

                    // Clear interview state
                    transcript: '',
                    lastTranscript: '',
                    currentTokens: '',
                    ttsAudioQueue: [],
                    isRecording: false,
                    interviewActive: false,
                    interviewMode: 'practice',
                    interviewFeedbackTiming: 'end_only',
                    currentQuestion: null,
                    questionNumber: 0,
                    totalQuestions: 0,
                    answerEvaluation: null,
                    coachingEnabled: false,
                    coachingHint: null,
                    allEvaluations: [],
                    interviewSummary: null,
                    answerSubmitPending: false,
                    selectedSession: null,
                    currentSessionId: null,
                    retryAttemptsByQuestion: {},
                    retrySubmitting: {},
                    retryErrors: {},
                    interviewHistory: [],
                    historyLoading: false,
                    deletingSessionIds: {},
                    selectedSessionLoading: false,
                    thinkingLog: []
                });

                console.log('✅ Logout complete');
            },

            // ============== Interview Practice Actions ==============

            // Start interview with context from analysis
            startInterviewPractice: (mode = 'practice') => {
                const { skillMapping, jobRequirements, readinessScore, focusAreas, jobDescription, questionCountOverride, interviewerPersona, piperStyle, ttsProvider } = get();

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
                    job_description: jobDescription || '',
                    question_count: questionCountOverride || undefined,
                    mode: mode,
                    coaching_enabled: mode === 'coaching',
                    feedback_timing: 'end_only',
                    live_scoring: false,
                    interviewer_persona: interviewerPersona || 'friendly',
                    piper_style: normalizePiperStyle(piperStyle, 'interviewer'),
                    tts_provider: normalizeTtsProvider(ttsProvider, 'piper'),
                });

                set({
                    appState: APP_STATES.INTERVIEWING,
                    interviewMode: mode,
                    interviewFeedbackTiming: 'end_only',
                    coachingEnabled: mode === 'coaching',
                });
                get().addThinking(`🎙️ Starting ${mode} mode...`);
            },

            // Submit answer to current question
            submitInterviewAnswer: (answerText, durationSeconds) => {
                const { socket, answerSubmitPending } = get();
                if (!socket?.connected || answerSubmitPending) return false;

                set({ answerSubmitPending: true });
                socket.emit('submit_interview_answer', {
                    answer: answerText,
                    duration_seconds: durationSeconds
                });
                return true;
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

            // Set default interviewer persona for upcoming sessions.
            setInterviewerPersona: (persona) => {
                const normalized = String(persona || '').trim().toLowerCase();
                const allowed = new Set(['friendly', 'strict']);
                set({ interviewerPersona: allowed.has(normalized) ? normalized : 'friendly' });
            },

            // Set default Piper voice style for upcoming sessions.
            setPiperStyle: (style) => {
                set({ piperStyle: normalizePiperStyle(style, 'interviewer') });
            },

            // Set default TTS provider for upcoming sessions.
            setTtsProvider: (provider) => {
                set({ ttsProvider: normalizeTtsProvider(provider, 'piper') });
            },

            // Save user preferences to backend
            savePreferences: (preferences) => {
                const { socket } = get();
                if (socket?.connected) {
                    socket.emit('save_preferences', preferences);
                }
                if (preferences && typeof preferences === 'object') {
                    const nextState = {};
                    if (Object.prototype.hasOwnProperty.call(preferences, 'target_role')) {
                        nextState.targetRole = preferences.target_role || '';
                    }
                    if (Object.prototype.hasOwnProperty.call(preferences, 'target_company')) {
                        nextState.targetCompany = preferences.target_company || '';
                    }
                    if (Object.prototype.hasOwnProperty.call(preferences, 'job_description')) {
                        nextState.jobDescription = preferences.job_description || '';
                    }
                    if (Object.prototype.hasOwnProperty.call(preferences, 'question_count_override')) {
                        const raw = preferences.question_count_override;
                        nextState.questionCountOverride =
                            raw === '' || raw === null || raw === undefined ? null : Number(raw);
                    }
                    if (Object.prototype.hasOwnProperty.call(preferences, 'interviewer_persona')) {
                        const normalized = String(preferences.interviewer_persona || '').trim().toLowerCase();
                        const allowed = new Set(['friendly', 'strict']);
                        nextState.interviewerPersona = allowed.has(normalized) ? normalized : 'friendly';
                    }
                    if (Object.prototype.hasOwnProperty.call(preferences, 'piper_style')) {
                        nextState.piperStyle = normalizePiperStyle(
                            preferences.piper_style,
                            get().piperStyle || 'interviewer'
                        );
                    }
                    if (Object.prototype.hasOwnProperty.call(preferences, 'tts_provider')) {
                        nextState.ttsProvider = normalizeTtsProvider(
                            preferences.tts_provider,
                            get().ttsProvider || 'piper'
                        );
                    }
                    if (Object.keys(nextState).length > 0) {
                        set(nextState);
                    }
                }
            },

            // Load user preferences from backend
            loadPreferences: () => {
                const { socket } = get();
                if (socket?.connected) {
                    socket.emit('get_preferences');
                }
            },

            // Load latest saved career analysis from backend DB.
            loadLatestAnalysis: () => {
                const { socket } = get();
                if (socket?.connected) {
                    socket.emit('get_latest_analysis', {});
                }
            },

            // Load interview history from backend
            loadInterviewHistory: (force = false) => {
                const { socket, interviewHistory, historyLoading } = get();
                // Don't re-fetch if already loading or data exists (unless forced)
                if (!socket?.connected) return;
                if (historyLoading) return;
                if (!force && interviewHistory.length > 0) return;
                set({ historyLoading: true });
                socket.emit('get_interview_history', { limit: 30 });
            },

            deleteInterviewHistory: () => {
                const { socket } = get();
                if (!socket?.connected) return false;
                set({ historyLoading: true, selectedSessionLoading: false });
                socket.emit('delete_interview_history', {});
                return true;
            },

            deleteInterviewSession: (sessionId) => {
                const cleanSessionId = String(sessionId || '').trim();
                const { socket } = get();
                if (!socket?.connected || !cleanSessionId) return false;
                set((state) => ({
                    historyLoading: true,
                    selectedSessionLoading: false,
                    deletingSessionIds: {
                        ...state.deletingSessionIds,
                        [cleanSessionId]: true,
                    },
                }));
                socket.emit('delete_interview_session', { session_id: cleanSessionId });
                return true;
            },

            clearConfiguration: () => {
                const { socket } = get();
                if (!socket?.connected) return false;
                socket.emit('clear_configuration', {});
                return true;
            },

            resetAllData: () => {
                const { socket } = get();
                if (!socket?.connected) return false;
                set({ historyLoading: true, selectedSessionLoading: false });
                socket.emit('reset_all_data', {});
                return true;
            },

            // Load details of a specific session
            loadSessionDetails: (sessionId) => {
                const { socket } = get();
                if (socket?.connected) {
                    set({ selectedSessionLoading: true, selectedSession: null });
                    socket.emit('get_session_details', { session_id: sessionId });
                }
            },

            // Clear selected session
            clearSelectedSession: () => set({ selectedSession: null }),

            loadRetryAttempts: (sessionId, questionNumber) => {
                const { socket } = get();
                if (!socket?.connected || !sessionId || !questionNumber) return;
                socket.emit('get_retry_attempts', {
                    session_id: sessionId,
                    question_number: Number(questionNumber),
                });
            },

            submitRetryAnswer: ({
                sessionId,
                questionNumber,
                answer,
                durationSeconds = 0,
                inputMode = 'text',
            }) => {
                const { socket } = get();
                if (!socket?.connected || !sessionId || !questionNumber) return false;
                const cleanAnswer = String(answer || '').trim();
                if (!cleanAnswer) return false;

                const key = `${sessionId}:${Number(questionNumber)}`;
                set((state) => ({
                    retrySubmitting: { ...state.retrySubmitting, [key]: true },
                    retryErrors: { ...state.retryErrors, [key]: '' },
                }));

                socket.emit('submit_retry_answer', {
                    session_id: sessionId,
                    question_number: Number(questionNumber),
                    answer: cleanAnswer,
                    duration_seconds: Number(durationSeconds || 0),
                    input_mode: String(inputMode || 'text'),
                });
                return true;
            },

            // Normalize a historical session payload into report-compatible state
            setReportFromHistorySession: (session) => {
                if (!session) return;

                const summary = session.summary || {};
                const evaluations = (session.answers || []).map((answer) => ({
                    question: {
                        text: answer.question_text || 'Question',
                        category: answer.category || 'General',
                        skill_tested: answer.difficulty || '',
                        expected_points: [],
                    },
                    answer: answer.user_answer || '',
                    evaluation: answer.evaluation || {},
                    duration: answer.duration_seconds || 0,
                }));

                set({
                    selectedSession: session,
                    currentSessionId: session.session_id || null,
                    interviewSummary: {
                        ...summary,
                        average_score: session.average_score ?? summary.average_score ?? 0,
                        total_questions: session.total_questions ?? summary.total_questions ?? evaluations.length,
                        answered_questions: session.answered_questions ?? summary.answered_questions ?? evaluations.length,
                    },
                    allEvaluations: evaluations,
                    answerSubmitPending: false,
                    appState: APP_STATES.COMPLETE,
                });
            },
        }),

        {
            name: 'interview-agent-storage', // localStorage key
            partialize: (state) => ({
                // Only persist these fields:
                userId: state.userId,
                sessionToken: state.sessionToken,
                appState: state.appState,
                onboardingComplete: state.onboardingComplete,
                darkMode: state.darkMode,
                mindmap: state.mindmap,
                readinessScore: state.readinessScore,
                skillMapping: state.skillMapping,
                bridgeRoles: state.bridgeRoles,
                jobRequirements: state.jobRequirements,
                resumeData: state.resumeData,
                targetRole: state.targetRole,
                targetCompany: state.targetCompany,
                jobDescription: state.jobDescription,
                questionCountOverride: state.questionCountOverride,
                interviewerPersona: state.interviewerPersona,
                piperStyle: state.piperStyle,
                ttsProvider: state.ttsProvider,
                evaluationThresholds: state.evaluationThresholds,
                recordingThresholds: state.recordingThresholds,
                focusAreas: state.focusAreas,
                lastAnalysisTime: state.lastAnalysisTime,
                suggestedSessions: state.suggestedSessions,
                practicePlan: state.practicePlan,
                currentSessionId: state.currentSessionId,
                selectedSession: state.selectedSession,
                interviewSummary: state.interviewSummary,
                allEvaluations: state.allEvaluations,
            }),
        }
    )
);

// Selector to convert isConnected boolean to connectionStatus string
// Useful for compact network badges in any view.
export const useConnectionStatus = () => {
    return useInterviewStore((state) =>
        state.isConnected ? 'connected' : 'disconnected'
    );
};

export { APP_STATES };
export default useInterviewStore;
