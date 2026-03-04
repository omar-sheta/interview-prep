import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import useInterviewStore, { APP_STATES } from '@/store/useInterviewStore';
import {
    ThemeProvider,
    CssBaseline,
    Box,
    Container,
    Paper,
    Stack,
    Typography,
    Button,
    Chip,
    Divider,
    CircularProgress,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    TextField,
    ToggleButtonGroup,
    ToggleButton,
    IconButton,
} from '@mui/material';
import {
    ArrowForward,
    PlayArrow,
    Psychology,
    Code,
    AccountTree,
    AutoAwesome,
    EmojiEvents,
    TipsAndUpdates,
    Diversity3,
    Gavel,
    BoltOutlined,
    Close,
} from '@mui/icons-material';
import { createHiveTheme } from '@/theme/hiveTheme';
import HiveTopNav from '@/components/ui/HiveTopNav';

const INTERVIEW_TYPES = [
    {
        id: 'behavioral',
        title: 'Behavioral Interview',
        description: 'Practice leadership, conflict handling, communication, and STAR-style storytelling.',
        icon: Psychology,
        tags: ['STAR', 'Leadership', 'Communication'],
    },
    {
        id: 'technical',
        title: 'Technical Interview',
        description: 'Focus on implementation decisions, trade-offs, debugging, and applied technical reasoning.',
        icon: Code,
        tags: ['Problem Solving', 'Architecture', 'Debugging'],
    },
    {
        id: 'system_design',
        title: 'System Design Interview',
        description: 'Practice large-scale design prompts around scalability, reliability, and performance.',
        icon: AccountTree,
        tags: ['Scalability', 'Reliability', 'Trade-offs'],
    },
    {
        id: 'mixed',
        title: 'Mixed Interview',
        description: 'Balanced flow across behavioral, technical, and design-style prompts.',
        icon: AutoAwesome,
        tags: ['Balanced', 'Adaptive', 'General Prep'],
    },
];

const INTERVIEW_STYLES = [
    {
        id: 'mock',
        title: 'Mock Mode',
        subtitle: 'Premium simulation flow',
        description: 'Questions first, full grading only at the end. Great for realistic interview pressure.',
        mode: 'practice',
        coachingEnabled: false,
        icon: EmojiEvents,
        bullets: ['No visible per-question scores', 'Focused, uninterrupted answer flow', 'Optional hints only if you enable them'],
    },
    {
        id: 'coach',
        title: 'Coach Mode',
        subtitle: 'Guided practice flow',
        description: 'Same final report scoring, plus contextual hints and structure prompts while you answer.',
        mode: 'coaching',
        coachingEnabled: true,
        icon: TipsAndUpdates,
        bullets: ['Live hint cards with framework and next step', 'Manual hint request anytime', 'Best for fixing patterns quickly'],
    },
];

const INTERVIEW_PERSONAS = [
    {
        id: 'friendly',
        title: 'Friendly',
        icon: Diversity3,
        description: 'Supportive tone, clear prompts, and collaborative pacing.',
    },
    {
        id: 'strict',
        title: 'Strict',
        icon: Gavel,
        description: 'High bar, direct wording, and precision-focused follow-ups.',
    },
];

function normalizePersona(value) {
    const normalized = String(value || '').trim().toLowerCase();
    const allowed = new Set(INTERVIEW_PERSONAS.map((p) => p.id));
    return allowed.has(normalized) ? normalized : 'friendly';
}

function normalizeQuestionCount(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return 5;
    return Math.max(1, Math.min(12, Math.trunc(n)));
}

function getSkillGapsForType(interviewType, missingSkills = []) {
    const base = Array.isArray(missingSkills) ? missingSkills : [];

    if (interviewType === 'behavioral') {
        return [
            'communication',
            'stakeholder management',
            'leadership',
            'conflict resolution',
            ...base,
        ].slice(0, 8);
    }

    if (interviewType === 'technical') {
        if (base.length > 0) return base;
        return ['technical fundamentals', 'problem solving', 'debugging'];
    }

    if (interviewType === 'system_design') {
        return [
            'system design',
            'scalability',
            'reliability',
            'trade-offs',
            ...base,
        ].slice(0, 8);
    }

    return base;
}

