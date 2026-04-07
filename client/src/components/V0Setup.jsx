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
} from '@mui/icons-material';
import { createHiveTheme } from '@/theme/hiveTheme';
import HiveTopNav from '@/components/ui/HiveTopNav';
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

    const handlePersonaSelect = (personaId) => {
        const normalized = normalizeQuickPersona(personaId);
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
            setError('Profile is incomplete. Set target role and job description first.');
            return;
        }
        setError('');

        const selectedSkillGaps = getSkillGapsForType(interviewType.id, skillMapping?.missing || []);
        setStartingType(interviewType.id);
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

    const handleQuickStart = () => {
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
                                    <Chip size="small" label="Mock Mode" variant="outlined" />
                                    <Chip size="small" label={activePersona.label} variant="outlined" />
                                </Stack>
                            </Stack>
                            <Divider sx={{ my: 1.4 }} />
                            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                Profile: {targetRole || 'Not set'} {targetCompany ? `• ${targetCompany}` : ''}
                            </Typography>
                            {analysisProgress && (
                                <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                                    {analysisProgress}
                                </Typography>
                            )}
                        </Paper>

                        <Paper sx={{ p: { xs: 2, md: 2.5 } }}>
                            <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1.2} sx={{ mb: 1.2 }}>
                                <Box>
                                    <Typography variant="h6">Interviewer Persona</Typography>
                                    <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                        Choose how the interviewer behaves during the session.
                                    </Typography>
                                </Box>
                                <Chip size="small" label={`Active: ${activePersona.label}`} color="secondary" variant="outlined" />
                            </Stack>
                            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 0.9 }}>
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
                                                        {persona.label}
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

                        {!hasConfiguration && (
                            <Paper sx={{ p: 2 }}>
                                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                                    Full Interview (with Analysis)
                                </Typography>
                                <Typography variant="body2" sx={{ color: 'text.secondary', mb: 1.2 }}>
                                    For personalized questions based on your resume, set up your profile and run analysis first.
                                </Typography>
                                <Button variant="outlined" endIcon={<ArrowForward />} onClick={() => navigate('/config')}>
                                    Open Profile
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
                                    const quickTypeMatch = QUICK_INTERVIEW_TYPES.find((item) => item.id === type.id);
                                    const Icon = quickTypeMatch?.icon;
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
                                                {Icon ? <Icon sx={{ color: 'primary.main' }} /> : null}
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

            <Dialog
                open={quickOpen}
                onClose={() => !quickStarting && setQuickOpen(false)}
                maxWidth="sm"
                fullWidth
            >
                <DialogTitle>
                    <Stack direction="row" justifyContent="space-between" alignItems="center">
                        <Stack direction="row" spacing={1} alignItems="center">
                            <BoltOutlined sx={{ color: '#6366f1' }} />
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
                                    background: 'linear-gradient(135deg, rgba(99,102,241,0.18), rgba(139,92,246,0.12))',
                                }}
                            >
                                <CircularProgress size={32} sx={{ color: '#8b5cf6' }} />
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
                                    background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                                    '&:hover': { background: 'linear-gradient(135deg, #4f46e5, #7c3aed)' },
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
