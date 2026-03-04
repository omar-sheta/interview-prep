import { useEffect, useMemo, useState } from 'react';
import useInterviewStore, { APP_STATES } from '@/store/useInterviewStore';
import PDFDropzone from '@/components/PDFDropzone';
import {
    ThemeProvider,
    CssBaseline,
    Box,
    Container,
    Paper,
    Stack,
    Typography,
    TextField,
    Button,
    Chip,
    Divider,
    CircularProgress,
    LinearProgress,
    Tooltip,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    FormControl,
    InputLabel,
    Select,
    MenuItem,
    ToggleButtonGroup,
    ToggleButton,
    IconButton,
} from '@mui/material';
import {
    PlayArrow,
    Save,
    UploadFile,
    DeleteSweep,
    CheckCircleOutline,
    ErrorOutline,
    HelpOutline,
    TrendingUp,
    AutoGraph,
    TipsAndUpdates,
    Diversity3,
    Gavel,
    BoltOutlined,
    Psychology,
    Code,
    AccountTree,
    AutoAwesome,
    Close,
} from '@mui/icons-material';
import { createHiveTheme } from '@/theme/hiveTheme';
import HiveTopNav from '@/components/ui/HiveTopNav';

const PERSONA_OPTIONS = [
    {
        id: 'friendly',
        label: 'Friendly',
        icon: Diversity3,
        description: 'Supportive tone, clear prompts, and collaborative pacing.',
    },
    {
        id: 'strict',
        label: 'Strict',
        icon: Gavel,
        description: 'High bar, direct wording, and precision-focused follow-ups.',
    },
];

const QUICK_INTERVIEW_TYPES = [
    {
        id: 'behavioral',
        title: 'Behavioral',
        description: 'STAR-style storytelling, leadership, and communication.',
        icon: Psychology,
        tags: ['STAR', 'Leadership'],
    },
    {
        id: 'technical',
        title: 'Technical',
        description: 'Implementation decisions, trade-offs, and debugging.',
        icon: Code,
        tags: ['Problem Solving', 'Architecture'],
    },
    {
        id: 'system_design',
        title: 'System Design',
        description: 'Scalability, reliability, and large-scale design.',
        icon: AccountTree,
        tags: ['Scalability', 'Trade-offs'],
    },
    {
        id: 'mixed',
        title: 'Mixed',
        description: 'Balanced flow across behavioral, technical, and design.',
        icon: AutoAwesome,
        tags: ['Balanced', 'Adaptive'],
    },
];

function getQuickSkillGaps(interviewType) {
    if (interviewType === 'behavioral') return ['communication', 'stakeholder management', 'leadership', 'conflict resolution'];
    if (interviewType === 'technical') return ['technical fundamentals', 'problem solving', 'debugging'];
    if (interviewType === 'system_design') return ['system design', 'scalability', 'reliability', 'trade-offs'];
    return [];
}

function clampQuestionCount(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return null;
    const intValue = Math.trunc(n);
    if (intValue < 1) return null;
    return Math.min(12, intValue);
}

function clamp01(value, fallback = 0) {
    const n = Number(value);
    if (!Number.isFinite(n)) return fallback;
    return Math.max(0, Math.min(1, n));
}

function statusMeta(statusRaw) {
    const value = String(statusRaw || '').trim().toLowerCase();
    if (value === 'strong') return { key: 'strong', label: 'Strong', color: 'success', rank: 5, icon: CheckCircleOutline };
    if (value === 'meets') return { key: 'meets', label: 'Meets', color: 'success', rank: 4, icon: CheckCircleOutline };
    if (value === 'borderline') return { key: 'borderline', label: 'Borderline', color: 'warning', rank: 3, icon: HelpOutline };
    if (value === 'uncertain') return { key: 'uncertain', label: 'Uncertain', color: 'warning', rank: 2, icon: HelpOutline };
    return { key: 'missing', label: 'Missing', color: 'error', rank: 1, icon: ErrorOutline };
}

function toSkillLabel(item) {
    if (typeof item === 'string') return item;
    if (item && typeof item === 'object') {
        return item.skill || item.name || item.label || item.title || '';
    }
    return '';
}

