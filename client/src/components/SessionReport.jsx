import { useEffect, useMemo, useRef, useState } from 'react';
import useInterviewStore from '@/store/useInterviewStore';
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
    Accordion,
    AccordionSummary,
    AccordionDetails,
    Divider,
    Grid,
    TextField,
    Alert,
    LinearProgress,
} from '@mui/material';
import {
    ExpandMore,
    Replay,
    TipsAndUpdates,
    TrendingUp,
} from '@mui/icons-material';
import { createHiveTheme } from '@/theme/hiveTheme';
import HiveTopNav from '@/components/ui/HiveTopNav';

function normalizeScore(value) {
    const n = Number(value);
    if (Number.isNaN(n)) return 0;
    return Math.max(0, Math.min(10, n));
}

function round1(value) {
    return Math.round(Number(value || 0) * 10) / 10;
}

function tone(score) {
    if (score >= 8) return { label: 'Excellent', color: 'success' };
    if (score >= 6) return { label: 'Good', color: 'success' };
    if (score >= 4) return { label: 'Fair', color: 'warning' };
    return { label: 'Needs Work', color: 'error' };
}

function scoreToneColor(score) {
    if (score >= 8) return '#16A34A';
    if (score >= 6) return '#D97706';
    if (score >= 4) return '#F59E0B';
    return '#DC2626';
}

const SCORE_KEYS = [
    { key: 'clarity', label: 'Clarity' },
    { key: 'accuracy', label: 'Accuracy' },
    { key: 'completeness', label: 'Completeness' },
    { key: 'structure', label: 'Structure' },
];

function toStringArray(value, limit = 6) {
    if (!Array.isArray(value)) return [];
    return value
        .map((item) => String(item || '').trim())
        .filter(Boolean)
        .slice(0, limit);
}

function deriveImprovementPlan(evaluation, questionText) {
    const plan = (evaluation && typeof evaluation.improvement_plan === 'object') ? evaluation.improvement_plan : {};
    const misses = toStringArray(evaluation?.rubric_misses || evaluation?.missing_concepts, 5);
    const focus = String(plan.focus || misses[0] || `Answer "${questionText}" with clearer structure`).trim();
    const steps = toStringArray(plan.steps, 3);
    const successCriteria = toStringArray(plan.success_criteria, 3);

    return {
        focus,
        steps: steps.length > 0 ? steps : [
            'Lead with one direct answer sentence.',
            'Add a concrete example with context and constraints.',
            'Close with outcome, impact, and one trade-off.',
        ],
        successCriteria: successCriteria.length > 0 ? successCriteria : [
            'Covers at least 2 expected points.',
            'Includes one measurable outcome.',
            'Uses clear flow: context -> action -> outcome.',
        ],
    };
}

function normalizeConfidence(value) {
    const n = Number(value);
    if (Number.isNaN(n)) return null;
    return Math.max(0, Math.min(1, n));
}

function formatDelta(value) {
    const n = Number(value || 0);
    if (Number.isNaN(n)) return '0.0';
    const sign = n > 0 ? '+' : '';
    return `${sign}${n.toFixed(1)}`;
}

function scoreBadgeColor(confidence) {
    if (confidence === null) return 'default';
    if (confidence >= 0.7) return 'success';
    if (confidence >= 0.45) return 'warning';
    return 'error';
}

