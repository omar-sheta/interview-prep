import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
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
    IconButton,
    Tooltip,
    CircularProgress,
    Divider,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
} from '@mui/material';
import {
    History,
    AutoGraph,
    Timer,
    ArrowForward,
    DeleteOutline,
} from '@mui/icons-material';
import { createHiveTheme } from '@/theme/hiveTheme';
import HiveTopNav from '@/components/ui/HiveTopNav';

function fmtDate(iso) {
    if (!iso) return 'N/A';
    return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function durationLabel(startIso, endIso) {
    if (!startIso || !endIso) return 'N/A';
    const diff = Math.round((new Date(endIso) - new Date(startIso)) / 60000);
    if (diff <= 0) return '<1m';
    return `${diff}m`;
}

function scoreMeta(score10 = 0) {
    if (score10 >= 8) return { label: 'Excellent', color: 'success' };
    if (score10 >= 6) return { label: 'Good', color: 'info' };
    if (score10 >= 4) return { label: 'Fair', color: 'warning' };
    return { label: 'Needs Work', color: 'error' };
}

export default function HistoryView() {
    const navigate = useNavigate();
    const {
        isConnected,
        interviewHistory,
        historyLoading,
        deletingSessionIds,
        selectedSession,
        selectedSessionLoading,
        loadInterviewHistory,
        loadSessionDetails,
        clearSelectedSession,
        deleteInterviewHistory,
        deleteInterviewSession,
        setReportFromHistorySession,
        darkMode,
    } = useInterviewStore();

    const [pendingSessionId, setPendingSessionId] = useState(null);
    const [confirmTarget, setConfirmTarget] = useState(null);
    const [noticeMessage, setNoticeMessage] = useState('');
    const hasLoaded = useRef(false);
    const theme = useMemo(() => createHiveTheme(darkMode ? 'dark' : 'light'), [darkMode]);

    useEffect(() => {
        if (!isConnected || hasLoaded.current) return;
        hasLoaded.current = true;
        loadInterviewHistory();
    }, [isConnected, loadInterviewHistory]);

    useEffect(() => {
        if (!pendingSessionId || !selectedSession || selectedSessionLoading) return;
        if (selectedSession.session_id !== pendingSessionId) return;

        setReportFromHistorySession(selectedSession);
        navigate('/report');
    }, [pendingSessionId, selectedSession, selectedSessionLoading, setReportFromHistorySession, navigate]);

    const sessions = (interviewHistory || []).filter((s) => s.completed_at);
    const avgScore = sessions.length
        ? sessions.reduce((acc, s) => acc + (s.average_score || 0), 0) / sessions.length
        : 0;
    const latestSession = sessions[0] || null;

    const openSessionReport = (sessionId) => {
        clearSelectedSession();
        setPendingSessionId(sessionId);
        loadSessionDetails(sessionId);
    };

    const requestDeleteHistory = () => {
        if (sessions.length === 0) return;
        setConfirmTarget({ kind: 'all' });
    };

    const requestDeleteSession = (session) => {
        const sessionId = String(session?.session_id || '').trim();
        if (!sessionId) return;
        setConfirmTarget({
            kind: 'single',
            sessionId,
            title: session?.job_title || 'Interview Session',
        });
    };

    const closeConfirmDialog = () => setConfirmTarget(null);

    const confirmDelete = () => {
        if (!confirmTarget) return;

        if (confirmTarget.kind === 'all') {
            const started = deleteInterviewHistory();
            if (!started) {
                setNoticeMessage('Not connected. Reconnect and try again.');
            }
            setConfirmTarget(null);
            return;
        }

        const sessionId = String(confirmTarget.sessionId || '').trim();
        const started = deleteInterviewSession(sessionId);
        if (!started) {
            setNoticeMessage('Not connected. Reconnect and try again.');
            setConfirmTarget(null);
            return;
        }
        if (pendingSessionId === sessionId) setPendingSessionId(null);
        setConfirmTarget(null);
    };

    return (
        <ThemeProvider theme={theme}>
            <CssBaseline />
            <Box
                sx={{
                    height: '100vh',
                    overflowY: 'auto',
                    overflowX: 'hidden',
                    bgcolor: 'background.default',
                    pb: { xs: 3, md: 5 },
                }}
            >
                <HiveTopNav active="history" />
                <Container maxWidth="lg" sx={{ pt: { xs: 2.5, md: 4 } }}>
                    <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" alignItems={{ xs: 'flex-start', md: 'center' }} spacing={2} sx={{ mb: 4 }}>
                        <Box>
                            <Typography variant="overline" sx={{ color: 'text.secondary', letterSpacing: '0.14em' }}>
                                Interview Sessions
                            </Typography>
                            <Typography variant="h4">History</Typography>
                            <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.5 }}>
                                {sessions.length} completed sessions • Avg score {avgScore.toFixed(1)}/10
                            </Typography>
                        </Box>
                        <Stack direction="row" spacing={1.25} useFlexGap flexWrap="wrap">
                            <Button
                                variant="outlined"
                                startIcon={<History />}
                                onClick={() => latestSession && openSessionReport(latestSession.session_id)}
                                disabled={!latestSession || selectedSessionLoading}
                            >
                                View Latest
                            </Button>
                            <Button
                                variant="outlined"
                                color="error"
                                startIcon={<DeleteOutline />}
                                onClick={requestDeleteHistory}
                                disabled={sessions.length === 0 || historyLoading}
                            >
                                Delete History
                            </Button>
                        </Stack>
                    </Stack>

                    {!isConnected && interviewHistory.length === 0 && (
                        <Paper sx={{ p: 4, textAlign: 'center' }}>
                            <CircularProgress size={28} sx={{ color: 'text.secondary', mb: 2 }} />
                            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                Connecting to interview engine...
                            </Typography>
                        </Paper>
                    )}

                    {historyLoading && interviewHistory.length === 0 && (
                        <Paper sx={{ p: 4, textAlign: 'center' }}>
                            <CircularProgress size={28} sx={{ color: 'primary.main', mb: 2 }} />
                            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                Loading your history...
                            </Typography>
                        </Paper>
                    )}

                    {!historyLoading && isConnected && sessions.length === 0 && (
                        <Paper sx={{ p: 4, textAlign: 'center' }}>
                            <History sx={{ color: 'text.secondary', fontSize: 34, mb: 1 }} />
                            <Typography variant="h6" sx={{ mb: 0.5 }}>
                                No completed sessions yet
                            </Typography>
                            <Typography variant="body2" sx={{ color: 'text.secondary', mb: 2 }}>
                                Finish an interview session and it will show up here.
                            </Typography>
                            <Button variant="contained" onClick={() => navigate('/')}>
                                Start Practicing
                            </Button>
                        </Paper>
                    )}

                    <Stack spacing={1.5}>
                        {sessions.map((session) => {
                            const score10 = Number(session.average_score || 0);
                            const meta = scoreMeta(score10);
                            const selected = pendingSessionId === session.session_id;
                            const deletingSession = Boolean(deletingSessionIds?.[session.session_id]);

                            return (
                                <Paper
                                    key={session.session_id}
                                    sx={{
                                        p: 2,
                                        borderColor: selected ? 'rgba(249, 115, 22, 0.55)' : 'rgba(249, 115, 22, 0.12)',
                                        boxShadow: selected ? '0 0 0 1px rgba(249,115,22,0.2)' : 'none',
                                    }}
                                >
                                    <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} justifyContent="space-between" alignItems={{ xs: 'flex-start', md: 'center' }}>
                                        <Stack spacing={0.75} sx={{ minWidth: 0 }}>
                                            <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
                                                <Typography variant="subtitle1" fontWeight={700} sx={{ lineHeight: 1.2 }}>
                                                    {session.job_title || 'Interview Session'}
                                                </Typography>
                                                <Chip size="small" label={meta.label} color={meta.color} variant="outlined" />
                                                <Chip size="small" label={`${score10.toFixed(1)}/10`} variant="outlined" />
                                            </Stack>
                                            <Stack direction="row" spacing={1.5} useFlexGap flexWrap="wrap" sx={{ color: 'text.secondary' }}>
                                                <Stack direction="row" spacing={0.5} alignItems="center">
                                                    <AutoGraph sx={{ fontSize: 16 }} />
                                                    <Typography variant="caption">{fmtDate(session.started_at)}</Typography>
                                                </Stack>
                                                <Stack direction="row" spacing={0.5} alignItems="center">
                                                    <Timer sx={{ fontSize: 16 }} />
                                                    <Typography variant="caption">{durationLabel(session.started_at, session.completed_at)}</Typography>
                                                </Stack>
                                                <Typography variant="caption">
                                                    {session.answered_questions ?? 0}/{session.total_questions ?? 0} answered
                                                </Typography>
                                            </Stack>
                                        </Stack>

                                        <Stack direction="row" spacing={0.8}>
                                            <Tooltip title="Delete this session">
                                                <span>
                                                    <IconButton
                                                        color="error"
                                                        onClick={() => requestDeleteSession(session)}
                                                        disabled={historyLoading || deletingSession}
                                                    >
                                                        {deletingSession ? <CircularProgress size={17} color="inherit" /> : <DeleteOutline />}
                                                    </IconButton>
                                                </span>
                                            </Tooltip>
                                            <Button
                                                variant={selected ? 'contained' : 'outlined'}
                                                endIcon={selectedSessionLoading && selected ? <CircularProgress size={14} color="inherit" /> : <ArrowForward />}
                                                onClick={() => openSessionReport(session.session_id)}
                                                disabled={deletingSession || (selectedSessionLoading && selected)}
                                            >
                                                {selectedSessionLoading && selected ? 'Opening...' : 'View Report'}
                                            </Button>
                                        </Stack>
                                    </Stack>
                                </Paper>
                            );
                        })}
                    </Stack>

                    {selectedSessionLoading && pendingSessionId && (
                        <Box sx={{ mt: 2 }}>
                            <Divider sx={{ mb: 1.5 }} />
                            <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                                Loading selected session report...
                            </Typography>
                        </Box>
                    )}
                </Container>

                <Dialog open={Boolean(confirmTarget)} onClose={closeConfirmDialog} maxWidth="xs" fullWidth>
                    <DialogTitle>
                        {confirmTarget?.kind === 'all' ? 'Delete All History?' : 'Delete This Session?'}
                    </DialogTitle>
                    <DialogContent>
                        <Typography variant="body2">
                            {confirmTarget?.kind === 'all'
                                ? 'This will permanently remove all past sessions, reports, answers, and retry attempts.'
                                : `This will permanently remove "${confirmTarget?.title || 'Interview Session'}" and its report, answers, and retries.`}
                        </Typography>
                    </DialogContent>
                    <DialogActions>
                        <Button onClick={closeConfirmDialog}>Cancel</Button>
                        <Button color="error" variant="contained" onClick={confirmDelete}>
                            {confirmTarget?.kind === 'all' ? 'Delete All' : 'Delete Session'}
                        </Button>
                    </DialogActions>
                </Dialog>

                <Dialog open={Boolean(noticeMessage)} onClose={() => setNoticeMessage('')} maxWidth="xs" fullWidth>
                    <DialogTitle>Action Required</DialogTitle>
                    <DialogContent>
                        <Typography variant="body2">{noticeMessage}</Typography>
                    </DialogContent>
                    <DialogActions>
                        <Button onClick={() => setNoticeMessage('')} variant="contained">OK</Button>
                    </DialogActions>
                </Dialog>
            </Box>
        </ThemeProvider>
    );
}
