import { useState, useEffect } from 'react';
import {
    Description,
    Code as CodeIcon,
    People as PeopleIcon,
    Add as AddIcon,
    ArrowForward,
    Search,
    History,
    Map as MapIcon,
    PlayArrow,
    UploadFile,
    LocalHospital,
    TrendingUp,
    Work,
    Warning,
    EmojiPeople,
    OpenInFull,
    Close as CloseIcon,
    Edit as EditIcon,
    AutoAwesome
} from '@mui/icons-material';
import useInterviewStore from '@/store/useInterviewStore';
import MindmapViewer from './MindmapViewer';
import PDFDropzone from './PDFDropzone';
import InterviewPipeline from './InterviewPipeline';
import {
    Container,
    Grid,
    Paper,
    Typography,
    Button,
    Box,
    TextField,
    InputAdornment,
    Collapse,
    IconButton,
    createTheme,
    ThemeProvider,
    CssBaseline,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    Chip,
    Avatar,
    Dialog,
    Slide,
    DialogTitle,
    DialogContent,
    DialogActions,
    CircularProgress,
    LinearProgress
} from '@mui/material';

import React from 'react';

// Transition for Dialog
const Transition = React.forwardRef(function Transition(props, ref) {
    return <Slide direction="up" ref={ref} {...props} />;
});

// --- Icon Mapping for Dynamic Cards ---
const IconMap = {
    Description: Description,
    Code: CodeIcon,
    People: PeopleIcon,
    LocalHospital: LocalHospital,
    TrendingUp: TrendingUp,
    Work: Work,
    Warning: Warning,
    EmojiPeople: EmojiPeople
};

// --- Hive & Bees Dark Theme Definition ---
const dashboardTheme = createTheme({
    palette: {
        mode: 'dark',
        background: {
            default: '#0A0A0A',
            paper: '#121212',
        },
        text: {
            primary: '#FAFAFA',
            secondary: '#A3A3A3',
        },
        primary: {
            main: '#F97316',
            light: '#FB923C',
            dark: '#EA580C',
        },
        secondary: {
            main: '#FBBF24',
        },
        success: {
            main: '#22C55E',
        },
        error: {
            main: '#EF4444',
        },
        divider: 'rgba(249, 115, 22, 0.15)',
    },
    typography: {
        fontFamily: '-apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
        h5: { fontWeight: 700, letterSpacing: '-0.5px', fontSize: '1.5rem', color: '#FAFAFA' },
        h6: { fontWeight: 600, fontSize: '1.1rem', color: '#FAFAFA' },
        button: { textTransform: 'none', fontWeight: 600 },
        body1: { fontSize: '0.95rem', color: '#E5E5E5' },
        body2: { fontSize: '0.875rem', color: '#A3A3A3' },
    },
    shape: {
        borderRadius: 20,
    },
    components: {
        MuiPaper: {
            styleOverrides: {
                root: {
                    backgroundImage: 'none',
                    backgroundColor: '#1A1A1A',
                    boxShadow: '0px 4px 20px rgba(0,0,0,0.4), inset 0 1px 0 rgba(251, 191, 36, 0.03)',
                    border: '1px solid rgba(249, 115, 22, 0.1)',
                },
                rounded: {
                    borderRadius: 20,
                },
            },
        },
        MuiButton: {
            styleOverrides: {
                root: {
                    borderRadius: 12,
                    boxShadow: 'none',
                },
                contained: {
                    backgroundColor: '#F97316',
                    '&:hover': {
                        backgroundColor: '#EA580C',
                    },
                },
            },
        },
        MuiTextField: {
            styleOverrides: {
                root: {
                    '& .MuiOutlinedInput-root': {
                        borderRadius: 14,
                        backgroundColor: '#1A1A1A',
                        '& fieldset': { borderColor: 'rgba(249, 115, 22, 0.2)' },
                        '&:hover fieldset': { borderColor: 'rgba(249, 115, 22, 0.4)' },
                        '&.Mui-focused fieldset': { borderColor: '#F97316' },
                    },
                    '& .MuiInputLabel-root': { color: '#A3A3A3' },
                    '& .MuiInputBase-input': { color: '#FAFAFA' },
                },
            },
        },
        MuiChip: {
            styleOverrides: {
                root: {
                    borderColor: 'rgba(249, 115, 22, 0.3)',
                },
                outlined: {
                    borderColor: 'rgba(249, 115, 22, 0.3)',
                },
            },
        },
        MuiDialog: {
            styleOverrides: {
                paper: {
                    backgroundColor: '#1A1A1A',
                    border: '1px solid rgba(249, 115, 22, 0.15)',
                },
            },
        },
        MuiLinearProgress: {
            styleOverrides: {
                root: {
                    backgroundColor: 'rgba(249, 115, 22, 0.1)',
                },
                bar: {
                    backgroundColor: '#F97316',
                },
            },
        },
    },
});