export default function V0Setup() {
    const navigate = useNavigate();
    const {
        connect,
        isConnected,
        darkMode,
        appState,
        analysisProgress,
        readinessScore,
        skillMapping,
        targetRole,
        targetCompany,
        jobDescription,
        questionCountOverride,
        interviewerPersona,
        setInterviewerPersona,
        savePreferences,
        startInterview,
    } = useInterviewStore();

    const [startingType, setStartingType] = useState(null);
    const [selectedStyle, setSelectedStyle] = useState('mock');
    const [selectedPersona, setSelectedPersona] = useState(normalizePersona(interviewerPersona));
    const [error, setError] = useState('');

    // Quick Interview (cold start) state
    const [quickOpen, setQuickOpen] = useState(false);
    const [quickRole, setQuickRole] = useState('');
    const [quickJD, setQuickJD] = useState('');
    const [quickType, setQuickType] = useState('mixed');
    const [quickStarting, setQuickStarting] = useState(false);

    // Pre-fill quick interview fields from saved config when dialog opens
    const openQuickDialog = () => {
        setQuickRole(String(targetRole || '').trim());
        setQuickJD(String(jobDescription || '').trim());
        setQuickOpen(true);
    };

    useEffect(() => {
        connect();
    }, [connect]);

    useEffect(() => {
        setSelectedPersona(normalizePersona(interviewerPersona));
    }, [interviewerPersona]);

    const theme = useMemo(() => createHiveTheme(darkMode ? 'dark' : 'light'), [darkMode]);
    const readinessPercent = Math.round(Math.max(0, Math.min(1, Number(readinessScore || 0))) * 100);
    const isAnalyzing = appState === APP_STATES.ANALYZING;
    const hasConfiguration = String(targetRole || '').trim() && String(jobDescription || '').trim();
    const questionCount = normalizeQuestionCount(questionCountOverride || 5);
    const activeStyle = INTERVIEW_STYLES.find((style) => style.id === selectedStyle) || INTERVIEW_STYLES[0];
    const activePersona = INTERVIEW_PERSONAS.find((persona) => persona.id === selectedPersona) || INTERVIEW_PERSONAS[0];

    const handlePersonaSelect = (personaId) => {
        const normalized = normalizePersona(personaId);
        setSelectedPersona(normalized);
        setInterviewerPersona(normalized);
        savePreferences({ interviewer_persona: normalized });
    };

    const handleStart = (interviewType) => {
        if (!isConnected) {
            setError('Not connected to server yet. Please try again in a moment.');
            return;
        }

        if (!hasConfiguration) {
            setError('Configuration is incomplete. Set target role and job description first.');
            return;
        }

        // --- Unlock audio playback on user click ---
        try {
            const unlockAudio = new Audio();
            // A silent 1-second base64 wav file
            unlockAudio.src = 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA';
            unlockAudio.play().catch(() => { });
        } catch (e) {
            console.warn('Audio unlock failed:', e);
        }
        // -------------------------------------------

        setError('');
        setStartingType(interviewType.id);

        const selectedSkillGaps = getSkillGapsForType(interviewType.id, skillMapping?.missing || []);

        startInterview({
            job_title: String(targetRole || '').trim(),
            skill_gaps: selectedSkillGaps,
            readiness_score: readinessScore || 0.5,
            job_description: String(jobDescription || '').trim(),
            interview_type: interviewType.id,
            mode: activeStyle.mode,
            coaching_enabled: activeStyle.coachingEnabled,
            feedback_timing: 'end_only',
            live_scoring: false,
            interviewer_persona: selectedPersona,
            question_count: questionCount,
        });

        setTimeout(() => setStartingType(null), 3000);
    };

    const handleQuickStart = () => {
        const role = quickRole.trim();
        const jd = quickJD.trim();
        if (!role || !jd) return;
        if (!isConnected) {
            setError('Not connected to server yet. Please try again in a moment.');
            return;
        }

        // --- Unlock audio playback on user click ---
        try {
            const unlockAudio = new Audio();
            unlockAudio.src = 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA';
            unlockAudio.play().catch(() => { });
        } catch (e) {
            console.warn('Audio unlock failed:', e);
        }
        // -------------------------------------------

        setQuickStarting(true);
        setError('');

        const skillGaps = getSkillGapsForType(quickType, []);

        startInterview({
            job_title: role,
            skill_gaps: skillGaps,
            readiness_score: 0.5,
            job_description: jd,
            interview_type: quickType,
            mode: activeStyle.mode,
            coaching_enabled: activeStyle.coachingEnabled,
            feedback_timing: 'end_only',
            live_scoring: false,
            interviewer_persona: selectedPersona,
            question_count: questionCount,
        });

        setTimeout(() => {
            setQuickStarting(false);
            setQuickOpen(false);
        }, 3000);
    };

    return (
        <ThemeProvider theme={theme}>
            <CssBaseline />
            <Box sx={{ minHeight: '100vh', bgcolor: 'background.default', pb: { xs: 3, md: 5 } }}>
                <HiveTopNav active="interviews" />

                <Container maxWidth="lg" sx={{ pt: { xs: 2.5, md: 4 } }}>
                    <Stack spacing={2.2}>
                        <Paper sx={{ p: { xs: 2, md: 2.5 } }}>
                            <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={1.2}>
                                <Box>
                                    <Typography variant="h4">Choose Interview Type</Typography>
                                    <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                        Select the exact interview style you want to practice.
                                    </Typography>
                                </Box>
                                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                                    <Chip size="small" label={isConnected ? 'Connected' : 'Connecting'} color={isConnected ? 'success' : 'default'} variant="outlined" />
                                    <Chip size="small" label={readinessPercent > 0 ? `Readiness ${readinessPercent}%` : 'Quick Start'} color={readinessPercent > 0 ? 'default' : 'info'} variant="outlined" />
                                    <Chip size="small" label={`${questionCount} questions`} variant="outlined" />
                                    <Chip size="small" label={activeStyle.title} color={selectedStyle === 'coach' ? 'secondary' : 'default'} variant="outlined" />
                                    <Chip size="small" label={activePersona.title} variant="outlined" />
                                </Stack>
                            </Stack>
                            <Divider sx={{ my: 1.4 }} />
                            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                Configuration: {targetRole || 'Not set'} {targetCompany ? `• ${targetCompany}` : ''}
                            </Typography>
                            {analysisProgress && (
                                <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                                    {analysisProgress}
                                </Typography>
                            )}
                        </Paper>

                        <Paper
                            sx={{
                                p: { xs: 2, md: 2.5 },
                                background: darkMode
                                    ? 'linear-gradient(135deg, rgba(245,158,11,0.12), rgba(251,191,36,0.04))'
                                    : 'linear-gradient(135deg, rgba(251,191,36,0.2), rgba(249,115,22,0.06))',
                            }}
                        >
                            <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1.2} sx={{ mb: 1.5 }}>
                                <Box>
                                    <Typography variant="h6">Session Style</Typography>
                                    <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                        Both modes grade at the end. Coach mode adds in-session guidance.
                                    </Typography>
                                </Box>
                                <Chip size="small" label="End-of-session grading" color="warning" variant="outlined" />
                            </Stack>

                            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 1.1 }}>
                                {INTERVIEW_STYLES.map((style) => {
                                    const Icon = style.icon;
                                    const selected = selectedStyle === style.id;
                                    return (
                                        <Paper
                                            key={style.id}
                                            onClick={() => setSelectedStyle(style.id)}
                                            role="button"
                                            tabIndex={0}
                                            onKeyDown={(event) => {
                                                if (event.key === 'Enter' || event.key === ' ') {
                                                    event.preventDefault();
                                                    setSelectedStyle(style.id);
                                                }
                                            }}
                                            sx={{
                                                p: 1.7,
                                                cursor: 'pointer',
                                                border: selected
                                                    ? '1px solid rgba(245, 158, 11, 0.72)'
                                                    : '1px solid rgba(245, 158, 11, 0.2)',
                                                boxShadow: selected
                                                    ? '0 0 0 1px rgba(245,158,11,0.3), 0 8px 20px rgba(245,158,11,0.16)'
                                                    : undefined,
                                            }}
                                        >
                                            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.8 }}>
                                                <Icon sx={{ color: selected ? 'primary.main' : 'text.secondary' }} />
                                                <Box>
                                                    <Typography variant="subtitle1" sx={{ fontWeight: 700, lineHeight: 1.15 }}>
                                                        {style.title}
                                                    </Typography>
                                                    <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                                                        {style.subtitle}
                                                    </Typography>
                                                </Box>
                                                {selected && <Chip size="small" label="Selected" color="primary" />}
                                            </Stack>
                                            <Typography variant="body2" sx={{ color: 'text.secondary', mb: 0.9 }}>
                                                {style.description}
                                            </Typography>
                                            <Stack spacing={0.4}>
                                                {style.bullets.map((point) => (
                                                    <Typography key={`${style.id}-${point}`} variant="caption" sx={{ color: 'text.secondary' }}>
                                                        • {point}
                                                    </Typography>
                                                ))}
                                            </Stack>
                                        </Paper>
                                    );
                                })}
                            </Box>
                        </Paper>

                        <Paper sx={{ p: { xs: 2, md: 2.5 } }}>
                            <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1.2} sx={{ mb: 1.2 }}>
                                <Box>
                                    <Typography variant="h6">Interviewer Persona</Typography>
                                    <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                        Choose how the interviewer behaves during the session.
                                    </Typography>
                                </Box>
                                <Chip size="small" label={`Active: ${activePersona.title}`} color="secondary" variant="outlined" />
                            </Stack>
                            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 0.9 }}>
                                {INTERVIEW_PERSONAS.map((persona) => {
                                    const Icon = persona.icon;
                                    const selected = selectedPersona === persona.id;
                                    return (
                                        <Paper
                                            key={persona.id}
                                            role="button"
                                            tabIndex={0}
                                            onClick={() => handlePersonaSelect(persona.id)}
                                            onKeyDown={(event) => {
                                                if (event.key === 'Enter' || event.key === ' ') {
                                                    event.preventDefault();
                                                    handlePersonaSelect(persona.id);
                                                }
                                            }}
                                            sx={{
                                                p: 1.2,
                                                cursor: 'pointer',
                                                border: selected
                                                    ? '1px solid rgba(245, 158, 11, 0.72)'
                                                    : '1px solid rgba(245, 158, 11, 0.2)',
                                                boxShadow: selected ? '0 0 0 1px rgba(245,158,11,0.25)' : undefined,
                                            }}
                                        >
                                            <Stack direction="row" spacing={1} alignItems="center">
                                                <Icon sx={{ color: selected ? 'primary.main' : 'text.secondary' }} />
                                                <Box sx={{ minWidth: 0 }}>
                                                    <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                                                        {persona.title}
                                                    </Typography>
                                                    <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                                                        {persona.description}
                                                    </Typography>
                                                </Box>
                                            </Stack>
                                        </Paper>
                                    );
                                })}
                            </Box>
                        </Paper>

                        {/* Quick Interview card — always visible */}
                        <Paper
                            sx={{
                                p: { xs: 2, md: 2.5 },
                                border: '1px solid',
                                borderColor: 'primary.main',
                                background: darkMode
                                    ? 'linear-gradient(135deg, rgba(99,102,241,0.12), rgba(139,92,246,0.04))'
                                    : 'linear-gradient(135deg, rgba(99,102,241,0.08), rgba(139,92,246,0.03))',
                            }}
                        >
                            <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} spacing={1.2}>
                                <Stack direction="row" spacing={1.2} alignItems="center">
                                    <BoltOutlined sx={{ color: 'primary.main', fontSize: 28 }} />
                                    <Box>
                                        <Typography variant="h6" sx={{ lineHeight: 1.2 }}>Quick Interview</Typography>
                                        <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                            Jump straight in with just a role and job description. No resume or analysis needed.
                                        </Typography>
                                    </Box>
                                </Stack>
                                <Button
                                    variant="contained"
                                    startIcon={<BoltOutlined />}
                                    onClick={openQuickDialog}
                                    disabled={!isConnected}
                                    sx={{ whiteSpace: 'nowrap', minWidth: 150 }}
                                >
                                    Start Quick Interview
                                </Button>
                            </Stack>
                        </Paper>

                        {!hasConfiguration && (
                            <Paper sx={{ p: 2 }}>
                                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                                    Full Interview (with Analysis)
                                </Typography>
                                <Typography variant="body2" sx={{ color: 'text.secondary', mb: 1.2 }}>
                                    For personalized questions based on your resume, set up your profile and run analysis first.
                                </Typography>
                                <Button variant="outlined" endIcon={<ArrowForward />} onClick={() => navigate('/config')}>
                                    Open Configuration
                                </Button>
                            </Paper>
                        )}

                        {error && (
                            <Typography variant="body2" color="error">
                                {error}
                            </Typography>
                        )}

                        {hasConfiguration && (
                            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 1.4 }}>
                                {INTERVIEW_TYPES.map((type) => {
                                    const Icon = type.icon;
                                    const isStarting = startingType === type.id;
                                    return (
                                        <Paper
                                            key={type.id}
                                            sx={{
                                                p: 2,
                                                border: '1px solid rgba(249, 115, 22, 0.18)',
                                                bgcolor: darkMode ? 'rgba(249, 115, 22, 0.06)' : 'rgba(249, 115, 22, 0.03)',
                                            }}
                                        >
                                            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.8 }}>
                                                <Icon sx={{ color: 'primary.main' }} />
                                                <Typography variant="h6">{type.title}</Typography>
                                            </Stack>
                                            <Typography variant="body2" sx={{ color: 'text.secondary', mb: 1.2 }}>
                                                {type.description}
                                            </Typography>
                                            <Stack direction="row" spacing={0.8} useFlexGap flexWrap="wrap" sx={{ mb: 1.4 }}>
                                                {type.tags.map((tag) => (
                                                    <Chip key={`${type.id}-${tag}`} size="small" label={tag} variant="outlined" />
                                                ))}
                                            </Stack>
                                            <Button
                                                variant="contained"
                                                startIcon={isStarting ? <CircularProgress size={14} color="inherit" /> : <PlayArrow />}
                                                onClick={() => handleStart(type)}
                                                disabled={isStarting || isAnalyzing}
                                            >
                                                {isStarting ? 'Starting...' : 'Start Interview'}
                                            </Button>
                                        </Paper>
                                    );
                                })}
                            </Box>
                        )}
                    </Stack>
                </Container>
            </Box>

            {/* Quick Interview Dialog */}
            <Dialog
                open={quickOpen}
                onClose={() => !quickStarting && setQuickOpen(false)}
                maxWidth="sm"
                fullWidth
            >
                <DialogTitle>
                    <Stack direction="row" justifyContent="space-between" alignItems="center">
                        <Stack direction="row" spacing={1} alignItems="center">
                            <BoltOutlined sx={{ color: 'primary.main' }} />
                            <span>Quick Interview</span>
                        </Stack>
                        <IconButton size="small" onClick={() => setQuickOpen(false)} disabled={quickStarting}>
                            <Close fontSize="small" />
                        </IconButton>
                    </Stack>
                </DialogTitle>
                <Divider />
                <DialogContent>
                    <Stack spacing={2.5} sx={{ pt: 1 }}>
                        <TextField
                            label="Target Role"
                            placeholder="e.g. Senior Backend Engineer"
                            value={quickRole}
                            onChange={(e) => setQuickRole(e.target.value)}
                            fullWidth
                            disabled={quickStarting}
                            autoFocus
                        />
                        <TextField
                            label="Job Description"
                            placeholder="Paste the job description here..."
                            value={quickJD}
                            onChange={(e) => setQuickJD(e.target.value)}
                            fullWidth
                            multiline
                            minRows={5}
                            maxRows={12}
                            disabled={quickStarting}
                        />
                        <Box>
                            <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>
                                Interview Type
                            </Typography>
                            <ToggleButtonGroup
                                value={quickType}
                                exclusive
                                onChange={(_, val) => val && setQuickType(val)}
                                size="small"
                                fullWidth
                                disabled={quickStarting}
                            >
                                {INTERVIEW_TYPES.map((t) => (
                                    <ToggleButton key={t.id} value={t.id} sx={{ textTransform: 'none', py: 1 }}>
                                        {t.title.replace(' Interview', '')}
                                    </ToggleButton>
                                ))}
                            </ToggleButtonGroup>
                        </Box>
                        {quickRole.trim() && quickJD.trim() && (
                            <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                                Style: {activeStyle.title} &bull; Persona: {activePersona.title} &bull; {questionCount} questions
                            </Typography>
                        )}
                    </Stack>
                </DialogContent>
                <Divider />
                <DialogActions sx={{ px: 3, py: 2 }}>
                    <Button onClick={() => setQuickOpen(false)} disabled={quickStarting}>
                        Cancel
                    </Button>
                    <Button
                        variant="contained"
                        size="large"
                        startIcon={quickStarting ? <CircularProgress size={16} color="inherit" /> : <PlayArrow />}
                        onClick={handleQuickStart}
                        disabled={!quickRole.trim() || !quickJD.trim() || quickStarting}
                    >
                        {quickStarting ? 'Starting...' : 'Start Interview'}
                    </Button>
                </DialogActions>
            </Dialog>
        </ThemeProvider>
    );
}
