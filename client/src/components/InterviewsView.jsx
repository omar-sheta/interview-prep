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
    BoltOutlined,
    Close,
    AutoAwesome,
} from '@mui/icons-material';
import { createHiveTheme } from '@/theme/hiveTheme';
import HiveTopNav from '@/components/ui/HiveTopNav';
import SectionCard from '@/components/ui/SectionCard';
import { primeQuestionAudioPlayback } from '@/lib/questionAudio';
import {
    PERSONA_OPTIONS,
    QUICK_INTERVIEW_TYPES,
    QUICK_JOB_PRESETS,
    getQuickSkillGaps,
    normalizeQuickPersona,
    clampQuickQuestionCount,
} from '@/lib/quickInterviewConfig';

const INTERVIEW_TYPES = [
    {
        id: 'behavioral',
        title: 'Behavioral Interview',
        description: 'Practice leadership, conflict handling, communication, and STAR-style storytelling.',
        tags: ['STAR', 'Leadership', 'Communication'],
    },
    {
        id: 'technical',
        title: 'Technical Interview',
        description: 'Focus on implementation decisions, trade-offs, debugging, and applied technical reasoning.',
        tags: ['Problem Solving', 'Architecture', 'Debugging'],
    },
    {
        id: 'system_design',
        title: 'System Design Interview',
        description: 'Practice large-scale design prompts around scalability, reliability, and performance.',
        tags: ['Scalability', 'Reliability', 'Trade-offs'],
    },
    {
        id: 'mixed',
        title: 'Mixed Interview',
        description: 'Balanced flow across behavioral, technical, and design-style prompts.',
        tags: ['Balanced', 'Adaptive', 'General Prep'],
    },
];

