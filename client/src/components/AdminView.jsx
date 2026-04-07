import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Navigate } from 'react-router-dom';
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
    Divider,
    Alert,
    CircularProgress,
} from '@mui/material';
import {
    AdminPanelSettings,
    Refresh,
    CancelScheduleSend,
    HubOutlined,
    Groups2Outlined,
    LanOutlined,
    PsychologyAltOutlined,
} from '@mui/icons-material';
import { createHiveTheme } from '@/theme/hiveTheme';
import HiveTopNav from '@/components/ui/HiveTopNav';

function fmtTime(value) {
    if (!value) return 'N/A';
    try {
        return new Date(value).toLocaleString();
    } catch (_) {
        return 'N/A';
    }
}

function StatCard({ icon, label, value, hint }) {
    return (
        <Paper sx={{ p: 1.6, borderRadius: 3 }}>
            <Stack spacing={0.9}>
                <Stack direction="row" spacing={1} alignItems="center">
                    <Box
                        sx={{
                            width: 34,
                            height: 34,
                            borderRadius: 2,
                            display: 'grid',
                            placeItems: 'center',
                            bgcolor: 'rgba(245, 158, 11, 0.12)',
                            color: 'primary.main',
                        }}
                    >
                        {icon}
                    </Box>
                    <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                        {label}
                    </Typography>
                </Stack>
                <Typography variant="h4" sx={{ lineHeight: 1, fontWeight: 800 }}>
                    {value}
                </Typography>
                {hint ? (
                    <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                        {hint}
                    </Typography>
                ) : null}
            </Stack>
        </Paper>
    );
}

