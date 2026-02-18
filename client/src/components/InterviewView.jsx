/**
 * Interview Session View - Redesigned
 * Split Screen Focus Interface (Question | Response)
 * Light Mode / Apple-like Aesthetic
 */

import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import useInterviewStore from '@/store/useInterviewStore';
import OrbVisualizer from './OrbVisualizer';
import {
    Mic,
    MicOff,
    Keyboard,
    Send,
    Lightbulb,
    ArrowBack,
    Timer,
    Stop,
    CheckCircle,
    FiberManualRecord
} from '@mui/icons-material';
import {
    Box,
    Typography,
    Paper,
    IconButton,
    Button,
    TextField,
    Chip,
    LinearProgress,
    Divider,
    ThemeProvider,
    createTheme,
    CssBaseline,
    Container,
    Grid,
    Stack,
    Fab
} from '@mui/material';

// --- Hive & Bees Dark Theme for Interview Mode ---
const interviewTheme = createTheme({
    palette: {
        mode: 'dark',
        background: { default: '#0A0A0A', paper: '#121212' },
        primary: { main: '#F97316', light: '#FB923C', dark: '#EA580C' },
        secondary: { main: '#FBBF24' },
        error: { main: '#EF4444' },
        success: { main: '#22C55E' },
        text: { primary: '#FAFAFA', secondary: '#A3A3A3' },
        divider: 'rgba(249, 115, 22, 0.15)',
    },
    typography: {
        fontFamily: 'Inter, -apple-system, sans-serif',
        h3: { fontWeight: 700, letterSpacing: '-0.5px', lineHeight: 1.2, color: '#FAFAFA' },
        h4: { fontWeight: 700, letterSpacing: '-0.5px', color: '#FAFAFA' },
        h6: { fontWeight: 600, color: '#FAFAFA' },
        body1: { lineHeight: 1.6, color: '#E5E5E5' }
    },
    shape: { borderRadius: 16 },
    components: {
        MuiPaper: {
            styleOverrides: {
                root: {
                    backgroundImage: 'none',
                    backgroundColor: '#1A1A1A',
                    border: '1px solid rgba(249, 115, 22, 0.1)',
                },
            },
        },
        MuiChip: {
            styleOverrides: {
                outlined: {
                    borderColor: 'rgba(249, 115, 22, 0.3)',
                },
            },
        },
        MuiButton: {
            styleOverrides: {
                contained: {
                    backgroundColor: '#F97316',
                    '&:hover': { backgroundColor: '#EA580C' },
                },
            },
        },
    },
});

// --- Main View ---