export default function SessionReport() {
    const {
        interviewSummary,
        allEvaluations,
        darkMode,
        currentSessionId,
        selectedSession,
        selectedSessionLoading,
        isConnected,
        loadSessionDetails,
        setReportFromHistorySession,
        retryAttemptsByQuestion,
        retrySubmitting,
        retryErrors,
        loadRetryAttempts,
        submitRetryAnswer,
    } = useInterviewStore();

    const [expanded, setExpanded] = useState(false);
    const [retryDrafts, setRetryDrafts] = useState({});
    const rehydrateRequestRef = useRef(null);
    const theme = useMemo(() => createHiveTheme(darkMode ? 'dark' : 'light'), [darkMode]);
    const reportSessionId = String(currentSessionId || selectedSession?.session_id || '').trim() || null;

    const summary = interviewSummary || {};
    const hasSummaryData = Object.keys(summary).length > 0;
    const hasEvaluationData = Array.isArray(allEvaluations) && allEvaluations.length > 0;
    const questions = useMemo(
        () =>
            (allEvaluations || []).map((ev, idx) => {
                const evaluation = ev?.evaluation || {};
                const score = normalizeScore(evaluation?.score || 0);
                const breakdown = evaluation?.score_breakdown || {};
                const normalizedBreakdown = {
                    clarity: normalizeScore(breakdown?.clarity ?? score),
                    accuracy: normalizeScore(breakdown?.accuracy ?? score),
                    completeness: normalizeScore(breakdown?.completeness ?? score),
                    structure: normalizeScore(breakdown?.structure ?? score),
                };

                const confidence = normalizeConfidence(evaluation?.confidence);
                const evidenceQuotes = toStringArray(evaluation?.evidence_quotes, 2);
                const rubricMisses = toStringArray(evaluation?.rubric_misses || evaluation?.missing_concepts, 5);
                const rubricHits = toStringArray(evaluation?.rubric_hits || evaluation?.strengths, 5);
                const qualityFlags = toStringArray(evaluation?.quality_flags, 6);
                const improvementPlan = deriveImprovementPlan(evaluation, ev?.question?.text || 'this question');
                const retryDrill = (evaluation?.retry_drill && typeof evaluation.retry_drill === 'object')
                    ? evaluation.retry_drill
                    : {};

                return {
                    id: `q-${idx + 1}`,
                    index: idx + 1,
                    text: ev?.question?.text || 'Question',
                    category: ev?.question?.category || 'General',
                    score,
                    breakdown: normalizedBreakdown,
                    answer: ev?.answer || '',
                    improved: evaluation?.optimized_answer || '',
                    strengths: rubricHits,
                    gaps: rubricMisses,
                    tip: evaluation?.coaching_tip || '',
                    confidence,
                    evidenceQuotes,
                    qualityFlags,
                    improvementPlan,
                    retryPrompt: String(retryDrill?.prompt || '').trim(),
                    retryTargetPoints: toStringArray(retryDrill?.target_points, 3),
                };
            }),
        [allEvaluations]
    );

    const computedAverageScore = useMemo(() => {
        if (!questions.length) return 0;
        const total = questions.reduce((sum, q) => sum + normalizeScore(q.score), 0);
        return round1(total / questions.length);
    }, [questions]);

    const computedOverallBreakdown = useMemo(() => {
        if (!questions.length) {
            return {
                clarity: 0,
                accuracy: 0,
                completeness: 0,
                structure: 0,
            };
        }
        const totals = {
            clarity: 0,
            accuracy: 0,
            completeness: 0,
            structure: 0,
        };
        for (const q of questions) {
            totals.clarity += normalizeScore(q.breakdown?.clarity);
            totals.accuracy += normalizeScore(q.breakdown?.accuracy);
            totals.completeness += normalizeScore(q.breakdown?.completeness);
            totals.structure += normalizeScore(q.breakdown?.structure);
        }
        return {
            clarity: round1(totals.clarity / questions.length),
            accuracy: round1(totals.accuracy / questions.length),
            completeness: round1(totals.completeness / questions.length),
            structure: round1(totals.structure / questions.length),
        };
    }, [questions]);

    const summaryBreakdown = (summary.overall_breakdown && typeof summary.overall_breakdown === 'object')
        ? summary.overall_breakdown
        : ((summary.score_breakdown && typeof summary.score_breakdown === 'object') ? summary.score_breakdown : {});

    const overallBreakdown = useMemo(
        () => ({
            clarity: Number.isFinite(Number(summaryBreakdown?.clarity))
                ? normalizeScore(summaryBreakdown.clarity)
                : computedOverallBreakdown.clarity,
            accuracy: Number.isFinite(Number(summaryBreakdown?.accuracy))
                ? normalizeScore(summaryBreakdown.accuracy)
                : computedOverallBreakdown.accuracy,
            completeness: Number.isFinite(Number(summaryBreakdown?.completeness))
                ? normalizeScore(summaryBreakdown.completeness)
                : computedOverallBreakdown.completeness,
            structure: Number.isFinite(Number(summaryBreakdown?.structure))
                ? normalizeScore(summaryBreakdown.structure)
                : computedOverallBreakdown.structure,
        }),
        [summaryBreakdown, computedOverallBreakdown]
    );

    const averageScore = questions.length > 0
        ? computedAverageScore
        : normalizeScore(summary.average_score || 0);

    const performanceBreakdown = useMemo(() => {
        if (!questions.length) {
            const pb = summary.performance_breakdown || {};
            return {
                excellent: Number(pb.excellent || 0),
                good: Number(pb.good || 0),
                needs_work: Number(pb.needs_work || 0),
            };
        }
        return {
            excellent: questions.filter((q) => q.score >= 8).length,
            good: questions.filter((q) => q.score >= 6 && q.score < 8).length,
            needs_work: questions.filter((q) => q.score < 6).length,
        };
    }, [questions, summary.performance_breakdown]);

    const totalQuestions = Number(summary.total_questions || questions.length || 0);
    const answeredQuestions = Number(summary.answered_questions || questions.length || 0);
    const scorePercent = Math.round((averageScore / 10) * 100);
    const scoreAngle = Math.round((averageScore / 10) * 360);
    const summaryStrengths = summary.top_strengths || summary.strengths || [];
    const summaryImprovements = summary.areas_to_improve || [];
    const summaryActions = summary.action_items || [];
    const priorityFocus = String(
        summary.priority_focus || summaryImprovements?.[0] || 'Not found in repo'
    ).trim();
    const qualityRisks = toStringArray(summary.quality_risks || [], 4);

    useEffect(() => {
        if (!reportSessionId) {
            rehydrateRequestRef.current = null;
            return;
        }

        if (hasSummaryData && hasEvaluationData) {
            rehydrateRequestRef.current = null;
            return;
        }

        const selectedId = String(selectedSession?.session_id || '').trim();
        if (selectedId && selectedId === reportSessionId) {
            setReportFromHistorySession(selectedSession);
            return;
        }

        if (!isConnected || selectedSessionLoading) return;
        if (rehydrateRequestRef.current === reportSessionId) return;

        rehydrateRequestRef.current = reportSessionId;
        loadSessionDetails(reportSessionId);
    }, [
        reportSessionId,
        hasSummaryData,
        hasEvaluationData,
        selectedSession,
        selectedSessionLoading,
        isConnected,
        loadSessionDetails,
        setReportFromHistorySession,
    ]);

    useEffect(() => {
        if (!expanded || !reportSessionId) return;
        const question = questions.find((item) => item.id === expanded);
        if (!question) return;
        const key = `${reportSessionId}:${question.index}`;
        if (retryAttemptsByQuestion[key] === undefined) {
            loadRetryAttempts(reportSessionId, question.index);
        }
    }, [expanded, reportSessionId, questions, retryAttemptsByQuestion, loadRetryAttempts]);

    const handleRetryChange = (questionId, value) => {
        setRetryDrafts((prev) => ({ ...prev, [questionId]: value }));
    };

    const handleRetrySubmit = (question) => {
        if (!reportSessionId) return;
        const answer = String(retryDrafts[question.id] || '').trim();
        if (!answer) return;

        const accepted = submitRetryAnswer({
            sessionId: reportSessionId,
            questionNumber: question.index,
            answer,
            durationSeconds: 0,
            inputMode: 'text',
        });

        if (accepted) {
            setRetryDrafts((prev) => ({ ...prev, [question.id]: '' }));
        }
    };

    return (
        <ThemeProvider theme={theme}>
            <CssBaseline />
            <Box
                sx={{
                    minHeight: '100vh',
                    bgcolor: 'background.default',
                    pb: { xs: 3, md: 5 },
                    position: 'relative',
                    overflow: 'hidden',
                    '&::before': {
                        content: '""',
                        position: 'absolute',
                        top: -120,
                        right: -120,
                        width: 360,
                        height: 360,
                        borderRadius: '50%',
                        background: 'radial-gradient(circle, rgba(249,115,22,0.18), transparent 65%)',
                        pointerEvents: 'none',
                    },
                    '&::after': {
                        content: '""',
                        position: 'absolute',
                        bottom: -140,
                        left: -140,
                        width: 420,
                        height: 420,
                        borderRadius: '50%',
                        background: 'radial-gradient(circle, rgba(251,191,36,0.14), transparent 70%)',
                        pointerEvents: 'none',
                    },
                }}
            >
                <HiveTopNav active="report" />

                <Container maxWidth="lg" sx={{ pt: { xs: 2.5, md: 4 }, position: 'relative', zIndex: 1 }}>
                    <Paper
                        sx={{
                            p: { xs: 2, md: 2.75 },
                            mb: 2.5,
                            background: (t) =>
                                t.palette.mode === 'dark'
                                    ? 'linear-gradient(145deg, rgba(31,31,31,0.95), rgba(23,23,23,0.9))'
                                    : 'linear-gradient(145deg, rgba(255,255,255,0.96), rgba(255,248,235,0.92))',
                            borderRadius: 3,
                        }}
                    >
                        <Stack
                            direction={{ xs: 'column', md: 'row' }}
                            spacing={1.2}
                            justifyContent="space-between"
                            alignItems={{ xs: 'flex-start', md: 'center' }}
                        >
                            <Box>
                                <Typography variant="overline" sx={{ color: 'warning.main', letterSpacing: '0.08em' }}>
                                    PERFORMANCE DEBRIEF
                                </Typography>
                                <Typography variant="h4">Interview Report</Typography>
                                <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                    Overall performance first, then per-question coaching.
                                </Typography>
                            </Box>
                            <Stack direction="row" spacing={0.8} useFlexGap flexWrap="wrap">
                                <Chip size="small" label={`${answeredQuestions}/${totalQuestions || answeredQuestions} answered`} variant="outlined" />
                                <Chip size="small" label={`Score ${scorePercent}%`} color="secondary" variant="outlined" />
                            </Stack>
                        </Stack>
                    </Paper>

                    <Paper
                        sx={{
                            p: { xs: 2, md: 2.75 },
                            mb: 2.5,
                            background: (themeCtx) =>
                                themeCtx.palette.mode === 'dark'
                                    ? 'linear-gradient(140deg, rgba(245,158,11,0.22), rgba(30,41,59,0.42))'
                                    : 'linear-gradient(140deg, rgba(249,115,22,0.13), rgba(255,255,255,0.95))',
                            border: '1px solid',
                            borderColor: 'divider',
                            borderRadius: 3,
                            position: 'relative',
                            overflow: 'hidden',
                        }}
                    >
                        <Box
                            sx={{
                                position: 'absolute',
                                inset: 0,
                                background:
                                    'linear-gradient(120deg, transparent 0%, rgba(255,255,255,0.08) 45%, transparent 70%)',
                                pointerEvents: 'none',
                            }}
                        />
                        <Stack spacing={1.5} sx={{ position: 'relative' }}>
                            <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={1.2}>
                                <Box>
                                    <Typography variant="h6">Overall Interview Score</Typography>
                                    <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                        Based on {answeredQuestions}/{totalQuestions || answeredQuestions} answered questions.
                                    </Typography>
                                </Box>
                                <Chip
                                    size="small"
                                    label={`${averageScore.toFixed(1)}/10 • ${tone(averageScore).label}`}
                                    color={tone(averageScore).color}
                                    variant="outlined"
                                />
                            </Stack>

                            <Grid container spacing={1.2} alignItems="stretch">
                                <Grid size={{ xs: 12, md: 4 }}>
                                    <Paper
                                        sx={{
                                            p: 1.4,
                                            height: '100%',
                                            borderRadius: 2.2,
                                            backgroundColor: 'rgba(15, 23, 42, 0.06)',
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'space-between',
                                            gap: 1.2,
                                        }}
                                    >
                                        <Box>
                                            <Typography variant="overline" sx={{ color: 'text.secondary', lineHeight: 1.1 }}>
                                                Final Score
                                            </Typography>
                                            <Typography variant="h2" sx={{ lineHeight: 1.02, fontWeight: 800 }}>
                                                {averageScore.toFixed(1)}
                                            </Typography>
                                            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                                out of 10
                                            </Typography>
                                        </Box>
                                        <Box
                                            sx={{
                                                width: 112,
                                                height: 112,
                                                borderRadius: '50%',
                                                display: 'grid',
                                                placeItems: 'center',
                                                background: `conic-gradient(${scoreToneColor(averageScore)} ${scoreAngle}deg, rgba(148,163,184,0.25) 0deg)`,
                                                boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.15)',
                                            }}
                                        >
                                            <Box
                                                sx={{
                                                    width: 78,
                                                    height: 78,
                                                    borderRadius: '50%',
                                                    bgcolor: 'background.paper',
                                                    display: 'grid',
                                                    placeItems: 'center',
                                                    border: '1px solid',
                                                    borderColor: 'divider',
                                                }}
                                            >
                                                <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                                                    {scorePercent}%
                                                </Typography>
                                            </Box>
                                        </Box>
                                    </Paper>
                                </Grid>
                                <Grid size={{ xs: 12, md: 8 }}>
                                    <Paper sx={{ p: 1.3, height: '100%', borderRadius: 2.2 }}>
                                        <Typography variant="subtitle2" sx={{ mb: 1 }}>
                                            Overall Breakdown
                                        </Typography>
                                        <Grid container spacing={1}>
                                            {SCORE_KEYS.map(({ key, label }) => {
                                                const value = normalizeScore(overallBreakdown[key]);
                                                return (
                                                    <Grid key={`overall-${key}`} size={{ xs: 12, sm: 6 }}>
                                                        <Paper
                                                            sx={{
                                                                p: 1,
                                                                borderRadius: 1.8,
                                                                backgroundColor: 'rgba(15,23,42,0.03)',
                                                            }}
                                                        >
                                                            <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.45 }}>
                                                                <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                                                                    {label}
                                                                </Typography>
                                                                <Typography variant="caption" sx={{ fontWeight: 700 }}>
                                                                    {value.toFixed(1)}/10
                                                                </Typography>
                                                            </Stack>
                                                            <LinearProgress
                                                                variant="determinate"
                                                                value={value * 10}
                                                                sx={{
                                                                    height: 8,
                                                                    borderRadius: 99,
                                                                    '& .MuiLinearProgress-bar': {
                                                                        borderRadius: 99,
                                                                        backgroundColor: scoreToneColor(value),
                                                                    },
                                                                }}
                                                            />
                                                        </Paper>
                                                    </Grid>
                                                );
                                            })}
                                        </Grid>
                                        <Stack direction="row" spacing={0.8} useFlexGap flexWrap="wrap" sx={{ mt: 1 }}>
                                            <Chip size="small" variant="outlined" label={`Excellent ${performanceBreakdown.excellent}`} />
                                            <Chip size="small" variant="outlined" label={`Good ${performanceBreakdown.good}`} />
                                            <Chip size="small" variant="outlined" label={`Needs work ${performanceBreakdown.needs_work}`} />
                                        </Stack>
                                    </Paper>
                                </Grid>
                            </Grid>
                        </Stack>
                    </Paper>

                    <Paper sx={{ p: { xs: 2, md: 2.5 }, mb: 2.5, borderRadius: 3 }}>
                        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.2} justifyContent="space-between" alignItems={{ xs: 'flex-start', md: 'center' }}>
                            <Box>
                                <Typography variant="h6">Priority Focus For Next Session</Typography>
                                <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                    {priorityFocus || 'Not found in repo.'}
                                </Typography>
                            </Box>
                            {qualityRisks.length > 0 && (
                                <Stack direction="row" spacing={0.8} useFlexGap flexWrap="wrap">
                                    {qualityRisks.map((risk, idx) => (
                                        <Chip key={`risk-${idx}`} size="small" label={risk.replaceAll('_', ' ')} color="warning" variant="outlined" />
                                    ))}
                                </Stack>
                            )}
                        </Stack>
                    </Paper>

                    <Paper sx={{ p: { xs: 2, md: 2.5 }, mb: 2.5, borderRadius: 3 }}>
                        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                            <Typography variant="h6">Per-Question Feedback</Typography>
                            <Chip size="small" label={`${questions.length} questions`} variant="outlined" />
                        </Stack>
                        <Divider sx={{ mb: 1.2 }} />

                        {questions.length === 0 ? (
                            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                No question feedback available for this session.
                            </Typography>
                        ) : (
                            <Stack spacing={1.1}>
                                {questions.map((q) => {
                                    const retryKey = reportSessionId ? `${reportSessionId}:${q.index}` : '';
                                    const attempts = retryKey ? (retryAttemptsByQuestion[retryKey] || []) : [];
                                    const latestAttempt = attempts.length > 0 ? attempts[attempts.length - 1] : null;
                                    const latestEval = latestAttempt?.evaluation || {};
                                    const latestBreakdown = latestEval?.score_breakdown || {};
                                    const baseline = normalizeScore(latestAttempt?.baseline_score ?? q.score);
                                    const retryDelta = Number(latestAttempt?.delta_score || 0);
                                    const busy = Boolean(retrySubmitting[retryKey]);
                                    const retryError = retryErrors[retryKey];

                                    return (
                                        <Accordion
                                            key={q.id}
                                            expanded={expanded === q.id}
                                            onChange={(_, isExpanded) => setExpanded(isExpanded ? q.id : false)}
                                            sx={{
                                                borderRadius: '14px !important',
                                                border: '1px solid',
                                                borderColor: 'divider',
                                                overflow: 'hidden',
                                                '&::before': { display: 'none' },
                                                boxShadow: '0 6px 20px rgba(0,0,0,0.06)',
                                            }}
                                        >
                                            <AccordionSummary expandIcon={<ExpandMore />}>
                                                <Stack direction="row" spacing={1.1} alignItems="center" sx={{ width: '100%', minWidth: 0 }}>
                                                    <Chip size="small" label={`Q${q.index}`} />
                                                    <Typography
                                                        sx={{
                                                            flex: 1,
                                                            fontWeight: 650,
                                                            whiteSpace: 'normal',
                                                            overflowWrap: 'anywhere',
                                                        }}
                                                    >
                                                        {q.text}
                                                    </Typography>
                                                    <Chip
                                                        size="small"
                                                        label={`${q.score.toFixed(1)}/10`}
                                                        color={tone(q.score).color}
                                                        variant="outlined"
                                                    />
                                                </Stack>
                                            </AccordionSummary>

                                            <AccordionDetails>
                                                <Stack spacing={1.1}>
                                                    <Stack direction="row" spacing={0.8} useFlexGap flexWrap="wrap">
                                                        <Chip size="small" label={q.category} color="secondary" variant="outlined" />
                                                        {q.confidence !== null && (
                                                            <Chip
                                                                size="small"
                                                                label={`Confidence ${(q.confidence * 100).toFixed(0)}%`}
                                                                color={scoreBadgeColor(q.confidence)}
                                                                variant="outlined"
                                                            />
                                                        )}
                                                        {attempts.length > 0 && (
                                                            <Chip size="small" label={`${attempts.length} retries`} variant="outlined" />
                                                        )}
                                                    </Stack>

                                                    <Paper sx={{ p: 1.2, bgcolor: 'rgba(249, 115, 22, 0.07)' }}>
                                                        <Typography variant="subtitle2" sx={{ mb: 0.9 }}>
                                                            Why this score
                                                        </Typography>

                                                        <Grid container spacing={0.8} sx={{ mb: 1 }}>
                                                            {SCORE_KEYS.map(({ key, label }) => (
                                                                <Grid key={`${q.id}-score-${key}`} size={{ xs: 6, md: 3 }}>
                                                                    <Paper sx={{ p: 1, borderStyle: 'dashed' }}>
                                                                        <Typography variant="caption" sx={{ color: 'text.secondary' }}>{label}</Typography>
                                                                        <Typography variant="body2" sx={{ fontWeight: 700 }}>
                                                                            {normalizeScore(q.breakdown[key]).toFixed(1)}/10
                                                                        </Typography>
                                                                    </Paper>
                                                                </Grid>
                                                            ))}
                                                        </Grid>

                                                        {q.evidenceQuotes.length > 0 && (
                                                            <Stack spacing={0.6} sx={{ mb: 0.8 }}>
                                                                {q.evidenceQuotes.map((quote, idx) => (
                                                                    <Typography key={`${q.id}-quote-${idx}`} variant="body2" sx={{ color: 'text.secondary' }}>
                                                                        "{quote}"
                                                                    </Typography>
                                                                ))}
                                                            </Stack>
                                                        )}

                                                        <Paper sx={{ p: 1, mb: 0.8 }}>
                                                            <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                                                                Your answer
                                                            </Typography>
                                                            <Typography variant="body2">
                                                                {q.answer || 'No answer captured.'}
                                                            </Typography>
                                                        </Paper>

                                                        {q.qualityFlags.length > 0 && (
                                                            <Stack direction="row" spacing={0.8} useFlexGap flexWrap="wrap">
                                                                {q.qualityFlags.map((flag, idx) => (
                                                                    <Chip
                                                                        key={`${q.id}-flag-${idx}`}
                                                                        size="small"
                                                                        label={flag.replaceAll('_', ' ')}
                                                                        color="warning"
                                                                        variant="outlined"
                                                                    />
                                                                ))}
                                                            </Stack>
                                                        )}
                                                    </Paper>

                                                    <Paper sx={{ p: 1.2, bgcolor: 'rgba(34, 197, 94, 0.07)' }}>
                                                        <Stack direction="row" spacing={0.8} alignItems="center" sx={{ mb: 0.8 }}>
                                                            <TipsAndUpdates sx={{ fontSize: 18, color: 'success.main' }} />
                                                            <Typography variant="subtitle2">How to improve</Typography>
                                                        </Stack>

                                                        {q.gaps.length > 0 && (
                                                            <Stack direction="row" spacing={0.8} useFlexGap flexWrap="wrap" sx={{ mb: 0.9 }}>
                                                                {q.gaps.slice(0, 4).map((g, idx) => (
                                                                    <Chip key={`${q.id}-gap-${idx}`} size="small" label={g} color="warning" variant="outlined" />
                                                                ))}
                                                            </Stack>
                                                        )}

                                                        <Stack spacing={0.5} sx={{ mb: 0.9 }}>
                                                            {q.improvementPlan.steps.map((step, idx) => (
                                                                <Typography key={`${q.id}-step-${idx}`} variant="body2" sx={{ color: 'text.secondary' }}>
                                                                    {idx + 1}. {step}
                                                                </Typography>
                                                            ))}
                                                        </Stack>

                                                        <Paper sx={{ p: 1, mb: 0.8 }}>
                                                            <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                                                                Success criteria
                                                            </Typography>
                                                            <Stack spacing={0.3} sx={{ mt: 0.4 }}>
                                                                {q.improvementPlan.successCriteria.map((item, idx) => (
                                                                    <Typography key={`${q.id}-criteria-${idx}`} variant="body2">
                                                                        • {item}
                                                                    </Typography>
                                                                ))}
                                                            </Stack>
                                                        </Paper>

                                                        <Paper sx={{ p: 1, bgcolor: 'rgba(251, 191, 36, 0.1)' }}>
                                                            <Typography variant="caption" sx={{ color: 'secondary.main' }}>
                                                                Better answer pattern
                                                            </Typography>
                                                            <Typography variant="body2">
                                                                {q.improved || 'State context, describe your action, and end with measurable impact.'}
                                                            </Typography>
                                                        </Paper>
                                                    </Paper>

                                                    <Paper sx={{ p: 1.2 }}>
                                                        <Stack direction="row" spacing={0.8} alignItems="center" sx={{ mb: 0.8 }}>
                                                            <TrendingUp sx={{ fontSize: 18, color: 'secondary.main' }} />
                                                            <Typography variant="subtitle2">Retry now</Typography>
                                                        </Stack>

                                                        {q.retryPrompt && (
                                                            <Typography variant="body2" sx={{ color: 'text.secondary', mb: 0.8 }}>
                                                                {q.retryPrompt}
                                                            </Typography>
                                                        )}

                                                        {q.retryTargetPoints.length > 0 && (
                                                            <Stack direction="row" spacing={0.8} useFlexGap flexWrap="wrap" sx={{ mb: 0.8 }}>
                                                                {q.retryTargetPoints.map((point, idx) => (
                                                                    <Chip key={`${q.id}-target-${idx}`} size="small" label={point} variant="outlined" />
                                                                ))}
                                                            </Stack>
                                                        )}

                                                        <TextField
                                                            multiline
                                                            minRows={3}
                                                            value={retryDrafts[q.id] || ''}
                                                            onChange={(event) => handleRetryChange(q.id, event.target.value)}
                                                            placeholder="Rewrite this answer with clearer structure and evidence..."
                                                            fullWidth
                                                        />

                                                        <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                                                            <Button
                                                                variant="contained"
                                                                startIcon={<Replay />}
                                                                disabled={busy || !String(retryDrafts[q.id] || '').trim() || !reportSessionId}
                                                                onClick={() => handleRetrySubmit(q)}
                                                            >
                                                                Submit Retry
                                                            </Button>
                                                        </Stack>

                                                        {busy && <LinearProgress sx={{ mt: 1 }} />}
                                                        {retryError && (
                                                            <Alert severity="error" sx={{ mt: 1 }}>
                                                                {retryError}
                                                            </Alert>
                                                        )}
                                                        {latestAttempt && (
                                                            <Alert
                                                                severity={retryDelta >= 0 ? 'success' : 'warning'}
                                                                sx={{ mt: 1 }}
                                                            >
                                                                Attempt {latestAttempt.attempt_number} scored{' '}
                                                                {normalizeScore(latestEval?.score || 0).toFixed(1)}/10 ({formatDelta(retryDelta)})
                                                            </Alert>
                                                        )}

                                                        {attempts.length > 0 && (
                                                            <Paper sx={{ p: 1, mt: 1 }}>
                                                                <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                                                                    Attempt history
                                                                </Typography>
                                                                <Stack spacing={0.5} sx={{ mt: 0.6 }}>
                                                                    {attempts.map((entry) => {
                                                                        const num = Number(entry?.attempt_number || 0);
                                                                        const label = num === 0 ? 'Original' : `Retry ${num}`;
                                                                        const score = normalizeScore(entry?.evaluation?.score || 0);
                                                                        const delta = Number(entry?.delta_score || 0);
                                                                        return (
                                                                            <Stack
                                                                                key={`${q.id}-attempt-${entry?.retry_id || num}`}
                                                                                direction="row"
                                                                                spacing={0.8}
                                                                                alignItems="center"
                                                                                justifyContent="space-between"
                                                                            >
                                                                                <Typography variant="body2">
                                                                                    {label}
                                                                                </Typography>
                                                                                <Stack direction="row" spacing={0.8} alignItems="center">
                                                                                    <Chip size="small" label={`${score.toFixed(1)}/10`} variant="outlined" />
                                                                                    {num > 0 && (
                                                                                        <Chip
                                                                                            size="small"
                                                                                            label={formatDelta(delta)}
                                                                                            color={delta >= 0 ? 'success' : 'warning'}
                                                                                            variant="outlined"
                                                                                        />
                                                                                    )}
                                                                                </Stack>
                                                                            </Stack>
                                                                        );
                                                                    })}
                                                                </Stack>
                                                            </Paper>
                                                        )}
                                                    </Paper>

                                                    {latestAttempt && (
                                                        <Paper sx={{ p: 1.2 }}>
                                                            <Typography variant="subtitle2" sx={{ mb: 0.9 }}>
                                                                Before vs After
                                                            </Typography>
                                                            <Grid container spacing={0.8}>
                                                                <Grid size={{ xs: 12, md: 3 }}>
                                                                    <Paper sx={{ p: 1, borderStyle: 'dashed' }}>
                                                                        <Typography variant="caption" sx={{ color: 'text.secondary' }}>Score</Typography>
                                                                        <Typography variant="body2" sx={{ fontWeight: 700 }}>
                                                                            {baseline.toFixed(1)} -&gt; {normalizeScore(latestEval?.score || 0).toFixed(1)}
                                                                        </Typography>
                                                                    </Paper>
                                                                </Grid>
                                                                {SCORE_KEYS.map(({ key, label }) => (
                                                                    <Grid key={`${q.id}-delta-${key}`} size={{ xs: 6, md: 3 }}>
                                                                        <Paper sx={{ p: 1, borderStyle: 'dashed' }}>
                                                                            <Typography variant="caption" sx={{ color: 'text.secondary' }}>{label}</Typography>
                                                                            <Typography variant="body2" sx={{ fontWeight: 700 }}>
                                                                                {normalizeScore(q.breakdown[key]).toFixed(1)} -&gt; {normalizeScore(latestBreakdown[key]).toFixed(1)}
                                                                            </Typography>
                                                                        </Paper>
                                                                    </Grid>
                                                                ))}
                                                            </Grid>
                                                        </Paper>
                                                    )}

                                                    {q.tip && (
                                                        <Typography variant="body2" sx={{ color: 'warning.dark' }}>
                                                            <strong>Coach tip:</strong> {q.tip}
                                                        </Typography>
                                                    )}
                                                </Stack>
                                            </AccordionDetails>
                                        </Accordion>
                                    );
                                })}
                            </Stack>
                        )}
                    </Paper>

                    <Paper sx={{ p: { xs: 2, md: 2.5 }, borderRadius: 3 }}>
                        <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1.2} sx={{ mb: 1.2 }}>
                            <Typography variant="h6">Overall Coaching Summary</Typography>
                        </Stack>
                        <Typography variant="body2" sx={{ color: 'text.secondary', mb: 1.4 }}>
                            {summary.overall_feedback || 'General feedback is not available yet.'}
                        </Typography>
                        <Stack spacing={1}>
                            {summaryStrengths.length > 0 && (
                                <Box>
                                    <Typography variant="caption" sx={{ color: 'success.main' }}>Strengths</Typography>
                                    <Stack direction="row" spacing={0.8} useFlexGap flexWrap="wrap" sx={{ mt: 0.5 }}>
                                        {summaryStrengths.slice(0, 6).map((item, idx) => (
                                            <Chip key={`sum-s-${idx}`} size="small" label={item} color="success" variant="outlined" />
                                        ))}
                                    </Stack>
                                </Box>
                            )}
                            {summaryImprovements.length > 0 && (
                                <Box>
                                    <Typography variant="caption" sx={{ color: 'warning.main' }}>Areas to improve</Typography>
                                    <Stack direction="row" spacing={0.8} useFlexGap flexWrap="wrap" sx={{ mt: 0.5 }}>
                                        {summaryImprovements.slice(0, 6).map((item, idx) => (
                                            <Chip key={`sum-i-${idx}`} size="small" label={item} color="warning" variant="outlined" />
                                        ))}
                                    </Stack>
                                </Box>
                            )}
                            {summaryActions.length > 0 && (
                                <Box>
                                    <Typography variant="caption" sx={{ color: 'secondary.main' }}>Next actions</Typography>
                                    <Stack spacing={0.5} sx={{ mt: 0.5 }}>
                                        {summaryActions.slice(0, 5).map((item, idx) => (
                                            <Typography key={`sum-a-${idx}`} variant="body2" sx={{ color: 'text.secondary' }}>
                                                • {item}
                                            </Typography>
                                        ))}
                                    </Stack>
                                </Box>
                            )}
                        </Stack>
                    </Paper>
                </Container>
            </Box>
        </ThemeProvider>
    );
}
