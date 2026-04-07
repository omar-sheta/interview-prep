import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import useInterviewStore from '@/store/useInterviewStore';
import InterviewReadinessDialog from '@/components/InterviewReadinessDialog';
import {
    ThemeProvider,
    CssBaseline,
    Alert,
    Box,
    Container,
    Paper,
    Stack,
    Typography,
    Button,
    Chip,
    TextField,
    CircularProgress,
    Tabs,
    Tab,
    Fade,
} from '@mui/material';
import {
    ArrowBack,
    Lightbulb,
    LightbulbOutlined,
    VolumeUp,
    VolumeOff,
    Send,
    SkipNext,
    Timer,
    GraphicEq,
    Mic,
    MicOff,
    EditNote,
} from '@mui/icons-material';
import { createHiveTheme } from '@/theme/hiveTheme';
import HiveTopNav from '@/components/ui/HiveTopNav';
import {
    clearSharedPlaybackAudioSource,
    ensurePlaybackAudioSession,
    getQuestionAudioContext,
    primeQuestionAudioPlayback,
} from '@/lib/questionAudio';

const DEFAULT_SILENCE_AUTO_STOP_SECONDS = 5.0;
const DEFAULT_SILENCE_RMS_THRESHOLD = 0.008;

function formatTime(totalSeconds) {
    const s = Math.max(0, Math.round(totalSeconds));
    const min = Math.floor(s / 60);
    const sec = s % 60;
    return `${String(min).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
}

function floatTo16BitPCM(float32Array) {
    const out = new Int16Array(float32Array.length);
    for (let i = 0; i < float32Array.length; i += 1) {
        const sample = Math.max(-1, Math.min(1, float32Array[i]));
        out[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
    }
    return new Uint8Array(out.buffer);
}

function bytesToBase64(bytes) {
    let binary = '';
    const chunk = 0x8000;
    for (let i = 0; i < bytes.length; i += chunk) {
        binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
    }
    return window.btoa(binary);
}

function base64ToBytes(base64) {
    const binary = window.atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) {
        bytes[i] = binary.charCodeAt(i);
    }
    return bytes;
}

function pcm16Base64ToFloat32(base64) {
    const bytes = base64ToBytes(base64);
    const int16 = new Int16Array(bytes.buffer, bytes.byteOffset, Math.floor(bytes.byteLength / 2));
    const floats = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i += 1) {
        floats[i] = int16[i] / 32768;
    }
    return floats;
}

function normalizeHintList(value, limit = 3) {
    if (!Array.isArray(value)) return [];
    return value
        .map((item) => String(item || '').trim())
        .filter(Boolean)
        .slice(0, limit);
}

export default function InterviewView() {
    const {
        currentQuestion,
        questionNumber,
        totalQuestions,
        transcript,
        coachingHint,
        answerSubmitPending,
        interviewError,
        requestHint,
        toggleCoaching,
        clearCoachingHint,
        clearInterviewError,
        skipQuestion,
        endInterview,
        submitInterviewAnswer,
        sendAudioChunk,
        setRecording,
        ttsAudioQueue,
        ttsStreamQueue,
        popAudio,
        popTtsStreamChunk,
        darkMode,
        micPermissionGranted,
        recordingThresholds,
        interviewMode,
        interviewFeedbackTiming,
        coachingEnabled,
        interviewerPersona,
        generatingReport,
        savePreferences,
    } = useInterviewStore();

    const [draft, setDraft] = useState('');
    const [elapsedTime, setElapsedTime] = useState(0);
    const [showTipsPanel, setShowTipsPanel] = useState(false);
    const [showHintDetails, setShowHintDetails] = useState(false);
    const [inputMode, setInputMode] = useState('record');
    const [isMicRecording, setIsMicRecording] = useState(false);
    const [isMicStarting, setIsMicStarting] = useState(false);
    const [micError, setMicError] = useState('');
    const [questionAudioEnabled, setQuestionAudioEnabled] = useState(true);
    const [questionAudioBlocked, setQuestionAudioBlocked] = useState(false);
    const [questionAudioPlaying, setQuestionAudioPlaying] = useState(false);
    const [pendingQuestionAudio, setPendingQuestionAudio] = useState(null);
    const [pendingQuestionStreamChunk, setPendingQuestionStreamChunk] = useState(null);
    const [readinessOpen, setReadinessOpen] = useState(true);

    const isRecordingRef = useRef(false);
    const streamRef = useRef(null);
    const audioContextRef = useRef(null);
    const sourceNodeRef = useRef(null);
    const processorNodeRef = useRef(null);
    const muteGainNodeRef = useRef(null);
    const recordingEpochRef = useRef(0);
    const questionAudioRef = useRef(null);
    const questionAudioPlayingRef = useRef(false);
    const ttsPlaybackContextRef = useRef(null);
    const ttsScheduledSourcesRef = useRef([]);
    const ttsNextPlaybackTimeRef = useRef(0);
    const ttsPlaybackQuestionRef = useRef(null);
    const ttsPlaybackEndTimerRef = useRef(null);
    const autoHintQuestionRef = useRef(0);
    const silenceAutoStopSeconds = Math.max(
        1,
        Math.min(20, Number(recordingThresholds?.silence_auto_stop_seconds ?? DEFAULT_SILENCE_AUTO_STOP_SECONDS))
    );
    const silenceRmsThreshold = Math.max(
        0.001,
        Math.min(0.05, Number(recordingThresholds?.silence_rms_threshold ?? DEFAULT_SILENCE_RMS_THRESHOLD))
    );
    const silenceAutoStopMs = Math.round(silenceAutoStopSeconds * 1000);
    const isCoachSession = Boolean(coachingEnabled || interviewMode === 'coaching');
    const gradingModeLabel = interviewFeedbackTiming === 'live' ? 'Live score reveal' : 'Final report reveal';

    useEffect(() => {
        const timer = setInterval(() => setElapsedTime((prev) => prev + 1), 1000);
        return () => clearInterval(timer);
    }, []);

    const releaseAudioNodes = useCallback(() => {
        if (processorNodeRef.current) {
            processorNodeRef.current.onaudioprocess = null;
            processorNodeRef.current.disconnect();
            processorNodeRef.current = null;
        }
        if (sourceNodeRef.current) {
            sourceNodeRef.current.disconnect();
            sourceNodeRef.current = null;
        }
        if (muteGainNodeRef.current) {
            muteGainNodeRef.current.disconnect();
            muteGainNodeRef.current = null;
        }
        if (streamRef.current) {
            streamRef.current.getTracks().forEach((track) => track.stop());
            streamRef.current = null;
        }
        if (audioContextRef.current) {
            audioContextRef.current.close().catch(() => { });
            audioContextRef.current = null;
        }
    }, []);

    const stopRecording = useCallback((flushTranscript = false) => {
        // Invalidate any in-flight start sequence immediately.
        recordingEpochRef.current += 1;
        isRecordingRef.current = false;
        setIsMicRecording(false);
        setIsMicStarting(false);
        setRecording(false);
        releaseAudioNodes();
    }, [releaseAudioNodes, setRecording]);

    const startRecording = useCallback(async () => {
        if (isRecordingRef.current || isMicStarting) return;
        if (!navigator.mediaDevices?.getUserMedia) {
            setMicError('Microphone access is not supported in this browser.');
            return;
        }

        const epoch = recordingEpochRef.current + 1;
        recordingEpochRef.current = epoch;

        try {
            clearInterviewError();
            setMicError('');
            setIsMicStarting(true);

            const stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                    channelCount: 1,
                },
            });

            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            const audioContext = new AudioCtx();
            await audioContext.resume();

            // If user already stopped before startup completed, abort this start cleanly.
            if (recordingEpochRef.current !== epoch) {
                stream.getTracks().forEach((track) => track.stop());
                audioContext.close().catch(() => { });
                return;
            }

            const source = audioContext.createMediaStreamSource(stream);
            const processor = audioContext.createScriptProcessor(4096, 1, 1);
            const muteGain = audioContext.createGain();
            muteGain.gain.value = 0;
            let lastVoiceDetectedAt = performance.now();
            let silenceTriggered = false;

            processor.onaudioprocess = (event) => {
                if (!isRecordingRef.current || recordingEpochRef.current !== epoch) return;
                // Gate: skip sending mic audio while TTS plays to avoid echo feedback
                if (questionAudioPlayingRef.current) return;
                const input = event.inputBuffer.getChannelData(0);

                let sumSquares = 0;
                for (let i = 0; i < input.length; i += 1) {
                    sumSquares += input[i] * input[i];
                }
                const rms = Math.sqrt(sumSquares / Math.max(1, input.length));
                const now = performance.now();
                if (rms >= silenceRmsThreshold) {
                    lastVoiceDetectedAt = now;
                } else if (!silenceTriggered && (now - lastVoiceDetectedAt) >= silenceAutoStopMs) {
                    silenceTriggered = true;
                    stopRecording(false);
                    return;
                }

                const pcmBytes = floatTo16BitPCM(input);
                if (!pcmBytes.length) return;
                sendAudioChunk(bytesToBase64(pcmBytes), audioContext.sampleRate);
            };

            source.connect(processor);
            processor.connect(muteGain);
            muteGain.connect(audioContext.destination);

            streamRef.current = stream;
            audioContextRef.current = audioContext;
            sourceNodeRef.current = source;
            processorNodeRef.current = processor;
            muteGainNodeRef.current = muteGain;

            isRecordingRef.current = true;
            setIsMicRecording(true);
            setRecording(true);
            setIsMicStarting(false);
        } catch (err) {
            console.error('Microphone start error:', err);
            setMicError('Could not access microphone. Check browser permission and device input.');
            if (recordingEpochRef.current === epoch) {
                stopRecording(false);
            }
        }
    }, [clearInterviewError, isMicStarting, sendAudioChunk, setRecording, silenceAutoStopMs, silenceRmsThreshold, stopRecording]);

    const ensureQuestionPlaybackContext = useCallback(async () => {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (!AudioCtx) return null;

        await ensurePlaybackAudioSession('playback');

        let audioContext = ttsPlaybackContextRef.current || getQuestionAudioContext();
        if (!audioContext || audioContext.state === 'closed') {
            audioContext = new AudioCtx();
            window.__beePreparedQuestionAudioContext = audioContext;
            ttsPlaybackContextRef.current = audioContext;
        }
        if (audioContext.state === 'suspended') {
            await audioContext.resume();
        }
        ttsPlaybackContextRef.current = audioContext;
        return audioContext;
    }, []);

    const scheduleQuestionAudioFinish = useCallback(() => {
        if (ttsPlaybackEndTimerRef.current) {
            window.clearTimeout(ttsPlaybackEndTimerRef.current);
            ttsPlaybackEndTimerRef.current = null;
        }

        const audioContext = ttsPlaybackContextRef.current;
        const remainingMs = audioContext
            ? Math.max(80, ((ttsNextPlaybackTimeRef.current - audioContext.currentTime) * 1000) + 250)
            : 250;

        ttsPlaybackEndTimerRef.current = window.setTimeout(() => {
            setQuestionAudioPlaying(false);
            questionAudioPlayingRef.current = false;
            ttsPlaybackQuestionRef.current = null;
        }, remainingMs);
    }, []);

    const stopQuestionAudio = useCallback(() => {
        const audio = questionAudioRef.current;
        if (audio) {
            audio.pause();
            clearSharedPlaybackAudioSource();
            questionAudioRef.current = null;
        }
        if (ttsPlaybackEndTimerRef.current) {
            window.clearTimeout(ttsPlaybackEndTimerRef.current);
            ttsPlaybackEndTimerRef.current = null;
        }
        for (const source of ttsScheduledSourcesRef.current) {
            try {
                source.stop(0);
            } catch (_) {
                // Source may already be finished; safe to ignore.
            }
            try {
                source.disconnect();
            } catch (_) {
                // Already disconnected.
            }
        }
        ttsScheduledSourcesRef.current = [];
        ttsPlaybackContextRef.current = getQuestionAudioContext() || ttsPlaybackContextRef.current;
        ttsNextPlaybackTimeRef.current = 0;
        ttsPlaybackQuestionRef.current = null;
        setQuestionAudioPlaying(false);
        questionAudioPlayingRef.current = false;
    }, []);

    const playQuestionAudio = useCallback(async (audioBase64) => {
        if (!audioBase64) return false;
        console.log('[TTS] playQuestionAudio called, audioBase64 length:', audioBase64.length);
        stopQuestionAudio();

        try {
            const audioContext = await ensureQuestionPlaybackContext();
            if (!audioContext) return false;

            const bytes = base64ToBytes(audioBase64);
            const audioBuffer = await audioContext.decodeAudioData(bytes.buffer.slice(0));

            const source = audioContext.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(audioContext.destination);

            source.onended = () => {
                console.log('[TTS] Audio playback ended');
                ttsScheduledSourcesRef.current = ttsScheduledSourcesRef.current.filter((s) => s !== source);
                try { source.disconnect(); } catch (_) { /* already disconnected */ }
                setQuestionAudioPlaying(false);
                setTimeout(() => { questionAudioPlayingRef.current = false; }, 250);
            };

            ttsScheduledSourcesRef.current.push(source);
            source.start(0);

            setQuestionAudioPlaying(true);
            questionAudioPlayingRef.current = true;
            console.log('[TTS] Web Audio playback started');
            return true;
        } catch (err) {
            console.error('[TTS] Web Audio playback failed:', err);
            setQuestionAudioPlaying(false);
            questionAudioPlayingRef.current = false;
            return false;
        }
    }, [stopQuestionAudio, ensureQuestionPlaybackContext]);

    const playQuestionStreamChunk = useCallback(async (chunkPayload) => {
        if (!chunkPayload?.audio) return false;

        try {
            const questionIndex = Number.isInteger(chunkPayload.question_index)
                ? Number(chunkPayload.question_index)
                : null;
            const chunkIndex = Number(chunkPayload.chunk_index || 0);
            const audioContext = await ensureQuestionPlaybackContext();
            if (!audioContext) return false;

            if (chunkIndex === 0 || (questionIndex !== null && ttsPlaybackQuestionRef.current !== questionIndex)) {
                stopQuestionAudio();
                const refreshedContext = await ensureQuestionPlaybackContext();
                if (!refreshedContext) return false;
                ttsPlaybackQuestionRef.current = questionIndex;
            }

            const activeContext = ttsPlaybackContextRef.current;
            if (!activeContext) return false;

            const samples = pcm16Base64ToFloat32(chunkPayload.audio);
            const sampleRate = Math.max(1, Number(chunkPayload.sample_rate || 24000));
            const audioBuffer = activeContext.createBuffer(1, samples.length, sampleRate);
            audioBuffer.copyToChannel(samples, 0);

            const source = activeContext.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(activeContext.destination);

            const startAt = Math.max(
                activeContext.currentTime + 0.03,
                ttsNextPlaybackTimeRef.current || (activeContext.currentTime + 0.03),
            );
            ttsNextPlaybackTimeRef.current = startAt + audioBuffer.duration;
            source.onended = () => {
                ttsScheduledSourcesRef.current = ttsScheduledSourcesRef.current.filter((item) => item !== source);
                try {
                    source.disconnect();
                } catch (_) {
                    // Already disconnected.
                }
            };
            ttsScheduledSourcesRef.current.push(source);
            source.start(startAt);

            setQuestionAudioPlaying(true);
            questionAudioPlayingRef.current = true;

            if (chunkPayload.is_final) {
                scheduleQuestionAudioFinish();
            }
            return true;
        } catch (err) {
            console.error('[TTS] Stream chunk playback failed:', err);
            return false;
        }
    }, [ensureQuestionPlaybackContext, scheduleQuestionAudioFinish, stopQuestionAudio]);

    useEffect(() => {
        console.log('[TTS] Playback effect: enabled=', questionAudioEnabled, 'playing=', questionAudioPlaying, 'queueLen=', ttsAudioQueue.length, 'pending=', !!pendingQuestionAudio);
        if (readinessOpen || !questionAudioEnabled || questionAudioPlaying) return;

        const nextAudio = pendingQuestionAudio || popAudio();
        if (!nextAudio) return;
        console.log('[TTS] Attempting playback, audio length:', nextAudio.length);

        let isMounted = true;
        playQuestionAudio(nextAudio).then((started) => {
            if (!isMounted) return;
            if (started) {
                setQuestionAudioBlocked(false);
                setPendingQuestionAudio(null);
            } else {
                setQuestionAudioBlocked(true);
                setPendingQuestionAudio(nextAudio);
            }
        });

        return () => {
            isMounted = false;
        };
    }, [pendingQuestionAudio, playQuestionAudio, popAudio, questionAudioEnabled, questionAudioPlaying, readinessOpen, ttsAudioQueue]);

    useEffect(() => {
        if (readinessOpen || !questionAudioEnabled) return;

        const nextChunk = pendingQuestionStreamChunk || popTtsStreamChunk();
        if (!nextChunk) return;

        let isMounted = true;
        playQuestionStreamChunk(nextChunk).then((started) => {
            if (!isMounted) return;
            if (started) {
                setQuestionAudioBlocked(false);
                setPendingQuestionStreamChunk(null);
            } else {
                setQuestionAudioBlocked(true);
                setPendingQuestionStreamChunk(nextChunk);
            }
        });

        return () => {
            isMounted = false;
        };
    }, [pendingQuestionStreamChunk, playQuestionStreamChunk, popTtsStreamChunk, questionAudioEnabled, readinessOpen, ttsStreamQueue]);

    useEffect(() => {
        if (readinessOpen || !questionAudioBlocked || !questionAudioEnabled || (!pendingQuestionAudio && !pendingQuestionStreamChunk)) return;

        let cancelled = false;
        const tryPlay = async () => {
            if (cancelled) return;
            const started = pendingQuestionStreamChunk
                ? await playQuestionStreamChunk(pendingQuestionStreamChunk)
                : await playQuestionAudio(pendingQuestionAudio);
            if (cancelled) return;
            if (started) {
                setQuestionAudioBlocked(false);
                setPendingQuestionAudio(null);
                setPendingQuestionStreamChunk(null);
            }
        };

        const onUserInteract = () => {
            void tryPlay();
        };

        window.addEventListener('pointerdown', onUserInteract);
        window.addEventListener('keydown', onUserInteract);
        return () => {
            cancelled = true;
            window.removeEventListener('pointerdown', onUserInteract);
            window.removeEventListener('keydown', onUserInteract);
        };
    }, [
        pendingQuestionAudio,
        pendingQuestionStreamChunk,
        playQuestionAudio,
        playQuestionStreamChunk,
        questionAudioBlocked,
        questionAudioEnabled,
        readinessOpen,
    ]);

    useEffect(() => {
        if (!readinessOpen) return;
        stopQuestionAudio();
    }, [readinessOpen, stopQuestionAudio]);

    useEffect(() => {
        if (coachingEnabled) {
            setShowTipsPanel((prev) => prev || true);
            return;
        }
        setShowTipsPanel(false);
        setShowHintDetails(false);
        clearCoachingHint();
    }, [coachingEnabled, clearCoachingHint]);

    useEffect(() => {
        const qNumber = Number(questionNumber || 0);
        if (!coachingEnabled || !showTipsPanel || qNumber <= 1) return;
        if (autoHintQuestionRef.current === qNumber) return;

        autoHintQuestionRef.current = qNumber;
        const timer = setTimeout(() => requestHint(), 280);
        return () => clearTimeout(timer);
    }, [coachingEnabled, questionNumber, requestHint, showTipsPanel]);

    useEffect(() => {
        setPendingQuestionAudio(null);
        setPendingQuestionStreamChunk(null);
        stopQuestionAudio();
        setDraft('');
        clearInterviewError();
    }, [clearInterviewError, questionNumber, stopQuestionAudio]);

    useEffect(() => () => stopRecording(false), [stopRecording]);
    useEffect(() => () => stopQuestionAudio(), [stopQuestionAudio]);

    const handleToggleHintsPanel = () => {
        if (showTipsPanel) {
            setShowTipsPanel(false);
            setShowHintDetails(false);
            toggleCoaching(false);
            clearCoachingHint();
            return;
        }
        setShowTipsPanel(true);
        setShowHintDetails(false);
        toggleCoaching(true);
        requestHint();
    };

    const handleReadinessClose = useCallback(() => {
        void primeQuestionAudioPlayback();
        setReadinessOpen(false);
    }, []);

    const handleSubmit = () => {
        if (answerSubmitPending) return;
        clearInterviewError();

        if (inputMode === 'type') {
            const answer = draft.trim();
            if (!answer) return;
            submitInterviewAnswer(answer, elapsedTime);
            setDraft('');
            return;
        }

        if (isMicRecording) {
            stopRecording(false);
            // Allow the last in-flight audio chunks to reach the server before submitting.
            setTimeout(() => submitInterviewAnswer('', elapsedTime), 200);
        } else {
            submitInterviewAnswer('', elapsedTime);
        }
    };

    const handleSkip = () => {
        if (answerSubmitPending) return;
        clearInterviewError();
        if (isMicRecording || isMicStarting) stopRecording(false);
        stopQuestionAudio();
        setDraft('');
        skipQuestion();
    };

    const handleModeChange = (_, nextMode) => {
        if (!nextMode) return;
        clearInterviewError();
        if (nextMode === 'type' && (isMicRecording || isMicStarting)) {
            stopRecording(false);
        }
        setInputMode(nextMode);
    };

    const transcriptText = String(transcript || '').trim();
    const submitDisabled = inputMode === 'type'
        ? (!draft.trim() || answerSubmitPending)
        : (answerSubmitPending || (!transcriptText && !isMicRecording));
    const hintLevel = Number(coachingHint?.level || 0);
    const hintMessage = String(coachingHint?.message || '').trim();
    const hintNextStep = String(coachingHint?.next_step || '').trim();
    const hintFramework = String(coachingHint?.framework || '').trim();
    const hintStarter = String(coachingHint?.starter || '').trim();
    const hintAvoid = String(coachingHint?.avoid || '').trim();
    const hintMustMention = normalizeHintList(coachingHint?.must_mention, 3);
    const hintsActionLabel = showTipsPanel ? 'Hide Hints' : 'Show Hints';
    const personaLabel = ({
        friendly: 'Friendly',
        strict: 'Strict',
    }[String(interviewerPersona || '').trim().toLowerCase()] || 'Friendly');
    const theme = useMemo(() => createHiveTheme(darkMode ? 'dark' : 'light'), [darkMode]);

    const handleEndSession = () => {
        clearInterviewError();
        if (isMicRecording || isMicStarting) {
            stopRecording(false);
        }
        stopQuestionAudio();
        endInterview();
    };

    const handleToggleQuestionAudio = () => {
        const next = !questionAudioEnabled;
        setQuestionAudioEnabled(next);
        if (!next) {
            stopQuestionAudio();
            setQuestionAudioBlocked(false);
            setPendingQuestionAudio(null);
            setPendingQuestionStreamChunk(null);
        }
    };

    const handleRetryQuestionAudio = async () => {
        const started = pendingQuestionStreamChunk
            ? await playQuestionStreamChunk(pendingQuestionStreamChunk)
            : (pendingQuestionAudio ? await playQuestionAudio(pendingQuestionAudio) : false);
        if (started) {
            setQuestionAudioBlocked(false);
            setPendingQuestionAudio(null);
            setPendingQuestionStreamChunk(null);
            return;
        }
        setQuestionAudioBlocked(true);
    };

    return (
        <ThemeProvider theme={theme}>
            <CssBaseline />
            <Box sx={{ minHeight: '100vh', bgcolor: 'background.default', pb: { xs: 3, md: 5 } }}>
                <HiveTopNav active="interview" />
                <Container
                    maxWidth={false}
                    sx={{
                        width: '100%',
                        maxWidth: 1040,
                        mx: 'auto',
                        px: { xs: 2, md: 3 },
                        pt: { xs: 2.5, md: 4 },
                    }}
                >
                    <Stack spacing={2.2}>
                        {/* Generating report overlay */}
                        {generatingReport && (
                            <Paper
                                sx={{
                                    p: { xs: 4, md: 6 },
                                    textAlign: 'center',
                                    display: 'flex',
                                    flexDirection: 'column',
                                    alignItems: 'center',
                                    gap: 2.5,
                                    minHeight: 320,
                                    justifyContent: 'center',
                                }}
                            >
                                <CircularProgress size={48} color="secondary" />
                                <Typography variant="h5" sx={{ fontWeight: 600 }}>
                                    Generating Your Report
                                </Typography>
                                <Typography variant="body1" color="text.secondary" sx={{ maxWidth: 420 }}>
                                    Evaluating your answers and building a detailed performance report. This usually takes a few seconds…
                                </Typography>
                            </Paper>
                        )}

                        {!generatingReport && (<><Paper sx={{ p: { xs: 2, md: 2.5 } }}>
                            <Stack spacing={1.2} sx={{ mb: 1.2 }}>
                                <Stack
                                    direction={{ xs: 'column', sm: 'row' }}
                                    justifyContent="space-between"
                                    alignItems={{ xs: 'flex-start', sm: 'center' }}
                                    spacing={1}
                                >
                                    <Typography variant="overline" sx={{ color: 'secondary.main', letterSpacing: '0.08em' }}>
                                        Question {questionNumber || 1} of {totalQuestions || 1}
                                    </Typography>
                                    <Chip
                                        size="small"
                                        icon={<Timer sx={{ fontSize: 15 }} />}
                                        label={formatTime(elapsedTime)}
                                        variant="outlined"
                                    />
                                </Stack>
                            </Stack>
                            <Typography variant="h5" sx={{ lineHeight: 1.35, maxWidth: 900 }}>
                                {currentQuestion?.text || 'Waiting for next question...'}
                            </Typography>
                            <Typography variant="body2" sx={{ mt: 1, color: 'text.secondary' }}>
                                {(isCoachSession ? 'Coach mode' : 'Mock mode')} • {personaLabel} interviewer • {gradingModeLabel} • {(currentQuestion?.category || 'General')} • {String(currentQuestion?.difficulty || 'medium')}
                            </Typography>
                            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mt: 1.25 }}>
                                <Button
                                    variant="outlined"
                                    color={questionAudioEnabled ? 'primary' : 'inherit'}
                                    startIcon={questionAudioEnabled ? <VolumeUp /> : <VolumeOff />}
                                    onClick={handleToggleQuestionAudio}
                                    size="small"
                                >
                                    {questionAudioEnabled ? 'Voice On' : 'Voice Off'}
                                </Button>
                                <Button
                                    variant={showTipsPanel ? 'contained' : 'outlined'}
                                    color={showTipsPanel ? 'secondary' : 'inherit'}
                                    startIcon={showTipsPanel ? <Lightbulb /> : <LightbulbOutlined />}
                                    onClick={handleToggleHintsPanel}
                                    size="small"
                                >
                                    {hintsActionLabel}
                                </Button>
                                <Button
                                    variant="text"
                                    color="warning"
                                    startIcon={<ArrowBack />}
                                    onClick={handleEndSession}
                                    size="small"
                                >
                                    End
                                </Button>
                            </Stack>
                            {questionAudioBlocked && questionAudioEnabled && (
                                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mt: 1.2 }}>
                                    <Typography variant="caption" sx={{ color: 'warning.main' }}>
                                        Browser blocked auto-play for question audio.
                                    </Typography>
                                    <Button
                                        size="small"
                                        variant="outlined"
                                        startIcon={<VolumeUp />}
                                        onClick={handleRetryQuestionAudio}
                                    >
                                        Play Prompt Audio
                                    </Button>
                                </Stack>
                            )}
                        </Paper>

                            {showTipsPanel && (
                                <Fade in timeout={160}>
                                    <Paper sx={{ p: { xs: 1.6, md: 2 } }}>
                                        <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1} sx={{ mb: 1 }}>
                                            <Box>
                                                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                                                    {isCoachSession ? 'Coach Hint' : 'Hint'}
                                                </Typography>
                                                <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                                    {hintMessage || 'Ask for a hint when you need guidance.'}
                                                </Typography>
                                            </Box>
                                            <Stack direction="row" spacing={0.6} useFlexGap flexWrap="wrap" alignItems="center">
                                                {hintLevel > 0 && <Chip size="small" label={`L${hintLevel}`} color="secondary" variant="outlined" />}
                                                <Button size="small" variant="outlined" onClick={requestHint}>
                                                    Refresh
                                                </Button>
                                                <Button size="small" variant="text" onClick={() => setShowHintDetails((prev) => !prev)}>
                                                    {showHintDetails ? 'Less' : 'Details'}
                                                </Button>
                                            </Stack>
                                        </Stack>

                                        {hintNextStep && (
                                            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                                <strong>Next:</strong> {hintNextStep}
                                            </Typography>
                                        )}

                                        {showHintDetails && (
                                            <Paper elevation={0} sx={{ mt: 1, p: 1.1, borderStyle: 'dashed' }}>
                                                {hintFramework && (
                                                    <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mb: 0.5 }}>
                                                        Framework: {hintFramework}
                                                    </Typography>
                                                )}
                                                {hintStarter && (
                                                    <Typography variant="body2" sx={{ mb: 0.7 }}>
                                                        <strong>Starter:</strong> "{hintStarter}"
                                                    </Typography>
                                                )}
                                                {hintMustMention.length > 0 && (
                                                    <Stack direction="row" spacing={0.6} useFlexGap flexWrap="wrap" sx={{ mb: 0.7 }}>
                                                        {hintMustMention.map((point) => (
                                                            <Chip key={point} size="small" label={point} variant="outlined" />
                                                        ))}
                                                    </Stack>
                                                )}
                                                <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                                    <strong>Avoid:</strong> {hintAvoid || 'Stay concrete and include one clear outcome.'}
                                                </Typography>
                                            </Paper>
                                        )}
                                    </Paper>
                                </Fade>
                            )}

                            {!showTipsPanel && !isCoachSession && (
                                <Paper sx={{ p: 1.2, bgcolor: darkMode ? 'rgba(245,158,11,0.05)' : 'rgba(249,115,22,0.05)' }}>
                                    <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1} alignItems={{ sm: 'center' }}>
                                        <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                                            Need help? Enable hints for one focused coaching prompt.
                                        </Typography>
                                        <Button
                                            size="small"
                                            variant="outlined"
                                            color="secondary"
                                            startIcon={<LightbulbOutlined />}
                                            onClick={handleToggleHintsPanel}
                                        >
                                            Enable Coach Hints
                                        </Button>
                                    </Stack>
                                </Paper>
                            )}

                            <Paper sx={{ p: { xs: 2, md: 2.5 } }}>
                                <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} spacing={1} sx={{ mb: 1.1 }}>
                                    <Typography variant="h6">Your Answer</Typography>
                                    <Tabs
                                        value={inputMode}
                                        onChange={handleModeChange}
                                        textColor="secondary"
                                        indicatorColor="secondary"
                                        sx={{ minHeight: 34, '& .MuiTab-root': { minHeight: 34, px: 1.6 } }}
                                    >
                                        <Tab icon={<GraphicEq sx={{ fontSize: 18 }} />} iconPosition="start" value="record" label="Record" />
                                        <Tab icon={<EditNote sx={{ fontSize: 18 }} />} iconPosition="start" value="type" label="Type" />
                                    </Tabs>
                                </Stack>

                                {inputMode === 'record' ? (
                                    <Stack spacing={1.2}>
                                        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }}>
                                            <Button
                                                variant={isMicRecording ? 'contained' : 'outlined'}
                                                color={isMicRecording ? 'error' : 'primary'}
                                                startIcon={isMicRecording ? <MicOff /> : <Mic />}
                                                onClick={isMicRecording ? () => stopRecording(true) : startRecording}
                                                disabled={isMicStarting}
                                            >
                                                {isMicStarting
                                                    ? 'Starting...'
                                                    : isMicRecording
                                                        ? 'Stop Recording'
                                                        : 'Start Recording'}
                                            </Button>
                                            <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                                                {isMicRecording ? 'Listening' : isMicStarting ? 'Starting mic' : 'Recorder idle'} • Auto-stop after {silenceAutoStopSeconds.toFixed(1)}s of silence
                                            </Typography>
                                        </Stack>

                                        {micError && (
                                            <Typography variant="body2" color="error">
                                                {micError}
                                            </Typography>
                                        )}

                                        {interviewError && (
                                            <Alert severity="warning" variant="outlined">
                                                {interviewError}
                                            </Alert>
                                        )}

                                        <Paper
                                            elevation={0}
                                            sx={{
                                                p: 1.2,
                                                minHeight: 140,
                                                maxHeight: 220,
                                                overflowY: 'auto',
                                                bgcolor: 'rgba(249, 115, 22, 0.06)',
                                                border: '1px solid rgba(249, 115, 22, 0.2)',
                                                position: 'relative',
                                            }}
                                        >
                                            {!transcriptText && !micError && (
                                                <Stack
                                                    spacing={0.8}
                                                    alignItems="center"
                                                    justifyContent="center"
                                                    sx={{
                                                        position: 'absolute',
                                                        inset: 0,
                                                        pointerEvents: 'none',
                                                        color: 'rgba(107, 114, 128, 0.35)',
                                                    }}
                                                >
                                                    <Mic sx={{ fontSize: 34 }} />
                                                    <Typography variant="caption" sx={{ letterSpacing: '0.05em' }}>
                                                        Live transcript waits for your voice
                                                    </Typography>
                                                </Stack>
                                            )}
                                            <Typography
                                                variant="body2"
                                                sx={{
                                                    color: transcriptText ? 'text.primary' : 'text.secondary',
                                                    whiteSpace: 'pre-wrap',
                                                    overflowWrap: 'anywhere',
                                                    position: 'relative',
                                                    zIndex: 1,
                                                }}
                                            >
                                                {transcriptText}
                                            </Typography>
                                        </Paper>
                                    </Stack>
                                ) : (
                                    <TextField
                                        fullWidth
                                        multiline
                                        minRows={8}
                                        value={draft}
                                        onChange={(e) => setDraft(e.target.value)}
                                        placeholder="Type your answer..."
                                    />
                                )}

                                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} justifyContent="space-between" sx={{ mt: 1.4 }}>
                                    <Button
                                        variant="outlined"
                                        startIcon={<SkipNext />}
                                        onClick={handleSkip}
                                        disabled={answerSubmitPending}
                                    >
                                        Skip Question
                                    </Button>
                                    <Button
                                        variant="contained"
                                        startIcon={answerSubmitPending ? <CircularProgress size={14} color="inherit" /> : <Send />}
                                        onClick={handleSubmit}
                                        disabled={submitDisabled}
                                    >
                                        {answerSubmitPending
                                            ? 'Submitting...'
                                            : inputMode === 'record'
                                                ? 'Submit Transcript'
                                                : 'Submit Answer'}
                                    </Button>
                                </Stack>
                            </Paper></>)}
                    </Stack>
                </Container>
                <InterviewReadinessDialog
                    open={readinessOpen}
                    onClose={handleReadinessClose}
                    onConfirm={handleReadinessClose}
                    micPermissionGranted={micPermissionGranted}
                    onMicPermissionChange={(granted) => savePreferences({ mic_permission_granted: granted })}
                    title="Mic & Sound Check"
                    subtitle="Check your mic and speaker on this device."
                    actionLabel="Continue"
                />
            </Box>
        </ThemeProvider>
    );
}