function normalizeSkillBoard(skillMapping) {
    const rawBoard = Array.isArray(skillMapping?.coverage_board) ? skillMapping.coverage_board : [];
    if (rawBoard.length > 0) {
        return rawBoard.map((row, index) => {
            const status = statusMeta(row?.status);
            const importance = clamp01(row?.importance, 0.5);
            return {
                id: `${row?.skill || row?.name || 'skill'}-${index}`,
                skill: row?.skill || row?.name || 'Unknown Skill',
                name: row?.name || row?.skill || 'Unknown Skill',
                priority: row?.priority || 'must_have',
                requiredLevel: row?.required_level || 'intermediate',
                candidateLevel: row?.candidate_level || 'none',
                status,
                confidence: clamp01(row?.confidence, 0),
                importance,
                reason: row?.reason || '',
                learningTip: row?.learning_tip || '',
                jdEvidence: row?.evidence_required || '',
                candidateEvidence: Array.isArray(row?.evidence_candidate) ? row.evidence_candidate : [],
            };
        });
    }

    const fallbackRows = [];
    const pushRows = (items, statusValue, confidence, requiredLevel = 'intermediate', candidateLevel = 'intermediate') => {
        const list = Array.isArray(items) ? items : [];
        for (const item of list) {
            const label = String(toSkillLabel(item) || '').trim();
            if (!label) continue;
            fallbackRows.push({
                id: `${label}-${statusValue}`,
                skill: label,
                name: label,
                priority: 'must_have',
                requiredLevel,
                candidateLevel,
                status: statusMeta(statusValue),
                confidence: clamp01(item?.confidence, confidence),
                importance: clamp01(item?.importance, 0.5),
                reason: item?.reason || '',
                learningTip: item?.learning_tip || '',
                jdEvidence: item?.evidence_required || '',
                candidateEvidence: Array.isArray(item?.evidence_candidate) ? item.evidence_candidate : [],
            });
        }
    };

    pushRows(skillMapping?.matched, 'meets', 0.85, 'intermediate', 'advanced');
    pushRows(skillMapping?.partial, 'borderline', 0.55, 'intermediate', 'intermediate');
    pushRows(skillMapping?.missing, 'missing', 0.25, 'intermediate', 'none');
    return fallbackRows;
}

function summarizeCoverage(skillMapping, skillBoard) {
    const summary = skillMapping?.coverage_summary;
    if (summary && typeof summary === 'object') {
        return {
            mustHave: clamp01(summary.must_have_coverage, 0),
            niceToHave: clamp01(summary.nice_to_have_coverage, 0),
            requiredCount: Number(summary.required_skills_count || skillBoard.length || 0),
            candidateCount: Number(summary.candidate_skills_count || skillMapping?.candidate_skills?.length || 0),
        };
    }

    const rows = Array.isArray(skillBoard) ? skillBoard : [];
    const requiredCount = rows.length;
    const coveredCount = rows.filter((row) => row?.status?.key === 'strong' || row?.status?.key === 'meets').length;
    const candidateCountFallback = Number(skillMapping?.candidate_skills?.length || 0);
    const partialCount = Array.isArray(skillMapping?.partial) ? skillMapping.partial.length : 0;
    const matchedCount = Array.isArray(skillMapping?.matched) ? skillMapping.matched.length : coveredCount;
    return {
        mustHave: requiredCount > 0 ? coveredCount / requiredCount : 0,
        niceToHave: requiredCount > 0 ? coveredCount / requiredCount : 0,
        requiredCount,
        candidateCount: candidateCountFallback || (matchedCount + partialCount),
    };
}