export default function AdminView() {
    const { darkMode, isAdmin, sessionToken, isConnected } = useInterviewStore();
    const [overview, setOverview] = useState(null);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState('');
    const [taskActionUserId, setTaskActionUserId] = useState('');
    const [pollingSuspended, setPollingSuspended] = useState(false);
    const hasLoadedOnceRef = useRef(false);
    const requestInFlightRef = useRef(false);

    const theme = useMemo(() => createHiveTheme(darkMode ? 'dark' : 'light'), [darkMode]);

    const loadOverview = useCallback(async (showSpinner = false) => {
        const token = sessionToken || localStorage.getItem('session_token');
        if (!isAdmin || !token || (pollingSuspended && !showSpinner)) {
            setLoading(false);
            return;
        }
        if (requestInFlightRef.current) {
            return;
        }

        requestInFlightRef.current = true;

        if (showSpinner) {
            setRefreshing(true);
        } else if (!hasLoadedOnceRef.current) {
            setLoading(true);
        }

        try {
            const response = await fetch('/api/admin/overview', {
                method: 'GET',
                headers: {
                    'X-Session-Token': token,
                    'Cache-Control': 'no-store',
                },
                cache: 'no-store',
            });

            if (response.status === 401 || response.status === 403) {
                setPollingSuspended(true);
                throw new Error('Admin access was denied for this account.');
            }
            if (!response.ok) {
                throw new Error(`Admin overview failed (${response.status})`);
            }

            const payload = await response.json();
            setOverview(payload);
            hasLoadedOnceRef.current = true;
            setError('');
        } catch (err) {
            setError(err?.message || 'Unable to load admin overview.');
        } finally {
            requestInFlightRef.current = false;
            setLoading(false);
            setRefreshing(false);
        }
    }, [isAdmin, pollingSuspended, sessionToken]);

    useEffect(() => {
        if (!isAdmin || pollingSuspended) return undefined;

        const pollIfVisible = () => {
            if (document.visibilityState === 'hidden') return;
            void loadOverview(false);
        };

        pollIfVisible();
        const intervalId = window.setInterval(() => {
            pollIfVisible();
        }, 15000);

        const refreshOnFocus = () => {
            if (document.visibilityState === 'visible') {
                void loadOverview(false);
            }
        };

        document.addEventListener('visibilitychange', refreshOnFocus);
        window.addEventListener('focus', refreshOnFocus);

        return () => {
            window.clearInterval(intervalId);
            document.removeEventListener('visibilitychange', refreshOnFocus);
            window.removeEventListener('focus', refreshOnFocus);
        };
    }, [isAdmin, loadOverview, pollingSuspended]);

    const cancelTask = useCallback(async (userId) => {
        const token = sessionToken || localStorage.getItem('session_token');
        if (!token || !userId) return;

        setTaskActionUserId(userId);
        try {
            const response = await fetch(`/api/admin/tasks/${encodeURIComponent(userId)}/cancel`, {
                method: 'POST',
                headers: {
                    'X-Session-Token': token,
                    'Cache-Control': 'no-store',
                },
                cache: 'no-store',
            });

            if (response.status === 401 || response.status === 403) {
                throw new Error('Admin access was denied for this action.');
            }
            if (!response.ok) {
                throw new Error(`Task cancellation failed (${response.status})`);
            }

            setPollingSuspended(false);
            await loadOverview(false);
        } catch (err) {
            setError(err?.message || 'Unable to cancel the selected task.');
        } finally {
            setTaskActionUserId('');
        }
    }, [loadOverview, sessionToken]);

    if (!isAdmin) {
        return <Navigate to="/interviews" replace />;
    }

    const counts = overview?.counts || {};
    const liveUsers = Array.isArray(overview?.live_users) ? overview.live_users : [];
    const activeTasks = Array.isArray(overview?.active_tasks)
        ? overview.active_tasks.filter((task) => task && !task.done)
        : [];
    const feedbackMetrics = overview?.feedback_metrics || {};

    return (
        <ThemeProvider theme={theme}>
            <CssBaseline />
            <Box sx={{ minHeight: '100vh', bgcolor: 'background.default', pb: { xs: 3, md: 5 } }}>
                <HiveTopNav active="admin" />
                <Container maxWidth="lg" sx={{ pt: { xs: 2.5, md: 4 } }}>
                    <Stack spacing={2}>
                        <Paper sx={{ p: { xs: 2, md: 2.5 } }}>
                            <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={1.2}>
                                <Box>
                                    <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.4 }}>
                                        <AdminPanelSettings color="primary" />
                                        <Typography variant="h5">Admin Console</Typography>
                                    </Stack>
                                    <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                        Allowlisted access only. This view is read-mostly and refreshes every few seconds.
                                    </Typography>
                                </Box>
                                <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
                                    <Chip
                                        size="small"
                                        label={isConnected ? 'Socket connected' : 'Socket reconnecting'}
                                        color={isConnected ? 'success' : 'warning'}
                                        variant="outlined"
                                    />
                                    <Chip
                                        size="small"
                                        label={overview?.server_time ? `Updated ${fmtTime(overview.server_time)}` : 'Waiting for data'}
                                        variant="outlined"
                                    />
                                    <Button
                                        variant="outlined"
                                        size="small"
                                        startIcon={refreshing ? <CircularProgress size={14} /> : <Refresh />}
                                        onClick={() => {
                                            setPollingSuspended(false);
                                            void loadOverview(true);
                                        }}
                                        disabled={refreshing}
                                    >
                                        Refresh
                                    </Button>
                                </Stack>
                            </Stack>
                            <Divider sx={{ my: 1.5 }} />
                            <Alert severity="info" variant="outlined">
                                Admin data is served with no-store headers, limited to emails in <code>ADMIN_EMAILS</code>, and polls gently while this tab is visible.
                            </Alert>
                            {error ? (
                                <Alert severity="error" variant="outlined" sx={{ mt: 1.2 }}>
                                    {error}
                                </Alert>
                            ) : null}
                        </Paper>

                        {loading && !overview ? (
                            <Paper sx={{ p: 3 }}>
                                <Stack direction="row" spacing={1.2} alignItems="center">
                                    <CircularProgress size={22} />
                                    <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                        Loading admin overview...
                                    </Typography>
                                </Stack>
                            </Paper>
                        ) : null}

                        <Box
                            sx={{
                                display: 'grid',
                                gridTemplateColumns: {
                                    xs: '1fr 1fr',
                                    lg: 'repeat(4, minmax(0, 1fr))',
                                },
                                gap: 1.2,
                            }}
                        >
                            <StatCard
                                icon={<Groups2Outlined fontSize="small" />}
                                label="Registered Users"
                                value={counts.registered_users ?? 0}
                                hint="Persistent user accounts"
                            />
                            <StatCard
                                icon={<LanOutlined fontSize="small" />}
                                label="Live Connections"
                                value={counts.live_connections ?? 0}
                                hint={`${counts.socket_sessions ?? 0} socket sessions`}
                            />
                            <StatCard
                                icon={<HubOutlined fontSize="small" />}
                                label="Active Interviews"
                                value={counts.active_interviews ?? 0}
                                hint={`${counts.live_users ?? 0} live authenticated users`}
                            />
                            <StatCard
                                icon={<PsychologyAltOutlined fontSize="small" />}
                                label="Active Tasks"
                                value={counts.active_analysis_tasks ?? 0}
                                hint={`${counts.authenticated_socket_sessions ?? 0} authenticated sockets`}
                            />
                        </Box>

                        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', xl: '1.15fr 0.85fr' }, gap: 1.2 }}>
                            <Paper sx={{ p: { xs: 2, md: 2.25 } }}>
                                <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                                    <Typography variant="h6">Live Users</Typography>
                                    <Chip size="small" label={`${liveUsers.length} active`} variant="outlined" />
                                </Stack>
                                <Divider sx={{ mb: 1.2 }} />
                                <Stack spacing={1}>
                                    {liveUsers.length === 0 ? (
                                        <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                            No authenticated users are currently connected.
                                        </Typography>
                                    ) : liveUsers.map((user) => (
                                        <Paper key={user.user_id} variant="outlined" sx={{ p: 1.2, borderRadius: 2.5 }}>
                                            <Stack spacing={0.7}>
                                                <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={0.8}>
                                                    <Box>
                                                        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                                                            {user.username || user.email || user.user_id}
                                                        </Typography>
                                                        <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                                                            {user.email || user.user_id}
                                                        </Typography>
                                                    </Box>
                                                    <Stack direction="row" spacing={0.8} useFlexGap flexWrap="wrap">
                                                        <Chip size="small" label={`${user.connections || 0} connection${Number(user.connections || 0) === 1 ? '' : 's'}`} variant="outlined" />
                                                        {user.active_interview ? (
                                                            <Chip size="small" label={`Interview Q${user.current_question || 1}`} color="warning" variant="outlined" />
                                                        ) : (
                                                            <Chip size="small" label="Idle" variant="outlined" />
                                                        )}
                                                        {user.active_analysis_task ? (
                                                            <Chip size="small" label="Analyzing" color="info" variant="outlined" />
                                                        ) : null}
                                                    </Stack>
                                                </Stack>
                                            </Stack>
                                        </Paper>
                                    ))}
                                </Stack>
                            </Paper>

                            <Stack spacing={1.2}>
                                <Paper sx={{ p: { xs: 2, md: 2.25 } }}>
                                    <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                                        <Typography variant="h6">Active Analysis Tasks</Typography>
                                        <Chip size="small" label={`${activeTasks.length} running`} variant="outlined" />
                                    </Stack>
                                    <Divider sx={{ mb: 1.2 }} />
                                    <Stack spacing={1}>
                                        {activeTasks.length === 0 ? (
                                            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                                No long-running career-analysis tasks are currently active. Live interview state is shown in the user cards.
                                            </Typography>
                                        ) : activeTasks.map((task) => (
                                            <Paper key={task.user_id} variant="outlined" sx={{ p: 1.2, borderRadius: 2.5 }}>
                                                <Stack spacing={0.8}>
                                                    <Box>
                                                        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                                                            {task.username || task.email || task.user_id}
                                                        </Typography>
                                                        <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                                                            {task.email || task.user_id}
                                                        </Typography>
                                                    </Box>
                                                    <Stack direction="row" spacing={0.8} useFlexGap flexWrap="wrap">
                                                        <Chip size="small" label={`${task.connections || 0} connection${Number(task.connections || 0) === 1 ? '' : 's'}`} variant="outlined" />
                                                        <Chip size="small" label="In progress" color="info" variant="outlined" />
                                                    </Stack>
                                                    <Button
                                                        size="small"
                                                        variant="outlined"
                                                        color="warning"
                                                        startIcon={taskActionUserId === task.user_id ? <CircularProgress size={14} /> : <CancelScheduleSend />}
                                                        disabled={taskActionUserId === task.user_id}
                                                        onClick={() => void cancelTask(task.user_id)}
                                                    >
                                                        Cancel task
                                                    </Button>
                                                </Stack>
                                            </Paper>
                                        ))}
                                    </Stack>
                                </Paper>

                                <Paper sx={{ p: { xs: 2, md: 2.25 } }}>
                                    <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                                        <Typography variant="h6">Feedback Snapshot</Typography>
                                        <Chip size="small" label="Read only" variant="outlined" />
                                    </Stack>
                                    <Divider sx={{ mb: 1.2 }} />
                                    <Stack spacing={0.8}>
                                        {Object.keys(feedbackMetrics).length === 0 ? (
                                            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                                No feedback metrics are available yet.
                                            </Typography>
                                        ) : Object.entries(feedbackMetrics).map(([key, value]) => (
                                            <Stack key={key} direction="row" justifyContent="space-between" spacing={1}>
                                                <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                                    {key}
                                                </Typography>
                                                <Typography variant="body2" sx={{ fontWeight: 700 }}>
                                                    {typeof value === 'number' ? value.toFixed(2) : String(value)}
                                                </Typography>
                                            </Stack>
                                        ))}
                                    </Stack>
                                </Paper>
                            </Stack>
                        </Box>
                    </Stack>
                </Container>
            </Box>
        </ThemeProvider>
    );
}