function normalizeQuestionCount(value) {
    return clampQuickQuestionCount(value);
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

async function primeInterviewQuestionAudio() {
    try {
        await Promise.race([
            primeQuestionAudioPlayback(),
            new Promise((resolve) => window.setTimeout(resolve, 450)),
        ]);
    } catch (error) {
        console.warn('Question audio priming failed before interview start:', error);
    }
}

export default function InterviewsView() {
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
    const [selectedPersona, setSelectedPersona] = useState(normalizeQuickPersona(interviewerPersona));
    const [error, setError] = useState('');

    const [quickOpen, setQuickOpen] = useState(false);
    const [quickRole, setQuickRole] = useState('');
    const [quickJD, setQuickJD] = useState('');
    const [quickType, setQuickType] = useState('mixed');
    const [quickQuestionCount, setQuickQuestionCount] = useState('5');
    const [quickStarting, setQuickStarting] = useState(false);
    const activeQuickPresetId = useMemo(
        () => QUICK_JOB_PRESETS.find(
            (preset) =>
                String(quickRole || '').trim() === preset.jobTitle &&
                String(quickJD || '').trim() === preset.jobDescription
        )?.id || '',
        [quickRole, quickJD],
    );

    const openQuickDialog = () => {
        const nextRole = String(targetRole || '').trim();
        const nextJD = String(jobDescription || '').trim();
        const fallbackPreset = QUICK_JOB_PRESETS[0];
        setQuickRole(nextRole || fallbackPreset?.jobTitle || '');
        setQuickJD(nextJD || fallbackPreset?.jobDescription || '');
        setQuickQuestionCount(String(normalizeQuestionCount(questionCountOverride || 5)));
        setQuickOpen(true);
    };

    const applyQuickPreset = (preset) => {
        if (!preset) return;
        setQuickRole(preset.jobTitle);
        setQuickJD(preset.jobDescription);
    };

    useEffect(() => {
        connect();
    }, [connect]);

    useEffect(() => {
        setSelectedPersona(normalizeQuickPersona(interviewerPersona));
    }, [interviewerPersona]);

    useEffect(() => {
        if (appState === APP_STATES.INTERVIEWING) {
            setStartingType(null);
            setQuickStarting(false);
            setQuickOpen(false);
            return;
        }

        if (appState !== APP_STATES.ANALYZING) {
            setStartingType(null);
            setQuickStarting(false);
        }
    }, [appState]);

    const theme = useMemo(() => createHiveTheme(darkMode ? 'dark' : 'light'), [darkMode]);
    const readinessPercent = Math.round(Math.max(0, Math.min(1, Number(readinessScore || 0))) * 100);
    const isAnalyzing = appState === APP_STATES.ANALYZING;
    const hasConfiguration = String(targetRole || '').trim() && String(jobDescription || '').trim();
    const questionCount = normalizeQuestionCount(questionCountOverride || 5);
    const activePersona = PERSONA_OPTIONS.find((persona) => persona.id === selectedPersona) || PERSONA_OPTIONS[0];
    const recommendedType = INTERVIEW_TYPES.find((type) => type.id === 'mixed') || INTERVIEW_TYPES[0];

    const handlePersonaSelect = (personaId) => {
        const normalized = normalizeQuickPersona(personaId);
        setSelectedPersona(normalized);
        setInterviewerPersona(normalized);
        savePreferences({ interviewer_persona: normalized });
    };

    const handleStart = async (interviewType) => {
        if (!isConnected) {
            setError('Not connected to server yet. Please try again in a moment.');
            return;
        }

        if (!hasConfiguration) {
            setError('Profile is incomplete. Set target role and job description first.');
            return;
        }
        setError('');

        const selectedSkillGaps = getSkillGapsForType(interviewType.id, skillMapping?.missing || []);
        setStartingType(interviewType.id);
        await primeInterviewQuestionAudio();
        startInterview({
            job_title: String(targetRole || '').trim(),
            skill_gaps: selectedSkillGaps,
            readiness_score: readinessScore || 0.5,
            job_description: String(jobDescription || '').trim(),
            interview_type: interviewType.id,
            mode: 'practice',
            coaching_enabled: false,
            feedback_timing: 'end_only',
            live_scoring: false,
            interviewer_persona: selectedPersona,
            question_count: questionCount,
        });
    };

    const handleQuickStart = async () => {
        const role = quickRole.trim();
        const jd = quickJD.trim();
        if (!role || !jd) return;
        if (!isConnected) {
            setError('Not connected to server yet. Please try again in a moment.');
            return;
        }
        setError('');

        const qCount = normalizeQuestionCount(quickQuestionCount || 5);
        setQuickStarting(true);
        await primeInterviewQuestionAudio();
        startInterview({
            job_title: role,
            skill_gaps: getQuickSkillGaps(quickType),
            readiness_score: 0.5,
            job_description: jd,
            interview_type: quickType,
            mode: 'practice',
            coaching_enabled: false,
            feedback_timing: 'end_only',
            live_scoring: false,
            interviewer_persona: selectedPersona,
            question_count: qCount,
        });
    };

    return (
        <ThemeProvider theme={theme}>
            <CssBaseline />
            <Box sx={{ minHeight: '100vh', bgcolor: 'background.default', pb: { xs: 3, md: 5 } }}>
                <HiveTopNav
                    active="interviews"
                    quickActionLabel="Quick Interview"
                    quickActionIcon={<BoltOutlined />}
                    onQuickAction={openQuickDialog}
                />

                <Container maxWidth="xl" sx={{ pt: { xs: 3.5, sm: 3, md: 4 } }}>
                    <Stack spacing={{ xs: 2.4, md: 3 }}>
                        <Paper
                            sx={{
                                position: 'relative',
                                overflow: 'hidden',
                                borderRadius: { xs: 4, md: 6 },
                                p: { xs: 2.6, md: 4.5 },
                                minHeight: { md: 360 },
                                color: '#FFF8ED',
                                border: '1px solid rgba(255,255,255,0.12)',
                                background:
                                    'radial-gradient(circle at 78% 18%, rgba(255,154,77,0.36), transparent 28%), radial-gradient(circle at 16% 92%, rgba(246,161,0,0.2), transparent 26%), linear-gradient(135deg, #111827 0%, #1D2430 42%, #3A1D12 100%)',
                                boxShadow: darkMode
                                    ? '0 34px 90px rgba(0,0,0,0.55)'
                                    : '0 34px 90px rgba(80,52,22,0.22)',
                                '&::before': {
                                    content: '""',
                                    position: 'absolute',
                                    inset: 0,
                                    backgroundImage:
                                        'linear-gradient(rgba(255,255,255,0.055) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.04) 1px, transparent 1px)',
                                    backgroundSize: '42px 42px',
                                    maskImage: 'linear-gradient(90deg, black, transparent 78%)',
                                    pointerEvents: 'none',
                                },
                            }}
                        >
                            <Stack
                                direction={{ xs: 'column', md: 'row' }}
                                justifyContent="space-between"
                                alignItems={{ xs: 'stretch', md: 'center' }}
                                spacing={{ xs: 3, md: 5 }}
                                sx={{ position: 'relative', zIndex: 1 }}
                            >
                                <Box sx={{ maxWidth: 760 }}>
                                    <Chip
                                        icon={<AutoAwesome />}
                                        label={isConnected ? 'Live AI interview console' : 'Connecting interview engine'}
                                        sx={{
                                            mb: 2.2,
                                            color: '#FFF8ED',
                                            bgcolor: 'rgba(255,255,255,0.1)',
                                            border: '1px solid rgba(255,255,255,0.16)',
                                            '& .MuiChip-icon': { color: '#FFD36A' },
                                        }}
                                    />
                                    <Typography variant="h3" sx={{ maxWidth: 690 }}>
                                        Practice like the interview is already real.
                                    </Typography>
                                    <Typography
                                        variant="body1"
                                        sx={{ color: 'rgba(255,248,237,0.76)', mt: 2, maxWidth: 650, fontSize: { md: '1.06rem' } }}
                                    >
                                        {hasConfiguration
                                            ? `${targetRole}${targetCompany ? ` at ${targetCompany}` : ''}. ${questionCount} focused questions with the ${activePersona.label.toLowerCase()} interviewer.`
                                            : 'Launch a polished quick mock now, or add your profile once for sharper, resume-aware practice.'}
                                    </Typography>
                                    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.2} sx={{ mt: 3, maxWidth: { xs: '100%', sm: 560 } }}>
                                        <Button
                                            variant="contained"
                                            size="large"
                                            startIcon={isAnalyzing || startingType === recommendedType.id ? <CircularProgress size={16} color="inherit" /> : <PlayArrow />}
                                            onClick={() => hasConfiguration ? handleStart(recommendedType) : openQuickDialog('mixed')}
                                            disabled={isAnalyzing || startingType === recommendedType.id}
                                            fullWidth
                                            sx={{
                                                minHeight: 54,
                                                background: 'linear-gradient(135deg, #FFD36A 0%, #FF6A1A 62%, #E1420B 100%)',
                                                color: '#17110D',
                                                boxShadow: '0 18px 42px rgba(255,106,26,0.32)',
                                                '&:hover': {
                                                    background: 'linear-gradient(135deg, #FFE19A 0%, #FF6A1A 62%, #C93407 100%)',
                                                },
                                            }}
                                        >
                                            {hasConfiguration ? 'Start Mock Interview' : 'Start Quick Mock'}
                                        </Button>
                                        <Button
                                            variant="outlined"
                                            size="large"
                                            onClick={() => navigate('/config')}
                                            fullWidth
                                            sx={{
                                                minHeight: 54,
                                                color: '#FFF8ED',
                                                borderColor: 'rgba(255,255,255,0.28)',
                                                bgcolor: 'rgba(255,255,255,0.06)',
                                                '&:hover': {
                                                    borderColor: '#FFD36A',
                                                    bgcolor: 'rgba(255,255,255,0.11)',
                                                },
                                            }}
                                        >
                                            Refine Profile
                                        </Button>
                                    </Stack>
                                </Box>

                                <Paper
                                    sx={{
                                        width: { xs: '100%', md: 310 },
                                        p: 2.2,
                                        borderRadius: 5,
                                        color: '#FFF8ED',
                                        bgcolor: 'rgba(255,255,255,0.08)',
                                        border: '1px solid rgba(255,255,255,0.16)',
                                        backdropFilter: 'blur(20px)',
                                        boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.1)',
                                    }}
                                >
                                    <Typography variant="caption" sx={{ color: 'rgba(255,248,237,0.62)', fontWeight: 800, letterSpacing: '0.16em' }}>
                                        SESSION READINESS
                                    </Typography>
                                    <Stack direction="row" alignItems="flex-end" spacing={1} sx={{ mt: 1 }}>
                                        <Typography variant="h3">{readinessPercent || '--'}</Typography>
                                        <Typography variant="h6" sx={{ color: 'rgba(255,248,237,0.62)', mb: 0.8 }}>%</Typography>
                                    </Stack>
                                    <Divider sx={{ my: 2, borderColor: 'rgba(255,255,255,0.12)' }} />
                                    <Stack spacing={1.2}>
                                        {[
                                            ['Questions', questionCount],
                                            ['Style', activePersona.label],
                                            ['Status', isConnected ? 'Connected' : 'Connecting'],
                                        ].map(([label, value]) => (
                                            <Stack key={label} direction="row" justifyContent="space-between" spacing={2}>
                                                <Typography variant="body2" sx={{ color: 'rgba(255,248,237,0.62)' }}>{label}</Typography>
                                                <Typography variant="body2" sx={{ fontWeight: 800 }}>{value}</Typography>
                                            </Stack>
                                        ))}
                                    </Stack>
                                </Paper>
                            </Stack>
                            {analysisProgress && (
                                <Typography variant="caption" sx={{ color: 'rgba(255,248,237,0.6)', display: 'block', mt: 2.4, position: 'relative', zIndex: 1 }}>
                                    {analysisProgress}
                                </Typography>
                            )}
                        </Paper>

                        <SectionCard
                            title="Interviewer Style"
                            description="Choose the room you want to walk into. This should feel like a setting, not a form."
                            sx={{ p: { xs: 2.2, md: 2.6 } }}
                        >
                            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 1.3 }}>
                                {PERSONA_OPTIONS.map((persona) => {
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
                                                p: 1.8,
                                                borderRadius: 4,
                                                cursor: 'pointer',
                                                bgcolor: selected
                                                    ? (darkMode ? 'rgba(255,106,26,0.16)' : 'rgba(255,106,26,0.08)')
                                                    : (darkMode ? 'rgba(255,255,255,0.035)' : 'rgba(255,255,255,0.72)'),
                                                border: selected
                                                    ? '1px solid rgba(255, 106, 26, 0.58)'
                                                    : '1px solid rgba(24, 32, 44, 0.08)',
                                                boxShadow: selected ? '0 18px 44px rgba(255,106,26,0.12)' : 'none',
                                                transition: 'transform 160ms ease, border-color 160ms ease, box-shadow 160ms ease',
                                                '&:hover': {
                                                    transform: 'translateY(-2px)',
                                                    borderColor: 'rgba(255, 106, 26, 0.5)',
                                                },
                                            }}
                                        >
                                            <Stack direction="row" spacing={1.4} alignItems="center">
                                                <Box
                                                    sx={{
                                                        width: 44,
                                                        height: 44,
                                                        borderRadius: 3,
                                                        display: 'grid',
                                                        placeItems: 'center',
                                                        color: selected ? '#FFFFFF' : 'primary.main',
                                                        background: selected
                                                            ? 'linear-gradient(135deg, #18202C, #FF6A1A)'
                                                            : (darkMode ? 'rgba(255,255,255,0.06)' : 'rgba(255,106,26,0.08)'),
                                                    }}
                                                >
                                                    <Icon />
                                                </Box>
                                                <Box sx={{ minWidth: 0 }}>
                                                    <Typography variant="subtitle1">
                                                        {persona.label}
                                                    </Typography>
                                                    <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.2 }}>
                                                        {persona.description}
                                                    </Typography>
                                                </Box>
                                            </Stack>
                                        </Paper>
                                    );
                                })}
                            </Box>
                        </SectionCard>

                        {!hasConfiguration && (
                            <SectionCard
                                title="Want personalized questions?"
                                description="Add your resume and job description once, then BeePrepared can generate targeted sessions from your actual gaps."
                                action={(
                                    <Button variant="outlined" endIcon={<ArrowForward />} onClick={() => navigate('/config')}>
                                        Open Profile
                                    </Button>
                                )}
                            />
                        )}

                        {error && (
                            <Typography variant="body2" color="error">
                                {error}
                            </Typography>
                        )}

                        {hasConfiguration && (
                            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: { xs: 1.6, md: 2 } }}>
                                {INTERVIEW_TYPES.map((type) => {
                                    const quickTypeMatch = QUICK_INTERVIEW_TYPES.find((item) => item.id === type.id);
                                    const Icon = quickTypeMatch?.icon;
                                    const isStarting = startingType === type.id;
                                    const isRecommended = type.id === 'mixed';
                                    return (
                                        <Paper
                                            key={type.id}
                                            role="button"
                                            tabIndex={0}
                                            onClick={() => !isStarting && !isAnalyzing && handleStart(type)}
                                            onKeyDown={(event) => {
                                                if ((event.key === 'Enter' || event.key === ' ') && !isStarting && !isAnalyzing) {
                                                    event.preventDefault();
                                                    handleStart(type);
                                                }
                                            }}
                                            sx={{
                                                p: { xs: 2.2, md: 2.8 },
                                                minHeight: 260,
                                                display: 'flex',
                                                flexDirection: 'column',
                                                justifyContent: 'space-between',
                                                cursor: isStarting || isAnalyzing ? 'default' : 'pointer',
                                                position: 'relative',
                                                overflow: 'hidden',
                                                border: isRecommended
                                                    ? '1px solid rgba(255, 106, 26, 0.38)'
                                                    : '1px solid rgba(24, 32, 44, 0.08)',
                                                bgcolor: darkMode ? 'rgba(255,255,255,0.035)' : 'rgba(255,255,255,0.68)',
                                                transition: 'transform 180ms ease, border-color 180ms ease, box-shadow 180ms ease, background 180ms ease',
                                                '&::before': {
                                                    content: '""',
                                                    position: 'absolute',
                                                    top: 0,
                                                    left: 0,
                                                    right: 0,
                                                    height: 4,
                                                    background: isRecommended
                                                        ? 'linear-gradient(90deg, #FFD36A, #FF6A1A)'
                                                        : 'linear-gradient(90deg, rgba(24,32,44,0.14), rgba(24,32,44,0.02))',
                                                },
                                                '&:hover': isStarting || isAnalyzing ? {} : {
                                                    transform: 'translateY(-5px)',
                                                    borderColor: 'rgba(255, 106, 26, 0.5)',
                                                    boxShadow: darkMode
                                                        ? '0 26px 60px rgba(0,0,0,0.42)'
                                                        : '0 26px 60px rgba(80,52,22,0.13)',
                                                },
                                            }}
                                        >
                                            <Box>
                                                <Stack direction="row" justifyContent="space-between" spacing={2} alignItems="flex-start" sx={{ mb: 2 }}>
                                                    <Stack direction="row" spacing={1.25} alignItems="center">
                                                        <Box
                                                            sx={{
                                                                width: 46,
                                                                height: 46,
                                                                borderRadius: 3,
                                                                display: 'grid',
                                                                placeItems: 'center',
                                                                color: isRecommended ? '#FFFFFF' : 'primary.main',
                                                                background: isRecommended
                                                                    ? 'linear-gradient(135deg, #18202C, #FF6A1A)'
                                                                    : (darkMode ? 'rgba(255,255,255,0.06)' : 'rgba(255,106,26,0.08)'),
                                                            }}
                                                        >
                                                            {Icon ? <Icon /> : <PlayArrow />}
                                                        </Box>
                                                        <Typography variant="h6">{type.title}</Typography>
                                                    </Stack>
                                                    {isRecommended && (
                                                        <Chip size="small" label="Recommended" color="primary" />
                                                    )}
                                                </Stack>
                                                <Typography variant="body2" sx={{ color: 'text.secondary', mb: 2 }}>
                                                    {type.description}
                                                </Typography>
                                                <Stack direction="row" spacing={0.8} useFlexGap flexWrap="wrap">
                                                    {type.tags.map((tag) => (
                                                        <Chip key={`${type.id}-${tag}`} size="small" label={tag} variant="outlined" />
                                                    ))}
                                                </Stack>
                                            </Box>
                                            <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
                                                <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                                                    {questionCount} questions
                                                </Typography>
                                                <Button
                                                    variant="contained"
                                                    startIcon={isStarting ? <CircularProgress size={14} color="inherit" /> : <PlayArrow />}
                                                    onClick={(event) => {
                                                        event.stopPropagation();
                                                        handleStart(type);
                                                    }}
                                                    disabled={isStarting || isAnalyzing}
                                                    sx={{ minWidth: 116 }}
                                                >
                                                    {isStarting ? 'Starting...' : 'Begin'}
                                                </Button>
                                            </Stack>
                                        </Paper>
                                    );
                                })}
                            </Box>
                        )}
                    </Stack>
                </Container>
            </Box>

            <Dialog
                open={quickOpen}
                onClose={() => !quickStarting && setQuickOpen(false)}
                maxWidth="sm"
                fullWidth
            >
                <DialogTitle>
                    <Stack direction="row" justifyContent="space-between" alignItems="center">
                        <Stack direction="row" spacing={1} alignItems="center">
                            <BoltOutlined sx={{ color: '#FF6A1A' }} />
                            <span>Quick Interview</span>
                        </Stack>
                        <IconButton size="small" onClick={() => setQuickOpen(false)} disabled={quickStarting}>
                            <Close fontSize="small" />
                        </IconButton>
                    </Stack>
                </DialogTitle>
                <Divider />
                <DialogContent>
                    {quickStarting ? (
                        <Stack
                            spacing={2}
                            alignItems="center"
                            justifyContent="center"
                            sx={{ py: { xs: 5, md: 7 }, minHeight: 280 }}
                        >
                            <Box
                                sx={{
                                    width: 64,
                                    height: 64,
                                    borderRadius: '50%',
                                    display: 'grid',
                                    placeItems: 'center',
                                    background: 'linear-gradient(135deg, rgba(255,190,69,0.2), rgba(255,106,26,0.14))',
                                }}
                            >
                                <CircularProgress size={32} sx={{ color: '#FF6A1A' }} />
                            </Box>
                            <Typography variant="h6" sx={{ fontWeight: 700 }}>
                                Creating Interview…
                            </Typography>
                            <Typography variant="body2" sx={{ color: 'text.secondary', textAlign: 'center', maxWidth: 340 }}>
                                Generating {QUICK_INTERVIEW_TYPES.find((t) => t.id === quickType)?.title || 'Mixed'} questions for <strong>{quickRole.trim()}</strong>. This usually takes a few seconds.
                            </Typography>
                        </Stack>
                    ) : (
                        <Stack spacing={2.5} sx={{ pt: 1 }}>
                            <Box>
                                <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>
                                    Demo Roles
                                </Typography>
                                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                                    {QUICK_JOB_PRESETS.map((preset) => (
                                        <Chip
                                            key={preset.id}
                                            label={preset.title}
                                            clickable
                                            color={activeQuickPresetId === preset.id ? 'primary' : 'default'}
                                            variant={activeQuickPresetId === preset.id ? 'filled' : 'outlined'}
                                            onClick={() => applyQuickPreset(preset)}
                                        />
                                    ))}
                                </Stack>
                            </Box>
                            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1.5fr 0.7fr' }, gap: 1.2 }}>
                                <TextField
                                    label="Target Role"
                                    placeholder="e.g. Senior Backend Engineer"
                                    value={quickRole}
                                    onChange={(e) => setQuickRole(e.target.value)}
                                    fullWidth
                                    autoFocus
                                />
                                <TextField
                                    label="Question Count"
                                    type="number"
                                    value={quickQuestionCount}
                                    onChange={(e) => setQuickQuestionCount(e.target.value)}
                                    inputProps={{ min: 1, max: 12 }}
                                    fullWidth
                                />
                            </Box>
                            <TextField
                                label="Job Description"
                                placeholder="Paste the job description here..."
                                value={quickJD}
                                onChange={(e) => setQuickJD(e.target.value)}
                                fullWidth
                                multiline
                                minRows={5}
                                maxRows={12}
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
                                >
                                    {QUICK_INTERVIEW_TYPES.map((t) => (
                                        <ToggleButton key={t.id} value={t.id} sx={{ textTransform: 'none', py: 1 }}>
                                            {t.title}
                                        </ToggleButton>
                                    ))}
                                </ToggleButtonGroup>
                            </Box>
                            {quickRole.trim() && quickJD.trim() && (
                                <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                                    Mock mode &bull; {activePersona.label} persona &bull; {normalizeQuestionCount(quickQuestionCount || 5)} questions
                                </Typography>
                            )}
                        </Stack>
                    )}
                </DialogContent>
                {!quickStarting && (
                    <>
                        <Divider />
                        <DialogActions sx={{ px: 3, py: 2 }}>
                            <Button onClick={() => setQuickOpen(false)}>
                                Cancel
                            </Button>
                            <Button
                                variant="contained"
                                size="large"
                                startIcon={<PlayArrow />}
                                onClick={handleQuickStart}
                                disabled={!quickRole.trim() || !quickJD.trim()}
                                sx={{
                                    background: 'linear-gradient(135deg, #18202C, #FF6A1A)',
                                    '&:hover': { background: 'linear-gradient(135deg, #0F1723, #E1420B)' },
                                }}
                            >
                                Start Interview
                            </Button>
                        </DialogActions>
                    </>
                )}
            </Dialog>
        </ThemeProvider>
    );
}