export default function ConfigurationView() {
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
        jobDescription: storedJobDescription,
        questionCountOverride,
        interviewerPersona,
        ttsProvider,
        startCareerAnalysis,
        startInterview,
        setTargetJob,
        setTargetCompany,
        setInterviewerPersona,
        setTtsProvider,
        savePreferences,
        loadPreferences,
        loadLatestAnalysis,
        clearConfiguration,
    } = useInterviewStore();

    const theme = useMemo(() => createHiveTheme(darkMode ? 'dark' : 'light'), [darkMode]);
    const isAnalyzing = appState === APP_STATES.ANALYZING;
    const readinessPercent = Math.round(Math.max(0, Math.min(1, Number(readinessScore || 0))) * 100);

    const [jobTitle, setJobTitle] = useState(targetRole || '');
    const [company, setCompany] = useState(targetCompany || '');
    const [jobDescription, setJobDescription] = useState(storedJobDescription || '');
    const [questionCount, setQuestionCount] = useState(
        questionCountOverride !== null && questionCountOverride !== undefined ? String(questionCountOverride) : '5'
    );
    const [defaultPersona, setDefaultPersona] = useState(interviewerPersona || 'friendly');
    const [voiceEngine, setVoiceEngine] = useState('piper');
    const [resumeBase64, setResumeBase64] = useState('');
    const [resumeFilename, setResumeFilename] = useState('');
    const [status, setStatus] = useState('');
    const [error, setError] = useState('');
    const [skillFilter, setSkillFilter] = useState('actionable');
    const [selectedSkillId, setSelectedSkillId] = useState('');
    const [clearDialogOpen, setClearDialogOpen] = useState(false);

    // Quick Interview state
    const [quickOpen, setQuickOpen] = useState(false);
    const [quickRole, setQuickRole] = useState('');
    const [quickJD, setQuickJD] = useState('');
    const [quickType, setQuickType] = useState('mixed');
    const [quickStarting, setQuickStarting] = useState(false);

    useEffect(() => {
        connect();
    }, [connect]);

    useEffect(() => {
        if (isConnected) {
            loadPreferences();
            loadLatestAnalysis();
        }
    }, [isConnected, loadPreferences, loadLatestAnalysis]);

    useEffect(() => {
        setJobTitle(targetRole || '');
    }, [targetRole]);

    useEffect(() => {
        setCompany(targetCompany || '');
    }, [targetCompany]);

    useEffect(() => {
        setJobDescription(storedJobDescription || '');
    }, [storedJobDescription]);

    // Dismiss the quick-interview overlay once the session is live
    useEffect(() => {
        if (quickStarting && appState === APP_STATES.INTERVIEWING) {
            setQuickStarting(false);
            setQuickOpen(false);
        }
    }, [appState, quickStarting]);

    useEffect(() => {
        if (questionCountOverride === null || questionCountOverride === undefined) return;
        setQuestionCount(String(questionCountOverride));
    }, [questionCountOverride]);

    useEffect(() => {
        const allowed = new Set(PERSONA_OPTIONS.map((option) => option.id));
        const normalized = String(interviewerPersona || '').trim().toLowerCase();
        setDefaultPersona(allowed.has(normalized) ? normalized : 'friendly');
    }, [interviewerPersona]);

    useEffect(() => {
        const next = String(ttsProvider || 'piper').trim().toLowerCase();
        const allowed = new Set(['piper', 'qwen3_tts_mlx']);
        setVoiceEngine(allowed.has(next) ? next : 'piper');
    }, [ttsProvider]);

    const skillBoard = useMemo(() => normalizeSkillBoard(skillMapping), [skillMapping]);
    const coverage = useMemo(
        () => summarizeCoverage(skillMapping, skillBoard),
        [skillMapping, skillBoard],
    );

    const filteredBoard = useMemo(() => {
        const rows = [...skillBoard];
        rows.sort((a, b) => {
            if (b.importance !== a.importance) return b.importance - a.importance;
            if (a.status.rank !== b.status.rank) return a.status.rank - b.status.rank;
            return a.name.localeCompare(b.name);
        });

        if (skillFilter === 'all') return rows;
        if (skillFilter === 'must') return rows.filter((row) => row.priority === 'must_have');
        if (skillFilter === 'strong') return rows.filter((row) => row.status.key === 'strong' || row.status.key === 'meets');
        return rows.filter((row) => row.status.key === 'missing' || row.status.key === 'uncertain' || row.status.key === 'borderline');
    }, [skillBoard, skillFilter]);

    const followupTargets = Array.isArray(skillMapping?.followup_targets) ? skillMapping.followup_targets.slice(0, 3) : [];
    const followupQuestions = Array.isArray(skillMapping?.followup_questions) ? skillMapping.followup_questions.slice(0, 4) : [];

    useEffect(() => {
        if (filteredBoard.length === 0) {
            if (selectedSkillId) setSelectedSkillId('');
            return;
        }
        if (!filteredBoard.some((row) => row.id === selectedSkillId)) {
            setSelectedSkillId(filteredBoard[0].id);
        }
    }, [filteredBoard, selectedSkillId]);

    const selectedSkill = filteredBoard.find((row) => row.id === selectedSkillId) || null;

    const saveConfig = () => {
        const normalizedCount = clampQuestionCount(questionCount);
        if (questionCount.trim() && normalizedCount === null) {
            setError('Question count must be a number between 1 and 12.');
            return false;
        }

        setError('');
        const normalizedRole = String(jobTitle || '').trim();
        const normalizedCompany = String(company || '').trim();
        const normalizedDescription = String(jobDescription || '').trim();
        const allowedPersona = new Set(PERSONA_OPTIONS.map((option) => option.id));
        const normalizedPersona = allowedPersona.has(String(defaultPersona || '').trim().toLowerCase())
            ? String(defaultPersona).trim().toLowerCase()
            : 'friendly';

        setTargetJob(normalizedRole);
        setTargetCompany(normalizedCompany);
        setInterviewerPersona(normalizedPersona);
        setTtsProvider(voiceEngine);
        savePreferences({
            target_role: normalizedRole,
            target_company: normalizedCompany,
            job_description: normalizedDescription,
            question_count_override: normalizedCount || null,
            interviewer_persona: normalizedPersona,
            tts_provider: voiceEngine,
            resume_filename: resumeFilename || undefined,
        });
        setStatus('Configuration saved.');
        return true;
    };

    const runAnalysis = () => {
        if (!saveConfig()) return;

        const normalizedRole = String(jobTitle || '').trim();
        const normalizedCompany = String(company || '').trim();
        const normalizedDescription = String(jobDescription || '').trim();
        if (!normalizedRole) {
            setError('Target role is required for analysis.');
            return;
        }
        if (!normalizedDescription) {
            setError('Job description is required for analysis.');
            return;
        }

        setError('');
        setStatus('');
        startCareerAnalysis(
            resumeBase64 ? `data:application/pdf;base64,${resumeBase64}` : '',
            normalizedRole,
            normalizedCompany,
            normalizedDescription
        );
    };

    const clearConfig = () => {
        setError('');
        const started = clearConfiguration();
        if (!started) {
            setError('Not connected. Reconnect and try again.');
            return;
        }

        setJobTitle('');
        setCompany('');
        setJobDescription('');
        setQuestionCount('5');
        setDefaultPersona('friendly');
        setVoiceEngine('piper');
        setResumeBase64('');
        setResumeFilename('');
        setStatus('Configuration cleared.');
    };

    const openQuickDialog = (typeId = 'mixed') => {
        setQuickRole(String(jobTitle || targetRole || '').trim());
        setQuickJD(String(jobDescription || storedJobDescription || '').trim());
        setQuickType(typeId);
        setQuickOpen(true);
    };

    const handleQuickStart = () => {
        const role = quickRole.trim();
        const jd = quickJD.trim();
        if (!role || !jd) return;
        if (!isConnected) {
            setError('Not connected to server yet. Please try again in a moment.');
            return;
        }

        // Unlock audio playback on user click
        try {
            const unlockAudio = new Audio();
            unlockAudio.src = 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA';
            unlockAudio.play().catch(() => { });
        } catch (e) {
            console.warn('Audio unlock failed:', e);
        }

        setQuickStarting(true);
        setError('');

        const qCount = Math.max(1, Math.min(12, Math.trunc(Number(questionCount) || 5)));

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
            interviewer_persona: defaultPersona,
            question_count: qCount,
        });

    };

    return (
        <ThemeProvider theme={theme}>
            <CssBaseline />
            <Box sx={{ minHeight: '100vh', bgcolor: 'background.default', pb: { xs: 3, md: 5 } }}>
                <HiveTopNav active="config" />
                <Container maxWidth="lg" sx={{ pt: { xs: 2.5, md: 4 } }}>
                    <Stack spacing={2.2}>
                        <Paper sx={{ p: { xs: 2, md: 2.5 } }}>
                            <Typography variant="h4">Configuration</Typography>
                            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                Set target role, job description, resume, and interview defaults.
                            </Typography>
                        </Paper>

                        {/* ── Quick Interview Section ── */}
                        <Paper
                            sx={{
                                p: { xs: 2, md: 2.5 },
                                border: '1px solid',
                                borderColor: darkMode ? 'rgba(99,102,241,0.45)' : 'rgba(99,102,241,0.3)',
                                background: darkMode
                                    ? 'linear-gradient(135deg, rgba(99,102,241,0.14), rgba(139,92,246,0.06))'
                                    : 'linear-gradient(135deg, rgba(99,102,241,0.09), rgba(139,92,246,0.03))',
                            }}
                        >
                            <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} spacing={1.2} sx={{ mb: 1.8 }}>
                                <Stack direction="row" spacing={1.2} alignItems="center">
                                    <Box
                                        sx={{
                                            width: 40,
                                            height: 40,
                                            borderRadius: '50%',
                                            display: 'grid',
                                            placeItems: 'center',
                                            background: darkMode
                                                ? 'linear-gradient(135deg, rgba(99,102,241,0.55), rgba(139,92,246,0.4))'
                                                : 'linear-gradient(135deg, rgba(99,102,241,0.3), rgba(139,92,246,0.18))',
                                        }}
                                    >
                                        <BoltOutlined sx={{ color: darkMode ? '#c4b5fd' : '#6366f1', fontSize: 22 }} />
                                    </Box>
                                    <Box>
                                        <Typography variant="h6" sx={{ lineHeight: 1.2 }}>Try a Quick Interview</Typography>
                                        <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                            Jump straight in — pick a type and go. No resume or analysis needed.
                                        </Typography>
                                    </Box>
                                </Stack>
                                <Button
                                    variant="contained"
                                    startIcon={<BoltOutlined />}
                                    onClick={() => openQuickDialog('mixed')}
                                    disabled={!isConnected}
                                    sx={{
                                        whiteSpace: 'nowrap',
                                        minWidth: 160,
                                        background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                                        '&:hover': { background: 'linear-gradient(135deg, #4f46e5, #7c3aed)' },
                                    }}
                                >
                                    Quick Start
                                </Button>
                            </Stack>

                            <Box
                                sx={{
                                    display: 'grid',
                                    gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, 1fr)' },
                                    gap: 1,
                                }}
                            >
                                {QUICK_INTERVIEW_TYPES.map((type) => {
                                    const Icon = type.icon;
                                    return (
                                        <Paper
                                            key={type.id}
                                            role="button"
                                            tabIndex={0}
                                            onClick={() => openQuickDialog(type.id)}
                                            onKeyDown={(event) => {
                                                if (event.key === 'Enter' || event.key === ' ') {
                                                    event.preventDefault();
                                                    openQuickDialog(type.id);
                                                }
                                            }}
                                            sx={{
                                                p: 1.4,
                                                cursor: 'pointer',
                                                transition: 'all 0.18s ease',
                                                border: '1px solid',
                                                borderColor: darkMode ? 'rgba(99,102,241,0.25)' : 'rgba(99,102,241,0.15)',
                                                '&:hover': {
                                                    borderColor: darkMode ? 'rgba(99,102,241,0.55)' : 'rgba(99,102,241,0.4)',
                                                    boxShadow: '0 4px 16px rgba(99,102,241,0.15)',
                                                    transform: 'translateY(-1px)',
                                                },
                                            }}
                                        >
                                            <Stack spacing={0.6}>
                                                <Stack direction="row" spacing={0.7} alignItems="center">
                                                    <Icon sx={{ fontSize: 20, color: darkMode ? '#a5b4fc' : '#6366f1' }} />
                                                    <Typography variant="subtitle2" sx={{ fontWeight: 700, lineHeight: 1.2 }}>
                                                        {type.title}
                                                    </Typography>
                                                </Stack>
                                                <Typography variant="caption" sx={{ color: 'text.secondary', lineHeight: 1.3 }}>
                                                    {type.description}
                                                </Typography>
                                                <Stack direction="row" spacing={0.5} useFlexGap flexWrap="wrap">
                                                    {type.tags.map((tag) => (
                                                        <Chip key={`${type.id}-${tag}`} size="small" label={tag} variant="outlined" sx={{ fontSize: '0.65rem', height: 20 }} />
                                                    ))}
                                                </Stack>
                                            </Stack>
                                        </Paper>
                                    );
                                })}
                            </Box>
                        </Paper>

                        <Paper sx={{ p: { xs: 2, md: 2.5 } }}>
                            <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={1.2} sx={{ mb: 1.2 }}>
                                <Typography variant="h6">Target Profile</Typography>
                                <Stack direction="row" spacing={1}>
                                    <Chip size="small" label={`Readiness ${readinessPercent}%`} variant="outlined" />
                                </Stack>
                            </Stack>
                            <Divider sx={{ mb: 1.5 }} />

                            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: '1.2fr 1fr' }, gap: 1.5 }}>
                                <Stack spacing={1.2}>
                                    <TextField
                                        label="Target Role"
                                        value={jobTitle}
                                        onChange={(e) => setJobTitle(e.target.value)}
                                        size="small"
                                        InputLabelProps={{ shrink: true }}
                                    />
                                    <TextField
                                        label="Target Company"
                                        value={company}
                                        onChange={(e) => setCompany(e.target.value)}
                                        size="small"
                                        InputLabelProps={{ shrink: true }}
                                    />
                                    <TextField
                                        label="Default Question Count"
                                        type="number"
                                        value={questionCount}
                                        onChange={(e) => setQuestionCount(e.target.value)}
                                        inputProps={{ min: 1, max: 12 }}
                                        size="small"
                                        InputLabelProps={{ shrink: true }}
                                    />
                                    <TextField
                                        label="Job Description"
                                        multiline
                                        rows={6}
                                        value={jobDescription}
                                        onChange={(e) => setJobDescription(e.target.value)}
                                        inputProps={{ style: { overflowY: 'auto' } }}
                                        InputLabelProps={{ shrink: true }}
                                    />
                                </Stack>

                                <Stack spacing={1.1}>
                                    <Box
                                        sx={{
                                            minHeight: 190,
                                            border: '1px dashed rgba(249,115,22,0.35)',
                                            borderRadius: 2,
                                            overflow: 'hidden',
                                        }}
                                    >
                                        <PDFDropzone
                                            onUpload={(base64, filename) => {
                                                setResumeBase64(base64 || '');
                                                setResumeFilename(filename || '');
                                            }}
                                            isLoading={isAnalyzing}
                                        />
                                    </Box>
                                    {resumeFilename && (
                                        <Chip
                                            icon={<UploadFile />}
                                            size="small"
                                            label={`${resumeFilename} uploaded`}
                                            color="success"
                                            variant="outlined"
                                        />
                                    )}
                                    {!resumeBase64 && (
                                        <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                                            If no new file is uploaded, saved profile data will still be used.
                                        </Typography>
                                    )}
                                    <Stack spacing={0.8} sx={{ pt: 0.3 }}>
                                        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                                            Voice Engine
                                        </Typography>
                                        <FormControl fullWidth size="small">
                                            <InputLabel id="config-tts-provider-label">Voice Engine</InputLabel>
                                            <Select
                                                labelId="config-tts-provider-label"
                                                label="Voice Engine"
                                                value={voiceEngine}
                                                onChange={(event) => setVoiceEngine(String(event.target.value || 'piper'))}
                                            >
                                                <MenuItem value="piper">Piper (fast + lightweight)</MenuItem>
                                                <MenuItem value="qwen3_tts_mlx">Qwen3-TTS MLX (higher quality)</MenuItem>
                                            </Select>
                                        </FormControl>
                                        <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                                            This sets the default voice engine for interview question playback.
                                        </Typography>

                                        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                                            Default Interviewer Persona
                                        </Typography>
                                        <Box
                                            sx={{
                                                display: 'grid',
                                                gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' },
                                                gap: 0.75,
                                            }}
                                        >
                                            {PERSONA_OPTIONS.map((option) => {
                                                const selected = defaultPersona === option.id;
                                                const Icon = option.icon;
                                                return (
                                                    <Paper
                                                        key={option.id}
                                                        role="button"
                                                        tabIndex={0}
                                                        variant="outlined"
                                                        onClick={() => setDefaultPersona(option.id)}
                                                        onKeyDown={(event) => {
                                                            if (event.key === 'Enter' || event.key === ' ') {
                                                                event.preventDefault();
                                                                setDefaultPersona(option.id);
                                                            }
                                                        }}
                                                        sx={{
                                                            p: 0.9,
                                                            cursor: 'pointer',
                                                            borderColor: selected
                                                                ? 'rgba(249, 115, 22, 0.62)'
                                                                : 'rgba(249, 115, 22, 0.22)',
                                                            boxShadow: selected ? '0 0 0 1px rgba(249,115,22,0.22)' : 'none',
                                                        }}
                                                    >
                                                        <Stack direction="row" spacing={0.7} alignItems="flex-start">
                                                            <Icon
                                                                sx={{
                                                                    fontSize: 17,
                                                                    mt: '2px',
                                                                    color: selected ? 'warning.main' : 'text.secondary',
                                                                }}
                                                            />
                                                            <Box sx={{ minWidth: 0 }}>
                                                                <Typography variant="caption" sx={{ display: 'block', fontWeight: 700 }}>
                                                                    {option.label}
                                                                </Typography>
                                                                <Typography variant="caption" sx={{ color: 'text.secondary', lineHeight: 1.25 }}>
                                                                    {option.description}
                                                                </Typography>
                                                            </Box>
                                                        </Stack>
                                                    </Paper>
                                                );
                                            })}
                                        </Box>
                                        <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                                            Used as default for new sessions. You can still change persona on Interviews.
                                        </Typography>
                                    </Stack>
                                </Stack>
                            </Box>

                            {error && (
                                <Typography variant="body2" color="error" sx={{ mt: 1.2 }}>
                                    {error}
                                </Typography>
                            )}
                            {status && (
                                <Typography variant="body2" sx={{ mt: 1.2, color: 'success.main' }}>
                                    {status}
                                </Typography>
                            )}

                            <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1} sx={{ mt: 1.6 }}>
                                <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                                    {analysisProgress || 'Save configuration, then analyze to refresh readiness and skill gaps.'}
                                </Typography>
                                <Stack direction="row" spacing={1}>
                                    <Button
                                        variant="outlined"
                                        color="error"
                                        startIcon={<DeleteSweep />}
                                        onClick={() => setClearDialogOpen(true)}
                                        disabled={isAnalyzing}
                                    >
                                        Clear Configuration
                                    </Button>
                                    <Button variant="outlined" startIcon={<Save />} onClick={saveConfig} disabled={isAnalyzing}>
                                        Save
                                    </Button>
                                    <Button
                                        variant="contained"
                                        startIcon={isAnalyzing ? <CircularProgress size={14} color="inherit" /> : <PlayArrow />}
                                        onClick={runAnalysis}
                                        disabled={isAnalyzing}
                                    >
                                        {isAnalyzing ? 'Analyzing...' : 'Run Analysis'}
                                    </Button>
                                </Stack>
                            </Stack>
                        </Paper>

                        <Paper sx={{ p: { xs: 2, md: 2.5 } }}>
                            <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1.2} sx={{ mb: 1.2 }}>
                                <Box>
                                    <Typography variant="h6">Skills Intelligence</Typography>
                                    <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                        Compare what the job needs with what your profile currently proves.
                                    </Typography>
                                </Box>
                                <Chip
                                    size="small"
                                    icon={<TrendingUp />}
                                    label={`Readiness ${Math.round(clamp01(readinessScore, 0) * 100)}%`}
                                    color="warning"
                                    variant="outlined"
                                />
                            </Stack>
                            <Divider sx={{ mb: 1.5 }} />

                            {skillBoard.length === 0 ? (
                                <Box
                                    sx={{
                                        border: '1px dashed rgba(249,115,22,0.35)',
                                        borderRadius: 2,
                                        p: 2,
                                    }}
                                >
                                    <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                        Run analysis to generate required-vs-candidate skills, confidence, and focus targets.
                                    </Typography>
                                </Box>
                            ) : (
                                <Stack spacing={1.5}>
                                    <Box
                                        sx={{
                                            display: 'grid',
                                            gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, minmax(0, 1fr))' },
                                            gap: 1,
                                        }}
                                    >
                                        <Paper variant="outlined" sx={{ p: 1.1 }}>
                                            <Typography variant="caption" sx={{ color: 'text.secondary' }}>Must-have Coverage</Typography>
                                            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{Math.round(coverage.mustHave * 100)}%</Typography>
                                            <LinearProgress variant="determinate" value={coverage.mustHave * 100} sx={{ mt: 0.6, height: 7, borderRadius: 99 }} />
                                        </Paper>
                                        <Paper variant="outlined" sx={{ p: 1.1 }}>
                                            <Typography variant="caption" sx={{ color: 'text.secondary' }}>Nice-to-have Coverage</Typography>
                                            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{Math.round(coverage.niceToHave * 100)}%</Typography>
                                            <LinearProgress variant="determinate" value={coverage.niceToHave * 100} sx={{ mt: 0.6, height: 7, borderRadius: 99 }} />
                                        </Paper>
                                        <Paper variant="outlined" sx={{ p: 1.1 }}>
                                            <Typography variant="caption" sx={{ color: 'text.secondary' }}>Job Skills Tracked</Typography>
                                            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{coverage.requiredCount}</Typography>
                                        </Paper>
                                        <Paper variant="outlined" sx={{ p: 1.1 }}>
                                            <Typography variant="caption" sx={{ color: 'text.secondary' }}>Candidate Skills Seen</Typography>
                                            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{coverage.candidateCount}</Typography>
                                        </Paper>
                                    </Box>

                                    <Stack direction="row" spacing={0.8} useFlexGap flexWrap="wrap">
                                        <Chip
                                            size="small"
                                            label="Actionable"
                                            onClick={() => setSkillFilter('actionable')}
                                            color={skillFilter === 'actionable' ? 'warning' : 'default'}
                                            variant={skillFilter === 'actionable' ? 'filled' : 'outlined'}
                                        />
                                        <Chip
                                            size="small"
                                            label="Must-have"
                                            onClick={() => setSkillFilter('must')}
                                            color={skillFilter === 'must' ? 'warning' : 'default'}
                                            variant={skillFilter === 'must' ? 'filled' : 'outlined'}
                                        />
                                        <Chip
                                            size="small"
                                            label="Strong"
                                            onClick={() => setSkillFilter('strong')}
                                            color={skillFilter === 'strong' ? 'warning' : 'default'}
                                            variant={skillFilter === 'strong' ? 'filled' : 'outlined'}
                                        />
                                        <Chip
                                            size="small"
                                            label="All"
                                            onClick={() => setSkillFilter('all')}
                                            color={skillFilter === 'all' ? 'warning' : 'default'}
                                            variant={skillFilter === 'all' ? 'filled' : 'outlined'}
                                        />
                                    </Stack>

                                    <Box
                                        sx={{
                                            display: 'grid',
                                            gridTemplateColumns: { xs: '1fr', lg: '1.45fr 1fr' },
                                            gap: 1.2,
                                        }}
                                    >
                                        <Paper
                                            variant="outlined"
                                            sx={{
                                                p: 1,
                                                maxHeight: 410,
                                                overflowY: 'auto',
                                                display: 'flex',
                                                flexDirection: 'column',
                                                gap: 0.8,
                                            }}
                                        >
                                            {filteredBoard.map((row) => {
                                                const StatusIcon = row.status.icon;
                                                const isActive = selectedSkill?.id === row.id;
                                                return (
                                                    <Paper
                                                        key={row.id}
                                                        variant="outlined"
                                                        onClick={() => setSelectedSkillId(row.id)}
                                                        sx={{
                                                            p: 1,
                                                            cursor: 'pointer',
                                                            borderColor: isActive ? 'rgba(249, 115, 22, 0.5)' : 'divider',
                                                            boxShadow: isActive ? '0 0 0 1px rgba(249,115,22,0.22)' : 'none',
                                                        }}
                                                    >
                                                        <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
                                                            <Box sx={{ minWidth: 0 }}>
                                                                <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                                                                    {row.name}
                                                                </Typography>
                                                                <Stack direction="row" spacing={0.6} useFlexGap flexWrap="wrap" sx={{ mt: 0.35 }}>
                                                                    <Chip size="small" variant="outlined" label={row.priority === 'must_have' ? 'Must-have' : 'Nice-to-have'} />
                                                                    <Chip size="small" variant="outlined" label={`${Math.round(row.importance * 100)}% importance`} />
                                                                </Stack>
                                                            </Box>
                                                            <Stack spacing={0.4} alignItems="flex-end">
                                                                <Chip
                                                                    size="small"
                                                                    icon={<StatusIcon />}
                                                                    label={row.status.label}
                                                                    color={row.status.color}
                                                                    variant="outlined"
                                                                />
                                                                <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                                                                    {Math.round(row.confidence * 100)}% confidence
                                                                </Typography>
                                                            </Stack>
                                                        </Stack>
                                                        <Typography variant="caption" sx={{ color: 'text.secondary', mt: 0.7, display: 'block' }}>
                                                            Required: {row.requiredLevel} • Candidate: {row.candidateLevel}
                                                        </Typography>
                                                    </Paper>
                                                );
                                            })}
                                        </Paper>

                                        <Paper variant="outlined" sx={{ p: 1.2 }}>
                                            {selectedSkill ? (
                                                <Stack spacing={1}>
                                                    <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                                                        {selectedSkill.name}
                                                    </Typography>
                                                    <Stack direction="row" spacing={0.8} useFlexGap flexWrap="wrap">
                                                        <Chip size="small" label={selectedSkill.status.label} color={selectedSkill.status.color} variant="outlined" />
                                                        <Chip size="small" label={`${Math.round(selectedSkill.confidence * 100)}% confidence`} variant="outlined" />
                                                    </Stack>
                                                    {selectedSkill.reason && (
                                                        <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                                            {selectedSkill.reason}
                                                        </Typography>
                                                    )}
                                                    <Divider />
                                                    <Box>
                                                        <Typography variant="caption" sx={{ color: 'text.secondary' }}>Required by job</Typography>
                                                        <Typography variant="body2">{selectedSkill.requiredLevel}</Typography>
                                                        {selectedSkill.jdEvidence && (
                                                            <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                                                                {selectedSkill.jdEvidence}
                                                            </Typography>
                                                        )}
                                                    </Box>
                                                    <Box>
                                                        <Typography variant="caption" sx={{ color: 'text.secondary' }}>Candidate evidence</Typography>
                                                        {selectedSkill.candidateEvidence.length > 0 ? (
                                                            selectedSkill.candidateEvidence.map((ev, idx) => (
                                                                <Typography key={`${selectedSkill.id}-ev-${idx}`} variant="caption" sx={{ display: 'block', color: 'text.secondary' }}>
                                                                    • {ev}
                                                                </Typography>
                                                            ))
                                                        ) : (
                                                            <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                                                                No concrete evidence found yet.
                                                            </Typography>
                                                        )}
                                                    </Box>
                                                    {selectedSkill.learningTip && (
                                                        <Paper
                                                            variant="outlined"
                                                            sx={{
                                                                p: 1,
                                                                borderColor: 'rgba(249,115,22,0.35)',
                                                                bgcolor: 'rgba(249,115,22,0.04)',
                                                            }}
                                                        >
                                                            <Stack direction="row" spacing={0.8}>
                                                                <TipsAndUpdates sx={{ fontSize: 17, color: 'warning.main', mt: '2px' }} />
                                                                <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                                                                    {selectedSkill.learningTip}
                                                                </Typography>
                                                            </Stack>
                                                        </Paper>
                                                    )}
                                                </Stack>
                                            ) : (
                                                <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                                    Select a skill row to inspect details.
                                                </Typography>
                                            )}
                                        </Paper>
                                    </Box>

                                    {(followupTargets.length > 0 || followupQuestions.length > 0) && (
                                        <Box
                                            sx={{
                                                display: 'grid',
                                                gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' },
                                                gap: 1.1,
                                            }}
                                        >
                                            <Paper variant="outlined" sx={{ p: 1.2 }}>
                                                <Stack direction="row" spacing={0.8} alignItems="center" sx={{ mb: 0.8 }}>
                                                    <AutoGraph sx={{ color: 'warning.main', fontSize: 18 }} />
                                                    <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                                                        Top Focus Targets
                                                    </Typography>
                                                </Stack>
                                                {followupTargets.length === 0 ? (
                                                    <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                                                        No critical targets right now.
                                                    </Typography>
                                                ) : (
                                                    followupTargets.map((target, idx) => (
                                                        <Stack key={`target-${idx}`} spacing={0.2} sx={{ mb: idx < followupTargets.length - 1 ? 0.7 : 0 }}>
                                                            <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                                                {target?.name || target?.skill || 'Skill target'}
                                                            </Typography>
                                                            <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                                                                {target?.reason || 'Target this gap with concrete examples and trade-offs.'}
                                                            </Typography>
                                                        </Stack>
                                                    ))
                                                )}
                                            </Paper>

                                            <Paper variant="outlined" sx={{ p: 1.2 }}>
                                                <Stack direction="row" spacing={0.8} alignItems="center" sx={{ mb: 0.8 }}>
                                                    <TipsAndUpdates sx={{ color: 'warning.main', fontSize: 18 }} />
                                                    <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                                                        Validation Prompts
                                                    </Typography>
                                                </Stack>
                                                {followupQuestions.length === 0 ? (
                                                    <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                                                        Follow-up questions will appear after analysis.
                                                    </Typography>
                                                ) : (
                                                    followupQuestions.map((item, idx) => (
                                                        <Tooltip key={`followup-q-${idx}`} title={item?.intent || ''} placement="top-start">
                                                            <Typography variant="caption" sx={{ display: 'block', color: 'text.secondary', mb: idx < followupQuestions.length - 1 ? 0.8 : 0 }}>
                                                                • {item?.question || ''}
                                                            </Typography>
                                                        </Tooltip>
                                                    ))
                                                )}
                                            </Paper>
                                        </Box>
                                    )}
                                </Stack>
                            )}
                        </Paper>
                    </Stack>
                </Container>

                <Dialog open={clearDialogOpen} onClose={() => setClearDialogOpen(false)} maxWidth="xs" fullWidth>
                    <DialogTitle>Clear Configuration?</DialogTitle>
                    <DialogContent>
                        <Typography variant="body2">
                            This will remove target role, company, job description, uploaded resume context, and analysis outputs.
                        </Typography>
                    </DialogContent>
                    <DialogActions>
                        <Button onClick={() => setClearDialogOpen(false)}>Cancel</Button>
                        <Button
                            color="error"
                            variant="contained"
                            onClick={() => {
                                setClearDialogOpen(false);
                                clearConfig();
                            }}
                        >
                            Clear Configuration
                        </Button>
                    </DialogActions>
                </Dialog>

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
                                <TextField
                                    label="Target Role"
                                    placeholder="e.g. Senior Backend Engineer"
                                    value={quickRole}
                                    onChange={(e) => setQuickRole(e.target.value)}
                                    fullWidth
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
                                        Mock mode &bull; {PERSONA_OPTIONS.find((p) => p.id === defaultPersona)?.label || 'Friendly'} persona &bull; {questionCount || 5} questions
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
            </Box>
        </ThemeProvider>
    );
}