export default function InterviewView() {
    const {
        isRecording,
        currentQuestion,
        transcript,
        lastTranscript,
        answerEvaluation,
        submitInterviewAnswer,
        endInterview,
        skipQuestion,
        coachingHint,
        interviewActive,
        questionNumber,
        totalQuestions,
        requestHint,
        setRecording,
    } = useInterviewStore();

    const [mode, setMode] = useState('voice'); // 'voice' | 'text'
    const [elapsedTime, setElapsedTime] = useState(0);
    const [isProcessing, setIsProcessing] = useState(false);
    const [textInput, setTextInput] = useState('');

    // Audio Context Refs
    const audioContextRef = useRef(null);
    const analyserRef = useRef(null);
    const processorRef = useRef(null);
    const streamRef = useRef(null);
    const scrollRef = useRef(null);

    // Timer
    useEffect(() => {
        if (!interviewActive) return;
        const interval = setInterval(() => setElapsedTime(p => p + 1), 1000);
        return () => clearInterval(interval);
    }, [interviewActive]);

    const formatTime = (seconds) => {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    };

    // Auto-scroll transcript
    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [transcript, lastTranscript]);

    // Audio Handlers
    const startAudio = async () => {
        try {
            audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: 16000,
            });
            if (audioContextRef.current.state === 'suspended') {
                await audioContextRef.current.resume();
            }

            const stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                }
            });
            streamRef.current = stream;

            const source = audioContextRef.current.createMediaStreamSource(stream);
            const analyser = audioContextRef.current.createAnalyser();
            analyser.fftSize = 256;
            analyserRef.current = analyser;

            const processor = audioContextRef.current.createScriptProcessor(4096, 1, 1);
            processorRef.current = processor;

            processor.onaudioprocess = (e) => {
                const state = useInterviewStore.getState();
                if (!state.isRecording) return;

                const inputData = e.inputBuffer.getChannelData(0);
                let l = inputData.length;
                const buf = new Int16Array(l);
                while (l--) {
                    buf[l] = Math.min(1, Math.max(-1, inputData[l])) * 0x7FFF;
                }

                let binary = '';
                const bytes = new Uint8Array(buf.buffer);
                const len = bytes.byteLength;
                for (let i = 0; i < len; i++) {
                    binary += String.fromCharCode(bytes[i]);
                }
                const base64 = window.btoa(binary);

                const socket = state.socket;
                if (socket && socket.connected) {
                    socket.emit('user_audio_chunk', {
                        audio: base64,
                        sample_rate: audioContextRef.current.sampleRate
                    });
                }
            };

            source.connect(analyser);
            analyser.connect(processor);
            processor.connect(audioContextRef.current.destination);

            setRecording(true);
        } catch (error) {
            console.error("Mic Error:", error);
            alert("Could not access microphone.");
        }
    };

    const stopAudio = () => {
        if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop());
        if (processorRef.current) processorRef.current.disconnect();
        if (audioContextRef.current) audioContextRef.current.close();
        setRecording(false);
    };

    const handleToggleMic = () => {
        if (isRecording) {
            stopAudio();
        } else {
            startAudio();
        }
    };

    const handleSendText = () => {
        if (!textInput.trim()) return;
        setIsProcessing(true);
        submitInterviewAnswer(textInput, elapsedTime);
        setTextInput('');
        setIsProcessing(false);
    };

    const handleCompleteAnswer = () => {
        stopAudio();
        submitInterviewAnswer(transcript || lastTranscript || "", elapsedTime);
    };

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            stopAudio();
        };
    }, []);

    const displayTranscript = transcript || lastTranscript || "";

    return (
        <ThemeProvider theme={interviewTheme}>
            <CssBaseline />
            <Box sx={{ height: '100vh', bgcolor: '#0A0A0A', display: 'flex', flexDirection: 'column' }}>

                {/* Top Bar */}
                <Paper
                    elevation={0}
                    sx={{
                        p: 2,
                        borderBottom: '1px solid rgba(249, 115, 22, 0.15)',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        borderRadius: 0,
                        bgcolor: '#121212'
                    }}
                >
                    <Stack direction="row" alignItems="center" spacing={2}>
                        <Typography variant="h6" fontWeight="800" sx={{ background: 'linear-gradient(135deg, #FBBF24, #F97316)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>HIVE Interview</Typography>
                        <Chip
                            label="Live Session"
                            color="error"
                            size="small"
                            icon={<FiberManualRecord sx={{ fontSize: 12 }} />}
                            sx={{ '& .MuiChip-icon': { color: 'inherit' } }}
                        />
                    </Stack>

                    <Chip
                        icon={<Timer />}
                        label={formatTime(elapsedTime)}
                        variant="outlined"
                        sx={{ fontFamily: 'monospace', fontWeight: 600, minWidth: 100, borderColor: 'rgba(249, 115, 22, 0.3)', color: '#FBBF24' }}
                    />

                    <Button
                        color="error"
                        variant="text"
                        onClick={() => { stopAudio(); endInterview(); }}
                        startIcon={<ArrowBack />}
                    >
                        End Session
                    </Button>
                </Paper>

                <Container maxWidth="xl" sx={{ flexGrow: 1, py: 4, overflow: 'hidden' }}>
                    <Grid container spacing={4} sx={{ height: '100%' }}>

                        {/* LEFT: The Question (Focus) */}
                        <Grid item xs={12} md={6}>
                            <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                                <Typography variant="overline" sx={{ color: '#FBBF24', fontWeight: 'bold' }}>
                                    QUESTION {questionNumber || 1} OF {totalQuestions || 3}
                                </Typography>

                                <motion.div
                                    key={currentQuestion?.text}
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    transition={{ duration: 0.5 }}
                                >
                                    <Typography variant="h3" sx={{ mt: 2, mb: 4, color: '#FAFAFA' }}>
                                        {currentQuestion?.text || "Waiting for interviewer..."}
                                    </Typography>
                                </motion.div>

                                <Stack direction="row" spacing={1} sx={{ mb: 4 }}>
                                    <Chip
                                        label={currentQuestion?.category || "General"}
                                        variant="outlined"
                                        size="small"
                                        sx={{ borderColor: 'rgba(249, 115, 22, 0.3)', color: '#FB923C' }}
                                    />
                                    <Chip
                                        label={currentQuestion?.difficulty || "Medium"}
                                        variant="outlined"
                                        size="small"
                                        sx={{ borderColor: 'rgba(251, 191, 36, 0.3)', color: '#FBBF24' }}
                                    />
                                </Stack>

                                {/* AI Coach Tip - Honey themed */}
                                <Paper
                                    sx={{
                                        p: 3,
                                        bgcolor: 'rgba(251, 191, 36, 0.1)',
                                        border: '1px solid rgba(251, 191, 36, 0.3)',
                                        borderRadius: 2
                                    }}
                                    elevation={0}
                                >
                                    <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
                                        <Lightbulb sx={{ color: '#FBBF24', fontSize: 20 }} />
                                        <Typography variant="subtitle2" fontWeight="bold" sx={{ color: '#FBBF24' }}>
                                            AI Coach Tip
                                        </Typography>
                                    </Stack>
                                    <Typography variant="body2" sx={{ color: '#FCD34D' }}>
                                        {coachingHint?.message || "Click 'Get Hint' if you need help structuring your answer."}
                                    </Typography>
                                </Paper>

                                {/* Action Buttons - Get Hint & Skip */}
                                <Stack direction="row" spacing={2} sx={{ mt: 3 }}>
                                    <Button
                                        variant="outlined"
                                        startIcon={<Lightbulb />}
                                        onClick={requestHint}
                                        sx={{
                                            flex: 1,
                                            borderColor: '#FBBF24',
                                            color: '#FBBF24',
                                            '&:hover': {
                                                bgcolor: 'rgba(251, 191, 36, 0.1)',
                                                borderColor: '#FCD34D'
                                            }
                                        }}
                                    >
                                        Get Hint
                                    </Button>
                                    <Button
                                        variant="outlined"
                                        onClick={skipQuestion}
                                        sx={{
                                            flex: 1,
                                            borderColor: 'rgba(249, 115, 22, 0.5)',
                                            color: '#FB923C',
                                            '&:hover': {
                                                bgcolor: 'rgba(249, 115, 22, 0.1)',
                                                borderColor: '#F97316'
                                            }
                                        }}
                                    >
                                        Skip Question →
                                    </Button>
                                </Stack>
                            </Box>
                        </Grid>

                        {/* RIGHT: The Response (Transcript & Audio) */}
                        <Grid item xs={12} md={6}>
                            <Paper
                                elevation={0}
                                sx={{
                                    height: '100%',
                                    bgcolor: '#1A1A1A',
                                    borderRadius: 4,
                                    border: '1px solid rgba(249, 115, 22, 0.15)',
                                    p: 4,
                                    display: 'flex',
                                    flexDirection: 'column'
                                }}
                            >
                                {/* Mode Switcher */}
                                <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
                                    <Typography variant="h6" fontWeight="bold" sx={{ color: '#FAFAFA' }}>
                                        {mode === 'voice' ? 'Live Transcript' : 'Type Your Answer'}
                                    </Typography>
                                    <Stack direction="row" spacing={1}>
                                        <IconButton
                                            color={mode === 'voice' ? 'primary' : 'default'}
                                            onClick={() => setMode('voice')}
                                            size="small"
                                            sx={{ bgcolor: mode === 'voice' ? 'rgba(249, 115, 22, 0.15)' : 'transparent', color: mode === 'voice' ? '#F97316' : '#A3A3A3' }}
                                        >
                                            <Mic />
                                        </IconButton>
                                        <IconButton
                                            color={mode === 'text' ? 'primary' : 'default'}
                                            onClick={() => setMode('text')}
                                            size="small"
                                            sx={{ bgcolor: mode === 'text' ? 'rgba(249, 115, 22, 0.15)' : 'transparent', color: mode === 'text' ? '#F97316' : '#A3A3A3' }}
                                        >
                                            <Keyboard />
                                        </IconButton>
                                    </Stack>
                                </Stack>

                                {mode === 'voice' ? (
                                    <>
                                        {/* Scrolling Transcript Area */}
                                        <Box
                                            ref={scrollRef}
                                            sx={{
                                                flexGrow: 1,
                                                overflowY: 'auto',
                                                mb: 4,
                                                bgcolor: '#121212',
                                                p: 3,
                                                borderRadius: 2,
                                                minHeight: 200,
                                                border: '1px solid rgba(249, 115, 22, 0.1)'
                                            }}
                                        >
                                            <Typography
                                                variant="body1"
                                                sx={{
                                                    lineHeight: 1.8,
                                                    color: displayTranscript ? '#FAFAFA' : '#525252',
                                                    fontStyle: displayTranscript ? 'normal' : 'italic'
                                                }}
                                            >
                                                {displayTranscript || "Start speaking... your transcript will appear here."}
                                            </Typography>
                                        </Box>

                                        {/* Recording indicator */}
                                        {isRecording && (
                                            <LinearProgress
                                                sx={{ mb: 2, borderRadius: 1, height: 4, bgcolor: 'rgba(249, 115, 22, 0.1)', '& .MuiLinearProgress-bar': { bgcolor: '#F97316' } }}
                                            />
                                        )}

                                        {/* Mic Controls */}
                                        <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 3 }}>
                                            <Fab
                                                size="large"
                                                onClick={handleToggleMic}
                                                sx={{
                                                    width: 72,
                                                    height: 72,
                                                    bgcolor: isRecording ? '#EF4444' : '#F97316',
                                                    '&:hover': { bgcolor: isRecording ? '#DC2626' : '#EA580C' }
                                                }}
                                            >
                                                {isRecording ? <Stop sx={{ fontSize: 32, color: 'white' }} /> : <Mic sx={{ fontSize: 32, color: 'white' }} />}
                                            </Fab>

                                            {displayTranscript && (
                                                <Button
                                                    variant="contained"
                                                    color="success"
                                                    size="large"
                                                    onClick={handleCompleteAnswer}
                                                    startIcon={<CheckCircle />}
                                                    sx={{ borderRadius: 100, px: 4 }}
                                                >
                                                    Submit Answer
                                                </Button>
                                            )}
                                        </Box>

                                        <Typography variant="caption" sx={{ textAlign: 'center', mt: 2, color: '#A3A3A3' }}>
                                            {isRecording ? "Recording... speak clearly" : "Tap to start speaking"}
                                        </Typography>
                                    </>
                                ) : (
                                    <>
                                        {/* Text Input Mode */}
                                        <Box sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column' }}>
                                            <TextField
                                                fullWidth
                                                multiline
                                                rows={8}
                                                placeholder="Type your answer here..."
                                                variant="outlined"
                                                value={textInput}
                                                onChange={(e) => setTextInput(e.target.value)}
                                                sx={{
                                                    flexGrow: 1,
                                                    '& .MuiOutlinedInput-root': {
                                                        borderRadius: 2,
                                                        bgcolor: '#121212',
                                                        height: '100%',
                                                        color: '#FAFAFA',
                                                        '& fieldset': { borderColor: 'rgba(249, 115, 22, 0.2)' },
                                                        '&:hover fieldset': { borderColor: 'rgba(249, 115, 22, 0.4)' },
                                                        '&.Mui-focused fieldset': { borderColor: '#F97316' },
                                                    }
                                                }}
                                            />
                                        </Box>

                                        <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 3 }}>
                                            <Button
                                                variant="contained"
                                                size="large"
                                                disabled={!textInput.trim() || isProcessing}
                                                onClick={handleSendText}
                                                endIcon={<Send />}
                                                sx={{
                                                    borderRadius: 100,
                                                    px: 4,
                                                    bgcolor: '#F97316',
                                                    '&:hover': { bgcolor: '#EA580C' }
                                                }}
                                            >
                                                Submit Answer
                                            </Button>
                                        </Box>
                                    </>
                                )}
                            </Paper>
                        </Grid>

                    </Grid>
                </Container>
            </Box>
        </ThemeProvider>
    );
}
