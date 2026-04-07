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
    LinearProgress,
    Tooltip,
} from '@mui/material';
import {
    ExpandMore,
    TipsAndUpdates,
    PictureAsPdfOutlined,
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

const SCORE_DIMENSION_STYLES = {
    relevance: {
        color: '#2563EB',
        border: 'rgba(37, 99, 235, 0.28)',
        background: 'rgba(37, 99, 235, 0.08)',
    },
    depth: {
        color: '#059669',
        border: 'rgba(5, 150, 105, 0.28)',
        background: 'rgba(5, 150, 105, 0.08)',
    },
    structure: {
        color: '#D97706',
        border: 'rgba(217, 119, 6, 0.28)',
        background: 'rgba(217, 119, 6, 0.08)',
    },
    specificity: {
        color: '#7C3AED',
        border: 'rgba(124, 58, 237, 0.28)',
        background: 'rgba(124, 58, 237, 0.08)',
    },
    communication: {
        color: '#DB2777',
        border: 'rgba(219, 39, 119, 0.28)',
        background: 'rgba(219, 39, 119, 0.08)',
    },
};

const SCORE_KEYS = [
    { key: 'relevance', label: 'Relevance' },
    { key: 'depth', label: 'Depth' },
    { key: 'structure', label: 'Structure' },
    { key: 'specificity', label: 'Specificity' },
    { key: 'communication', label: 'Communication' },
];

// ---- Radar Chart (SVG) ----
function RadarChart({ data, size = 200 }) {
    const pad = 40; // extra space for labels
    const cx = size / 2 + pad;
    const cy = size / 2 + pad;
    const r = size * 0.38;
    const vbW = size + pad * 2;
    const vbH = size + pad * 2;
    const levels = 5;
    const labels = SCORE_KEYS.map((k) => k.label);
    const values = SCORE_KEYS.map((k) => Math.max(0, Math.min(10, Number(data[k.key]) || 0)));
    const n = labels.length;
    const angleStep = (2 * Math.PI) / n;
    const startAngle = -Math.PI / 2;

    const pointAt = (i, val) => {
        const angle = startAngle + i * angleStep;
        const dist = (val / 10) * r;
        return [cx + dist * Math.cos(angle), cy + dist * Math.sin(angle)];
    };

    const gridLines = [];
    for (let lvl = 1; lvl <= levels; lvl++) {
        const pts = [];
        for (let i = 0; i < n; i++) {
            pts.push(pointAt(i, (lvl / levels) * 10).join(','));
        }
        gridLines.push(
            <polygon key={`grid-${lvl}`} points={pts.join(' ')} fill="none" stroke="rgba(148,163,184,0.25)" strokeWidth="1" />
        );
    }

    const axes = [];
    for (let i = 0; i < n; i++) {
        const [ex, ey] = pointAt(i, 10);
        axes.push(<line key={`axis-${i}`} x1={cx} y1={cy} x2={ex} y2={ey} stroke="rgba(148,163,184,0.2)" strokeWidth="1" />);
    }

    const dataPts = values.map((v, i) => pointAt(i, v).join(',')).join(' ');
    const labelEls = labels.map((label, i) => {
        const [lx, ly] = pointAt(i, 12);
        return (
            <text key={`label-${i}`} x={lx} y={ly} textAnchor="middle" dominantBaseline="central" fontSize="10" fill="currentColor" opacity="0.7">
                {label}
            </text>
        );
    });
    const valueEls = values.map((v, i) => {
        const [px, py] = pointAt(i, v);
        return (
            <circle key={`dot-${i}`} cx={px} cy={py} r="3.5" fill="#F97316" stroke="#fff" strokeWidth="1.5" />
        );
    });

    return (
        <svg viewBox={`0 0 ${vbW} ${vbH}`} width={size} height={size} style={{ display: 'block', margin: '0 auto' }}>
            {gridLines}
            {axes}
            <polygon points={dataPts} fill="rgba(249,115,22,0.18)" stroke="#F97316" strokeWidth="2" />
            {valueEls}
            {labelEls}
        </svg>
    );
}

// ---- Speech Telemetry Panel ----
function SpeechTelemetry({ telemetry, communicationFeedback }) {
    if (!telemetry) return null;
    const fillers = Number(telemetry.fillerWords) || 0;
    const fillersPerMin = Number(telemetry.fillersPerMinute) || 0;
    const confidence = telemetry.confidence || 'N/A';
    const hedgeWords = Number(telemetry.hedge_words) || 0;
    const star = telemetry.star_analysis || {};
    const fillerDetail = telemetry.filler_detail || {};
    const hedgeDetail = telemetry.hedge_detail || {};

    const fillerStatus = fillersPerMin <= 2 ? 'success' : fillersPerMin <= 5 ? 'warning' : 'error';

    const starComponents = ['situation', 'task', 'action', 'result'];

    return (
        <Paper sx={{ p: { xs: 2, md: 2.5 }, mb: 2.5, borderRadius: 3 }}>
            <Typography variant="h6" sx={{ mb: 1.2 }}>Speech Analytics</Typography>
            <Grid container spacing={1.2}>
                <Grid size={{ xs: 6, md: 4 }}>
                    <Tooltip title={Object.entries(fillerDetail).map(([w, c]) => `${w}: ${c}`).join(', ') || 'None'} arrow>
                        <Paper sx={{ p: 1.2, textAlign: 'center', borderRadius: 2, cursor: 'help' }}>
                            <Typography variant="caption" sx={{ color: 'text.secondary' }}>Filler Words</Typography>
                            <Typography variant="h5" sx={{ fontWeight: 700, mt: 0.3 }}>{fillers}</Typography>
                            <Typography variant="caption" sx={{ color: 'text.secondary' }}>{fillersPerMin}/min</Typography>
                            <Box sx={{ mt: 0.5 }}>
                                <Chip size="small" label={fillersPerMin <= 2 ? 'Low' : fillersPerMin <= 5 ? 'Moderate' : 'High'} color={fillerStatus} variant="outlined" />
                            </Box>
                        </Paper>
                    </Tooltip>
                </Grid>
                <Grid size={{ xs: 6, md: 4 }}>
                    <Tooltip title={Object.entries(hedgeDetail).map(([w, c]) => `${w}: ${c}`).join(', ') || 'None'} arrow>
                        <Paper sx={{ p: 1.2, textAlign: 'center', borderRadius: 2, cursor: 'help' }}>
                            <Typography variant="caption" sx={{ color: 'text.secondary' }}>Hedge Words</Typography>
                            <Typography variant="h5" sx={{ fontWeight: 700, mt: 0.3 }}>{hedgeWords}</Typography>
                            <Typography variant="caption" sx={{ color: 'text.secondary' }}>weakening phrases</Typography>
                            <Box sx={{ mt: 0.5 }}>
                                <Chip size="small" label={hedgeWords <= 2 ? 'Confident' : hedgeWords <= 5 ? 'Some hedging' : 'Uncertain'} color={hedgeWords <= 2 ? 'success' : hedgeWords <= 5 ? 'warning' : 'error'} variant="outlined" />
                            </Box>
                        </Paper>
                    </Tooltip>
                </Grid>
                <Grid size={{ xs: 6, md: 4 }}>
                    <Paper sx={{ p: 1.2, textAlign: 'center', borderRadius: 2 }}>
                        <Typography variant="caption" sx={{ color: 'text.secondary' }}>Confidence</Typography>
                        <Typography variant="h5" sx={{ fontWeight: 700, mt: 0.3 }}>{confidence}</Typography>
                        <Typography variant="caption" sx={{ color: 'text.secondary' }}>overall level</Typography>
                        <Box sx={{ mt: 0.5 }}>
                            <Chip size="small" label={confidence} color={confidence === 'High' ? 'success' : confidence === 'Low' ? 'error' : 'warning'} variant="outlined" />
                        </Box>
                    </Paper>
                </Grid>
            </Grid>

            {star.score !== undefined && (
                <Paper sx={{ p: 1.2, mt: 1.2, borderRadius: 2, bgcolor: 'rgba(249,115,22,0.05)' }}>
                    <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0.6 }}>
                        <Typography variant="subtitle2">STAR Framework Usage</Typography>
                        <Chip size="small" label={`${star.score}/4 components`} color={star.complete ? 'success' : star.score >= 2 ? 'warning' : 'error'} variant="outlined" />
                    </Stack>
                    <Stack direction="row" spacing={0.8} useFlexGap flexWrap="wrap">
                        {starComponents.map((comp) => (
                            <Chip
                                key={comp}
                                size="small"
                                label={comp.charAt(0).toUpperCase() + comp.slice(1)}
                                color={star[comp] ? 'success' : 'default'}
                                variant={star[comp] ? 'filled' : 'outlined'}
                                sx={{ opacity: star[comp] ? 1 : 0.5 }}
                            />
                        ))}
                    </Stack>
                </Paper>
            )}

            {communicationFeedback && (
                <Typography variant="body2" sx={{ color: 'text.secondary', mt: 1.2, fontStyle: 'italic' }}>
                    {communicationFeedback}
                </Typography>
            )}
        </Paper>
    );
}