export default function Dashboard({ onStartPractice }) {
    const { socket, isConnected, userId, logout, startInterviewPractice, setTargetJob, setTargetCompany } = useInterviewStore();

    // State
    const [history, setHistory] = useState([]);
    const [preferences, setPreferences] = useState({});
    const [analysis, setAnalysis] = useState(null);
    const [showJD, setShowJD] = useState(false);
    const [customTopic, setCustomTopic] = useState('');
    const [isAnalyzing, setIsAnalyzing] = useState(false);
    const [analysisProgress, setAnalysisProgress] = useState('');
    const [openMindmapModal, setOpenMindmapModal] = useState(false);

    // New Features State
    const [prepModalOpen, setPrepModalOpen] = useState(false);
    const [prepSession, setPrepSession] = useState(null);
    const [prepStatus, setPrepStatus] = useState('');
    const [customizationOpen, setCustomizationOpen] = useState(false);
    const [customizationPrompt, setCustomizationPrompt] = useState('');
    const [isRegenerating, setIsRegenerating] = useState(false);

    // Socket Logic — data fetching listeners only
    // NOTE: prepModalOpen and onStartPractice are intentionally excluded from deps
    // to prevent re-registering listeners (and re-emitting get_preferences) on every modal open/close.
    useEffect(() => {
        if (!socket || !isConnected) return;

        socket.emit('get_interview_history', { limit: 10, user_id: userId });
        socket.emit('get_preferences', { user_id: userId });
        socket.emit('get_latest_analysis', { user_id: userId });

        socket.on('interview_history', data => setHistory(data.history || []));
        socket.on('user_preferences', data => setPreferences(data.preferences || {}));
        socket.on('career_analysis', data => {
            setAnalysis(data.analysis || null);
            setIsAnalyzing(false);
            setAnalysisProgress('');
            setIsRegenerating(false);
        });
        socket.on('session_restored', data => {
            if (data.preferences) setPreferences(data.preferences);
        });
        socket.on('analysis_progress', data => setAnalysisProgress(data.message));
        socket.on('suggestions_updated', data => {
            setAnalysis(prev => ({ ...prev, suggested_sessions: data.suggestions }));
            setIsRegenerating(false);
            setCustomizationOpen(false);
        });
        socket.on('status', data => setPrepStatus(data.stage));

        return () => {
            socket.off('interview_history');
            socket.off('user_preferences');
            socket.off('career_analysis');
            socket.off('session_restored');
            socket.off('analysis_progress');
            socket.off('suggestions_updated');
            socket.off('status');
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [socket, isConnected, userId]);

    // Separate effect for interview_started — needs onStartPractice but must NOT
    // re-register the data-fetching listeners above when it changes.
    useEffect(() => {
        if (!socket) return;

        const handleInterviewStarted = () => {
            setPrepModalOpen(false);
            onStartPractice();
        };

        socket.on('interview_started', handleInterviewStarted);
        return () => socket.off('interview_started', handleInterviewStarted);
    }, [socket, onStartPractice]);

    const handlePreferenceChange = (key, value) => {
        const newPrefs = { ...preferences, [key]: value };
        setPreferences(newPrefs);
        if (key === 'target_role') setTargetJob(value);
        if (key === 'target_company') setTargetCompany(value);
        if (socket) socket.emit('save_preferences', newPrefs);
    };

    const handleDropzoneUpload = (base64, filename) => {
        setPreferences(prev => ({ ...prev, resume_filename: filename }));
        setIsAnalyzing(true);
        if (socket) {
            socket.emit('start_career_analysis', {
                user_id: userId,
                resume: "data:application/pdf;base64," + base64,
                job_title: preferences.target_role || "Candidate",
                company: preferences.target_company
            });
        }
    };

    const handleStartSession = (session) => {
        setPrepSession(session);
        setPrepModalOpen(true);
        setPrepStatus('Connecting...');

        if (socket) {
            // Determine mode and skills
            const mode = session.type || 'practice';
            const skillGaps = session.focus_topic ? [session.focus_topic] : (analysis?.skill_gaps || []);

            socket.emit('start_interview', {
                user_id: userId,
                job_title: preferences.target_role || "Candidate",
                mode: mode,
                skill_gaps: skillGaps,
                readiness_score: analysis?.readiness_score || 0.5,
                suggestion_id: session.id // Pass ID to use cache!
            });

            // Also update store state for consistency
            if (session.type !== 'resume') {
                setTargetJob(preferences.target_role || "Candidate");
            }
        }
    };

    const handleCreateCustomTopic = () => {
        if (!customTopic.trim()) return;
        // Logic for custom topic (treat as session)
        handleStartSession({
            id: 'custom',
            title: customTopic,
            subtitle: 'Custom Topic',
            type: 'drill',
            focus_topic: customTopic,
            icon: 'Code',
            color: 'blue'
        });
    };

    const handleCustomizeSubmit = () => {
        if (!customizationPrompt.trim()) return;
        setIsRegenerating(true);
        if (socket) {
            socket.emit('regenerate_suggestions', {
                prompt: customizationPrompt,
                analysis_id: analysis?.id
            });
        }
    };

    const hasMapData = analysis && analysis.analysis_data && (analysis.analysis_data.mindmap || analysis.analysis_data.mindmap_code);

    const getSafeSkillMapping = () => {
        if (!analysis) return null;
        const baseMapping = analysis.analysis_data?.skill_mapping || {};
        if (analysis.skill_gaps && Array.isArray(analysis.skill_gaps)) {
            return { ...baseMapping, missing: analysis.skill_gaps };
        }
        return Object.keys(baseMapping).length > 0 ? baseMapping : null;
    };

    return (
        <ThemeProvider theme={dashboardTheme}>
            <CssBaseline />

            <Container maxWidth={false} sx={{ mt: 4, mb: 10, pb: 10, px: { xs: 2, md: 4 }, overflow: 'visible' }}>
                {/* Header Section */}
                <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
                    <Box>
                        <Typography variant="h5" color="text.primary" fontWeight="bold">Dashboard</Typography>
                        <Typography variant="body2" color="text.secondary">Welcome back, {preferences.target_role || 'Candidate'}</Typography>
                    </Box>
                    <Box>
                        <Button variant="text" color="inherit" onClick={logout} startIcon={<ArrowForward sx={{ transform: 'rotate(180deg)' }} />}>
                            Sign Out
                        </Button>
                    </Box>
                </Stack>

                {/* 2-Column Layout: LEFT (Session Config + Mission Status stacked) | RIGHT (Interview Rounds) */}
                <Box sx={{ display: 'flex', flexDirection: { xs: 'column', md: 'row' }, gap: 3, alignItems: 'flex-start' }}>

                    {/* LEFT COLUMN: Session Configuration + Mission Status (stacked) */}
                    <Box sx={{ width: { xs: '100%', md: '320px' }, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 3 }}>

                        {/* Session Configuration */}
                        <Paper elevation={0} sx={{ p: 3, border: '1px solid', borderColor: 'divider', borderRadius: 4 }}>
                            <Stack direction="row" justifyContent="space-between" alignItems="start" sx={{ mb: 2 }}>
                                <Box>
                                    <Typography variant="h6">Session Configuration</Typography>
                                    <Typography variant="body2" color="text.secondary">Customize your targets.</Typography>
                                </Box>
                                {isAnalyzing && (
                                    <Chip
                                        label={analysisProgress || "Analyzing..."}
                                        color="primary"
                                        variant="outlined"
                                        size="small"
                                        sx={{
                                            animation: 'pulse 2s infinite',
                                            maxWidth: { xs: 150, md: 180 },
                                            '& .MuiChip-label': {
                                                display: 'block',
                                                whiteSpace: 'nowrap',
                                                overflow: 'hidden',
                                                textOverflow: 'ellipsis'
                                            }
                                        }}
                                    />
                                )}
                            </Stack>

                            <Stack spacing={2}>
                                <TextField
                                    label="Target Role" fullWidth size="small"
                                    value={preferences.target_role || ''}
                                    onChange={(e) => handlePreferenceChange('target_role', e.target.value)}
                                    placeholder="e.g. Senior Frontend Engineer"
                                    InputLabelProps={{ shrink: true }}
                                />
                                <TextField
                                    label="Target Company" fullWidth size="small"
                                    value={preferences.target_company || ''}
                                    onChange={(e) => handlePreferenceChange('target_company', e.target.value)}
                                    placeholder="e.g. Google"
                                    InputLabelProps={{ shrink: true }}
                                />

                                <Box sx={{
                                    minHeight: '100px', bgcolor: '#1A1A1A', borderRadius: 3,
                                    border: '1px dashed rgba(249, 115, 22, 0.3)', overflow: 'hidden', display: 'flex', flexDirection: 'column'
                                }}>
                                    <PDFDropzone onUpload={handleDropzoneUpload} isLoading={isAnalyzing} />
                                </Box>

                                <Box>
                                    <Button
                                        size="small"
                                        startIcon={<AddIcon />}
                                        onClick={() => setShowJD(!showJD)}
                                        sx={{ color: 'primary.main', mb: showJD ? 1 : 0 }}
                                    >
                                        Add Job Description
                                    </Button>
                                    <Collapse in={showJD}>
                                        <TextField
                                            multiline
                                            rows={3}
                                            fullWidth
                                            size="small"
                                            placeholder="Paste JD..."
                                            value={preferences.job_description || ''}
                                            onChange={(e) => handlePreferenceChange('job_description', e.target.value)}
                                            sx={{ mt: 1 }}
                                        />
                                    </Collapse>
                                </Box>
                            </Stack>
                        </Paper>

                        {/* Mission Status (below Session Configuration) */}
                        <Paper elevation={0} sx={{ p: 3, border: '1px solid', borderColor: 'divider', borderRadius: 4 }}>
                            <Typography variant="h6" fontWeight="bold" gutterBottom>Mission Status</Typography>
                            {analysis ? (
                                <>
                                    <Typography variant="body2" color="text.secondary" gutterBottom>
                                        Readiness Score: {analysis.readiness_score ? Math.round(analysis.readiness_score * 100) : 0}%
                                    </Typography>
                                    <Box sx={{ mt: 1, height: 8, bgcolor: 'rgba(249, 115, 22, 0.1)', borderRadius: 4, overflow: 'hidden' }}>
                                        <Box sx={{ width: `${(analysis.readiness_score || 0) * 100}%`, height: '100%', bgcolor: 'primary.main' }} />
                                    </Box>

                                    {hasMapData && (
                                        <Button
                                            variant="outlined"
                                            size="small"
                                            sx={{ mt: 2 }}
                                            onClick={() => setOpenMindmapModal(true)}
                                            fullWidth
                                        >
                                            View Career Map
                                        </Button>
                                    )}
                                </>
                            ) : (
                                <Typography variant="body2" color="text.secondary">
                                    Upload resume to see your readiness score.
                                </Typography>
                            )}
                        </Paper>
                    </Box>

                    {/* COLUMN 3: The Mission Loop (Interview Rounds) */}
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                        <Paper
                            elevation={0}
                            sx={{
                                p: 3,
                                border: '1px solid',
                                borderColor: 'divider',
                                borderRadius: 4,
                                bgcolor: '#1A1A1A',
                                height: '100%',
                                minHeight: '400px'
                            }}
                        >
                            {isRegenerating ? (
                                <Box sx={{ py: 10, display: 'flex', justifyContent: 'center', alignItems: 'center', flexDirection: 'column', gap: 2 }}>
                                    <CircularProgress size={40} />
                                    <Typography variant="body2" color="text.secondary">Architecting your mission...</Typography>
                                </Box>
                            ) : analysis?.practice_plan ? (
                                <InterviewPipeline
                                    plan={analysis.practice_plan}
                                    onStartSession={handleStartSession}
                                    onCustomize={() => setCustomizationOpen(true)}
                                />
                            ) : (analysis?.suggested_sessions?.length > 0) ? (
                                /* Fallback for legacy plans */
                                <Box>
                                    <Typography variant="h6" gutterBottom>Suggested Sessions</Typography>
                                    <Grid container spacing={2}>
                                        {analysis.suggested_sessions.map((session) => (
                                            <Grid item xs={12} md={6} key={session.id}>
                                                <Paper sx={{ p: 2, border: '1px solid rgba(249, 115, 22, 0.15)', bgcolor: '#1A1A1A', cursor: 'pointer' }} onClick={() => handleStartSession(session)}>
                                                    <Typography fontWeight="bold">{session.title}</Typography>
                                                    <Typography variant="caption">{session.type}</Typography>
                                                </Paper>
                                            </Grid>
                                        ))}
                                    </Grid>
                                </Box>
                            ) : (
                                <Box sx={{ p: 5, textAlign: 'center', mt: 5 }}>
                                    <Typography variant="h6" color="text.secondary" gutterBottom>
                                        Ready to Start?
                                    </Typography>
                                    <Typography variant="body2" color="text.secondary">
                                        Upload your resume to generate your personalized interview mission.
                                    </Typography>
                                </Box>
                            )}
                        </Paper>
                    </Box>
                </Box>
            </Container>

            {/* --- Expanded Mindmap Modal --- */}
            <Dialog
                fullScreen
                open={openMindmapModal}
                onClose={() => setOpenMindmapModal(false)}
                TransitionComponent={Transition}
            >
                <Box sx={{ bgcolor: '#F3F6F9', height: '100vh', display: 'flex', flexDirection: 'column' }}>
                    <Paper
                        elevation={0}
                        sx={{
                            p: 2,
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            borderRadius: 0,
                            borderBottom: '1px solid #E5E5EA'
                        }}
                    >
                        <Typography variant="h6" sx={{ fontWeight: 700 }}>Detailed Skill Analysis</Typography>
                        <IconButton onClick={() => setOpenMindmapModal(false)} edge="end">
                            <CloseIcon />
                        </IconButton>
                    </Paper>

                    <Box sx={{ flexGrow: 1, p: 3, overflow: 'hidden' }}>
                        <Paper sx={{ width: '100%', height: '100%', overflow: 'hidden', borderRadius: 3 }}>
                            {hasMapData ? (
                                <MindmapViewer
                                    mindmapCode={typeof (analysis.analysis_data?.mindmap || analysis.analysis_data?.mindmap_code) === 'string'
                                        ? (analysis.analysis_data?.mindmap || analysis.analysis_data?.mindmap_code)
                                        : ''}
                                    skillMapping={getSafeSkillMapping()}
                                />
                            ) : (
                                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
                                    <Typography color="text.secondary">No data available yet.</Typography>
                                </Box>
                            )}
                        </Paper>
                    </Box>
                </Box>
            </Dialog>

            {/* --- Interview Prep Modal (Pop & Wait) --- */}
            <Dialog
                open={prepModalOpen}
                maxWidth="sm"
                fullWidth
                PaperProps={{
                    sx: { borderRadius: 3, p: 1, bgcolor: '#1A1A1A', border: '1px solid rgba(249, 115, 22, 0.2)' }
                }}
            >
                <DialogTitle>Initializing Session</DialogTitle>
                <DialogContent>
                    <Stack spacing={3} alignItems="center" sx={{ py: 2 }}>
                        {prepSession?.icon && (
                            <Avatar sx={{ width: 64, height: 64, bgcolor: `${prepSession?.color || 'blue'}.main`, color: '#fff' }}>
                                {IconMap[prepSession.icon] ? React.createElement(IconMap[prepSession.icon]) : <Work />}
                            </Avatar>
                        )}
                        <Box sx={{ textAlign: 'center' }}>
                            <Typography variant="h6" gutterBottom>{prepSession?.title || 'Practice Session'}</Typography>
                            <Typography variant="body2" color="text.secondary">
                                {prepSession?.description || 'Preparing your custom interview environment...'}
                            </Typography>
                        </Box>

                        <Box sx={{ width: '100%' }}>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                                <Typography variant="caption" color="text.secondary">Status</Typography>
                                <Typography variant="caption" fontWeight={600}>{prepStatus || 'Connecting...'}</Typography>
                            </Box>
                            <LinearProgress variant="indeterminate" sx={{ borderRadius: 1, height: 6 }} />
                        </Box>

                        <Box sx={{ bgcolor: 'rgba(251, 191, 36, 0.1)', p: 2, borderRadius: 2, width: '100%', border: '1px solid rgba(251, 191, 36, 0.2)' }}>
                            <Box sx={{ display: 'flex', gap: 1, mb: 1 }}>
                                <AutoAwesome fontSize="small" sx={{ color: '#FBBF24' }} />
                                <Typography variant="caption" fontWeight={600} sx={{ color: '#FBBF24' }}>AI Tip</Typography>
                            </Box>
                            <Typography variant="caption" sx={{ color: '#FCD34D' }}>
                                "Take your time to think before answering. We're looking for structured thinking, not just the right answer."
                            </Typography>
                        </Box>
                    </Stack>
                </DialogContent>
            </Dialog>

            {/* --- Customize Suggestions Modal --- */}
            <Dialog
                open={customizationOpen}
                onClose={() => setCustomizationOpen(false)}
                maxWidth="sm"
                fullWidth
                PaperProps={{
                    sx: { bgcolor: '#1A1A1A', border: '1px solid rgba(249, 115, 22, 0.2)' }
                }}
            >
                <DialogTitle>Customize Suggestions</DialogTitle>
                <DialogContent>
                    <Typography variant="body2" color="text.secondary" paragraph>
                        Tell the AI how to adjust your practice plan. For example: "Focus more on System Design" or "I want to practice Python generators".
                    </Typography>
                    <TextField
                        autoFocus
                        fullWidth
                        multiline
                        rows={3}
                        placeholder="e.g. Give me harder algorithmic problems..."
                        value={customizationPrompt}
                        onChange={(e) => setCustomizationPrompt(e.target.value)}
                        sx={{ mt: 1 }}
                    />
                </DialogContent>
                <DialogActions sx={{ p: 2 }}>
                    <Button onClick={() => setCustomizationOpen(false)}>Cancel</Button>
                    <Button variant="contained" onClick={handleCustomizeSubmit} disabled={!customizationPrompt.trim()} disableElevation>
                        Regenerate Plan
                    </Button>
                </DialogActions>
            </Dialog>

        </ThemeProvider>
    );
}