function toStringArray(value, limit = 6) {
    if (!Array.isArray(value)) return [];
    return value
        .map((item) => String(item || '').trim())
        .filter(Boolean)
        .slice(0, limit);
}

function deriveImprovementPlan(evaluation, questionText) {
    const plan = (evaluation && typeof evaluation.improvement_plan === 'object') ? evaluation.improvement_plan : {};
    const misses = toStringArray(evaluation?.gaps || evaluation?.rubric_misses || evaluation?.missing_concepts, 5);
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
        sessionToken,
    } = useInterviewStore();

    const [expanded, setExpanded] = useState(false);
    const [expandedTextBlocks, setExpandedTextBlocks] = useState({});
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
                    relevance: normalizeScore(breakdown?.relevance ?? breakdown?.accuracy ?? score),
                    depth: normalizeScore(breakdown?.depth ?? breakdown?.completeness ?? score),
                    structure: normalizeScore(breakdown?.structure ?? score),
                    specificity: normalizeScore(breakdown?.specificity ?? breakdown?.clarity ?? score),
                    communication: normalizeScore(breakdown?.communication ?? score),
                };

                const confidence = normalizeConfidence(evaluation?.confidence);
                const evalGaps = toStringArray(evaluation?.gaps || evaluation?.rubric_misses || evaluation?.missing_concepts, 5);
                const evalStrengths = toStringArray(evaluation?.strengths, 5);
                const qualityFlags = toStringArray(evaluation?.quality_flags, 6);
                const isSkipped = Boolean(ev?.skipped)
                    || qualityFlags.some((flag) => String(flag).toLowerCase() === 'skipped')
                    || String(ev?.answer || '').trim().toLowerCase() === '(skipped)';
                const improvementPlan = deriveImprovementPlan(evaluation, ev?.question?.text || 'this question');
                return {
                    id: `q-${idx + 1}`,
                    index: idx + 1,
                    text: ev?.question?.text || 'Question',
                    category: ev?.question?.category || 'General',
                    score,
                    breakdown: normalizedBreakdown,
                    answer: ev?.answer || '',
                    modelAnswer: evaluation?.model_answer || evaluation?.optimized_answer || '',
                    strengths: evalStrengths,
                    gaps: evalGaps,
                    tip: evaluation?.coaching_tip || '',
                    evaluationReasoning: evaluation?.evaluation_reasoning || evaluation?.feedback || '',
                    confidence,
                    qualityFlags,
                    isSkipped,
                    improvementPlan,
                };
            }),
        [allEvaluations]
    );

    const scorableQuestions = useMemo(
        () => questions.filter((q) => !q.isSkipped),
        [questions]
    );

    const computedAverageScore = useMemo(() => {
        if (!scorableQuestions.length) return 0;
        const total = scorableQuestions.reduce((sum, q) => sum + normalizeScore(q.score), 0);
        return round1(total / scorableQuestions.length);
    }, [scorableQuestions]);

    const computedOverallBreakdown = useMemo(() => {
        const dims = SCORE_KEYS.map((k) => k.key);
        if (!scorableQuestions.length) {
            return Object.fromEntries(dims.map((d) => [d, 0]));
        }
        const totals = Object.fromEntries(dims.map((d) => [d, 0]));
        for (const q of scorableQuestions) {
            for (const d of dims) {
                totals[d] += normalizeScore(q.breakdown?.[d]);
            }
        }
        return Object.fromEntries(dims.map((d) => [d, round1(totals[d] / scorableQuestions.length)]));
    }, [scorableQuestions]);

    const summaryBreakdown = (summary.overall_breakdown && typeof summary.overall_breakdown === 'object')
        ? summary.overall_breakdown
        : ((summary.score_breakdown && typeof summary.score_breakdown === 'object') ? summary.score_breakdown : {});

    const overallBreakdown = useMemo(
        () => {
            const result = {};
            for (const { key } of SCORE_KEYS) {
                result[key] = Number.isFinite(Number(summaryBreakdown?.[key]))
                    ? normalizeScore(summaryBreakdown[key])
                    : computedOverallBreakdown[key];
            }
            return result;
        },
        [summaryBreakdown, computedOverallBreakdown]
    );

    const averageScore = scorableQuestions.length > 0
        ? computedAverageScore
        : normalizeScore(summary.average_score || 0);

    const performanceBreakdown = useMemo(() => {
        if (!scorableQuestions.length) {
            const pb = summary.performance_breakdown || {};
            return {
                excellent: Number(pb.excellent || 0),
                good: Number(pb.good || 0),
                needs_work: Number(pb.needs_work || 0),
            };
        }
        return {
            excellent: scorableQuestions.filter((q) => q.score >= 8).length,
            good: scorableQuestions.filter((q) => q.score >= 6 && q.score < 8).length,
            needs_work: scorableQuestions.filter((q) => q.score < 6).length,
        };
    }, [scorableQuestions, summary.performance_breakdown]);

    const parsedTotalQuestions = Number(summary.total_questions);
    const parsedAnsweredQuestions = Number(summary.answered_questions);
    const parsedSkippedQuestions = Number(summary.skipped_questions);
    const hasEvaluationRows = questions.length > 0;

    const totalQuestions = hasEvaluationRows
        ? questions.length
        : (Number.isFinite(parsedTotalQuestions) && parsedTotalQuestions >= 0
            ? parsedTotalQuestions
            : questions.length);
    const answeredQuestions = hasEvaluationRows
        ? scorableQuestions.length
        : (Number.isFinite(parsedAnsweredQuestions) && parsedAnsweredQuestions >= 0
            ? parsedAnsweredQuestions
            : scorableQuestions.length);
    const skippedQuestions = hasEvaluationRows
        ? Math.max(0, questions.length - scorableQuestions.length)
        : (Number.isFinite(parsedSkippedQuestions) && parsedSkippedQuestions >= 0
            ? parsedSkippedQuestions
            : Math.max(0, totalQuestions - answeredQuestions));
    const hasScorableAnswers = answeredQuestions > 0;
    const scorePercent = hasScorableAnswers ? Math.round((averageScore / 10) * 100) : 0;
    const scoreAngle = hasScorableAnswers ? Math.round((averageScore / 10) * 360) : 0;
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

    const [exporting, setExporting] = useState(false);

    const toggleTextBlock = (key) => {
        setExpandedTextBlocks((prev) => ({ ...prev, [key]: !prev[key] }));
    };

    const handleExport = async () => {
        if (!reportSessionId || exporting) return;
        setExporting(true);
        try {
            const token = sessionToken || localStorage.getItem('session_token');
            const res = await fetch(`/api/session/${reportSessionId}/export`, {
                headers: token ? { 'X-Session-Token': token } : {},
            });
            if (!res.ok) throw new Error(`Export failed: ${res.status}`);
            const blob = await res.blob();
            const disposition = res.headers.get('Content-Disposition') || '';
            const filenameMatch = disposition.match(/filename="?([^"]+)"?/);
            const filename = filenameMatch ? filenameMatch[1] : `interview-report-${reportSessionId.slice(0, 8)}.pdf`;
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
        } catch (err) {
            console.error('Export error:', err);
        } finally {
            setExporting(false);
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
                            <Stack direction="row" spacing={0.8} useFlexGap flexWrap="wrap" alignItems="center">
                                <Chip size="small" label={`${answeredQuestions}/${totalQuestions || answeredQuestions} answered`} variant="outlined" />
                                {skippedQuestions > 0 && (
                                    <Chip size="small" label={`${skippedQuestions} skipped`} color="warning" variant="outlined" />
                                )}
                                <Chip
                                    size="small"
                                    label={hasScorableAnswers ? `Score ${scorePercent}%` : 'Score N/A'}
                                    color={hasScorableAnswers ? 'secondary' : 'default'}
                                    variant="outlined"
                                />
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
                                        {hasScorableAnswers
                                            ? `Based on ${answeredQuestions}/${totalQuestions || answeredQuestions} answered questions.`
                                            : `No scorable answers yet (${answeredQuestions}/${totalQuestions || answeredQuestions} answered).`}
                                    </Typography>
                                </Box>
                                <Chip
                                    size="small"
                                    label={hasScorableAnswers ? `${averageScore.toFixed(1)}/10 • ${tone(averageScore).label}` : 'Not scored'}
                                    color={hasScorableAnswers ? tone(averageScore).color : 'default'}
                                    variant="outlined"
                                />
                            </Stack>

                            <Grid container spacing={1.2} alignItems="stretch">
                                <Grid size={{ xs: 12, md: 4 }}>
                                    <Stack spacing={1.2} sx={{ height: '100%' }}>
                                        <Paper
                                            sx={{
                                                p: 1.4,
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
                                                    {hasScorableAnswers ? averageScore.toFixed(1) : 'N/A'}
                                                </Typography>
                                                <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                                    {hasScorableAnswers ? 'out of 10' : 'insufficient answers'}
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
                                        <Stack direction="row" spacing={0.8} useFlexGap flexWrap="wrap">
                                            <Chip size="small" variant="outlined" label={`Excellent ${performanceBreakdown.excellent}`} />
                                            <Chip size="small" variant="outlined" label={`Good ${performanceBreakdown.good}`} />
                                            <Chip size="small" variant="outlined" label={`Needs work ${performanceBreakdown.needs_work}`} />
                                        </Stack>
                                        {reportSessionId && (
                                            <Button
                                                variant="contained"
                                                size="large"
                                                startIcon={<PictureAsPdfOutlined />}
                                                onClick={handleExport}
                                                disabled={exporting}
                                                sx={{
                                                    mt: 0.4,
                                                    alignSelf: 'stretch',
                                                    borderRadius: 2.4,
                                                    textTransform: 'none',
                                                    fontWeight: 700,
                                                    py: 1.1,
                                                }}
                                            >
                                                {exporting ? 'Exporting PDF...' : 'Download PDF Report'}
                                            </Button>
                                        )}
                                    </Stack>
                                </Grid>
                                <Grid size={{ xs: 12, md: 4 }}>
                                    <Paper sx={{ p: 1.3, height: '100%', borderRadius: 2.2, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                        <RadarChart data={overallBreakdown} size={210} />
                                    </Paper>
                                </Grid>
                                <Grid size={{ xs: 12, md: 4 }}>
                                    <Paper sx={{ p: 1.3, height: '100%', borderRadius: 2.2 }}>
                                        <Typography variant="subtitle2" sx={{ mb: 1 }}>
                                            Dimension Scores
                                        </Typography>
                                        <Stack spacing={0.8}>
                                            {SCORE_KEYS.map(({ key, label }) => {
                                                const value = normalizeScore(overallBreakdown[key]);
                                                const style = SCORE_DIMENSION_STYLES[key] || SCORE_DIMENSION_STYLES.relevance;
                                                return (
                                                    <Box key={`overall-${key}`}>
                                                        <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.3 }}>
                                                            <Typography variant="caption" sx={{ color: style.color, fontWeight: 700 }}>
                                                                {label}
                                                            </Typography>
                                                            <Typography variant="caption" sx={{ fontWeight: 700 }}>
                                                                {value.toFixed(1)}
                                                            </Typography>
                                                        </Stack>
                                                        <LinearProgress
                                                            variant="determinate"
                                                            value={value * 10}
                                                            sx={{
                                                                height: 6,
                                                                borderRadius: 99,
                                                                bgcolor: style.background,
                                                                '& .MuiLinearProgress-bar': {
                                                                    borderRadius: 99,
                                                                    backgroundColor: style.color,
                                                                },
                                                            }}
                                                        />
                                                    </Box>
                                                );
                                            })}
                                        </Stack>
                                    </Paper>
                                </Grid>
                            </Grid>
                        </Stack>
                    </Paper>

                    <SpeechTelemetry telemetry={summary.telemetry} communicationFeedback={summary.communication_feedback} />

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
                                    const reasoningKey = `${q.id}-reasoning`;
                                    const answerKey = `${q.id}-answer`;
                                    const modelKey = `${q.id}-model`;
                                    const tipKey = `${q.id}-tip`;
                                    const showReasoningToggle = q.evaluationReasoning.length > 240;
                                    const showAnswerToggle = q.answer.length > 320;
                                    const showModelToggle = q.modelAnswer.length > 260;
                                    const showTipToggle = q.tip.length > 220;

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
                                                        label={q.isSkipped ? 'Skipped' : `${q.score.toFixed(1)}/10`}
                                                        color={q.isSkipped ? 'warning' : tone(q.score).color}
                                                        variant="outlined"
                                                    />
                                                </Stack>
                                            </AccordionSummary>

                                            <AccordionDetails sx={{ pt: 0, pb: 3, px: { xs: 2.5, md: 3.5 } }}>
                                                <Stack spacing={4}>
                                                    {/* Header Metadata */}
                                                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                                                        <Chip size="small" label={q.category} color="secondary" variant="outlined" sx={{ borderRadius: 1.5 }} />
                                                        {q.confidence !== null && (
                                                            <Chip
                                                                size="small"
                                                                label={`Model Confidence ${(q.confidence * 100).toFixed(0)}%`}
                                                                color={scoreBadgeColor(q.confidence)}
                                                                variant="outlined"
                                                                sx={{ borderRadius: 1.5 }}
                                                            />
                                                        )}
                                                        {q.qualityFlags.length > 0 && q.qualityFlags.map((flag, idx) => (
                                                            <Chip
                                                                key={`${q.id}-flag-${idx}`}
                                                                size="small"
                                                                label={flag.replaceAll('_', ' ')}
                                                                color="warning"
                                                                variant="filled"
                                                                sx={{ borderRadius: 1.5, fontWeight: 600 }}
                                                            />
                                                        ))}
                                                    </Stack>

                                                    {/* Why this Score */}
                                                    <Box>
                                                        <Typography variant="overline" sx={{ color: 'text.secondary', fontWeight: 700, letterSpacing: '0.05em' }}>
                                                            Why this score
                                                        </Typography>
                                                        
                                                        {q.evaluationReasoning && (
                                                            <Typography
                                                                variant="body1"
                                                                sx={{
                                                                    color: 'text.primary',
                                                                    mt: 1,
                                                                    mb: 2,
                                                                    lineHeight: 1.6,
                                                                    ...(showReasoningToggle && !expandedTextBlocks[reasoningKey]
                                                                        ? {
                                                                            display: '-webkit-box',
                                                                            WebkitLineClamp: 3,
                                                                            WebkitBoxOrient: 'vertical',
                                                                            overflow: 'hidden',
                                                                        }
                                                                        : {}),
                                                                }}
                                                            >
                                                                {q.evaluationReasoning}
                                                            </Typography>
                                                        )}
                                                        {showReasoningToggle && (
                                                            <Button
                                                                size="small"
                                                                variant="text"
                                                                color="primary"
                                                                sx={{ alignSelf: 'flex-start', mb: 2, px: 0, minWidth: 0, textTransform: 'none', fontWeight: 600 }}
                                                                onClick={() => toggleTextBlock(reasoningKey)}
                                                            >
                                                                {expandedTextBlocks[reasoningKey] ? 'Show less' : 'Show full reasoning'}
                                                            </Button>
                                                        )}

                                                        <Stack direction="row" spacing={4} useFlexGap flexWrap="wrap" sx={{ mb: 3.5, mt: 1 }}>
                                                            {SCORE_KEYS.map(({ key, label }) => {
                                                                const style = SCORE_DIMENSION_STYLES[key] || SCORE_DIMENSION_STYLES.relevance;
                                                                return (
                                                                    <Box key={`${q.id}-score-${key}`}>
                                                                        <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, display: 'block', mb: 0.2 }}>{label}</Typography>
                                                                        <Typography variant="body1" sx={{ fontWeight: 800, color: style.color }}>
                                                                            {normalizeScore(q.breakdown[key]).toFixed(1)} <Typography component="span" variant="caption" sx={{ color: 'text.disabled' }}>/10</Typography>
                                                                        </Typography>
                                                                    </Box>
                                                                );
                                                            })}
                                                        </Stack>
                                                        
                                                        <Box sx={{ 
                                                            p: 2, 
                                                            px: 2.5,
                                                            borderLeft: '3px solid', 
                                                            borderColor: 'divider', 
                                                            bgcolor: (themeCtx) => themeCtx.palette.mode === 'dark' ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.015)',
                                                            borderRadius: '0 8px 8px 0'
                                                        }}>
                                                            <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', mb: 1, display: 'block' }}>
                                                                Your Answer
                                                            </Typography>
                                                            <Typography
                                                                variant="body2"
                                                                sx={{
                                                                    lineHeight: 1.7,
                                                                    color: 'text.primary',
                                                                    ...(showAnswerToggle && !expandedTextBlocks[answerKey]
                                                                        ? {
                                                                            display: '-webkit-box',
                                                                            WebkitLineClamp: 3,
                                                                            WebkitBoxOrient: 'vertical',
                                                                            overflow: 'hidden',
                                                                        }
                                                                        : {}),
                                                                }}
                                                            >
                                                                {q.answer || 'No answer captured.'}
                                                            </Typography>
                                                            {showAnswerToggle && (
                                                                <Button
                                                                    size="small"
                                                                    variant="text"
                                                                    color="primary"
                                                                    sx={{ mt: 0.5, px: 0, minWidth: 0, textTransform: 'none', fontWeight: 600 }}
                                                                    onClick={() => toggleTextBlock(answerKey)}
                                                                >
                                                                    {expandedTextBlocks[answerKey] ? 'Show less' : 'View full answer'}
                                                                </Button>
                                                            )}
                                                        </Box>
                                                    </Box>

                                                    <Divider sx={{ opacity: 0.6 }} />

                                                    {/* How to Improve */}
                                                    <Box>
                                                        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2.5 }}>
                                                            <TipsAndUpdates sx={{ fontSize: 20, color: 'success.main' }} />
                                                            <Typography variant="h6" sx={{ fontWeight: 600 }}>Actionable Feedback</Typography>
                                                        </Stack>

                                                        {q.gaps.length > 0 && (
                                                            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 3.5 }}>
                                                                {q.gaps.slice(0, 4).map((g, idx) => (
                                                                    <Chip key={`${q.id}-gap-${idx}`} size="small" label={g} sx={{ color: 'warning.main', borderColor: 'warning.main', bgcolor: 'transparent' }} variant="outlined" />
                                                                ))}
                                                            </Stack>
                                                        )}

                                                        <Grid container spacing={4} sx={{ mb: 2 }}>
                                                            <Grid size={{ xs: 12, md: 6 }}>
                                                                <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1.5, color: 'text.primary' }}>Suggested Improvement Steps</Typography>
                                                                <Stack spacing={1.5}>
                                                                    {q.improvementPlan.steps.map((step, idx) => (
                                                                        <Stack key={`${q.id}-step-${idx}`} direction="row" spacing={1.8} alignItems="flex-start">
                                                                            <Box sx={{ width: 24, height: 24, borderRadius: '50%', bgcolor: 'rgba(34, 197, 94, 0.1)', color: 'success.main', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, fontSize: '0.75rem', fontWeight: 700 }}>
                                                                                {idx + 1}
                                                                            </Box>
                                                                            <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.2, lineHeight: 1.6 }}>
                                                                                {step}
                                                                            </Typography>
                                                                        </Stack>
                                                                    ))}
                                                                </Stack>
                                                            </Grid>
                                                            
                                                            <Grid size={{ xs: 12, md: 6 }}>
                                                                <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1.5, color: 'text.primary' }}>Target Success Criteria</Typography>
                                                                <Stack spacing={1.5}>
                                                                    {q.improvementPlan.successCriteria.map((item, idx) => (
                                                                        <Stack key={`${q.id}-criteria-${idx}`} direction="row" spacing={1.5} alignItems="flex-start">
                                                                            <Box sx={{ width: 6, height: 6, mt: 0.8, borderRadius: '50%', bgcolor: 'text.disabled', flexShrink: 0 }} />
                                                                            <Typography variant="body2" sx={{ color: 'text.secondary', lineHeight: 1.6 }}>
                                                                                {item}
                                                                            </Typography>
                                                                        </Stack>
                                                                    ))}
                                                                </Stack>
                                                            </Grid>
                                                        </Grid>

                                                        <Box sx={{ 
                                                            mt: 4,
                                                            p: 2, 
                                                            px: 2.5,
                                                            borderLeft: '3px solid', 
                                                            borderColor: 'secondary.main', 
                                                            bgcolor: (themeCtx) => themeCtx.palette.mode === 'dark' ? 'rgba(251, 191, 36, 0.04)' : 'rgba(251, 191, 36, 0.05)',
                                                            borderRadius: '0 8px 8px 0'
                                                        }}>
                                                            <Typography variant="caption" sx={{ color: 'secondary.main', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', mb: 1, display: 'block' }}>
                                                                Ideal Model Answer
                                                            </Typography>
                                                            <Typography
                                                                variant="body2"
                                                                sx={{
                                                                    lineHeight: 1.7,
                                                                    color: 'text.primary',
                                                                    ...(showModelToggle && !expandedTextBlocks[modelKey]
                                                                        ? {
                                                                            display: '-webkit-box',
                                                                            WebkitLineClamp: 3,
                                                                            WebkitBoxOrient: 'vertical',
                                                                            overflow: 'hidden',
                                                                        }
                                                                        : {}),
                                                                }}
                                                            >
                                                                {q.modelAnswer || 'State context, describe your action, and end with measurable impact.'}
                                                            </Typography>
                                                            {showModelToggle && (
                                                                <Button
                                                                    size="small"
                                                                    variant="text"
                                                                    color="secondary"
                                                                    sx={{ mt: 0.5, px: 0, minWidth: 0, textTransform: 'none', fontWeight: 600 }}
                                                                    onClick={() => toggleTextBlock(modelKey)}
                                                                >
                                                                    {expandedTextBlocks[modelKey] ? 'Show less' : 'View full example'}
                                                                </Button>
                                                            )}
                                                        </Box>
                                                    </Box>

                                                    {/* Coach Tip */}
                                                    {q.tip && (
                                                        <Box sx={{ 
                                                            display: 'flex', 
                                                            alignItems: 'flex-start', 
                                                            gap: 1.5,
                                                            p: 2.5, 
                                                            borderRadius: 3,
                                                            bgcolor: (themeCtx) => themeCtx.palette.mode === 'dark' ? 'rgba(245, 158, 11, 0.06)' : 'rgba(249, 115, 22, 0.04)',
                                                        }}>
                                                            <Box sx={{ color: 'warning.main', fontSize: '1.2rem', mt: 0 }}>💡</Box>
                                                            <Box sx={{ flex: 1 }}>
                                                                <Typography
                                                                    variant="body2"
                                                                    sx={{
                                                                        color: (themeCtx) => themeCtx.palette.mode === 'dark' ? 'warning.light' : 'warning.dark',
                                                                        lineHeight: 1.6,
                                                                        ...(showTipToggle && !expandedTextBlocks[tipKey]
                                                                            ? {
                                                                                display: '-webkit-box',
                                                                                WebkitLineClamp: 2,
                                                                                WebkitBoxOrient: 'vertical',
                                                                                overflow: 'hidden',
                                                                            }
                                                                            : {}),
                                                                    }}
                                                                >
                                                                    <Typography component="span" sx={{ fontWeight: 700, mr: 1 }}>Coach Tip:</Typography>
                                                                    {q.tip}
                                                                </Typography>
                                                                {showTipToggle && (
                                                                    <Button
                                                                        size="small"
                                                                        variant="text"
                                                                        color="warning"
                                                                        sx={{ mt: 0.5, px: 0, minWidth: 0, textTransform: 'none', fontWeight: 600 }}
                                                                        onClick={() => toggleTextBlock(tipKey)}
                                                                    >
                                                                        {expandedTextBlocks[tipKey] ? 'Show less' : 'Read full tip'}
                                                                    </Button>
                                                                )}
                                                            </Box>
                                                        </Box>
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
