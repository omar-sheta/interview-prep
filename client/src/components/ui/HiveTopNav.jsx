import { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
    AppBar,
    Container,
    Stack,
    Box,
    Typography,
    Button,
    Chip,
    IconButton,
    Tooltip,
    Paper,
    alpha,
} from '@mui/material';
import { Hive, History, SmartToy, Tune, DarkMode, LightMode, Logout } from '@mui/icons-material';
import useInterviewStore from '@/store/useInterviewStore';

export default function HiveTopNav({
    active = 'interviews',
    showInterviews = true,
    showConfiguration = true,
    showHistory = true,
    showSignOut = true,
    quickActionLabel = '',
    quickActionIcon = null,
    onQuickAction = null,
}) {
    const navigate = useNavigate();
    const location = useLocation();
    const { darkMode, toggleDarkMode, logout, endInterview, interviewActive } = useInterviewStore();
    const isInterviewRoute = location.pathname === '/session';
    const shouldConfirmExit = Boolean(isInterviewRoute && interviewActive);
    const [pendingAction, setPendingAction] = useState(null);

    useEffect(() => {
        if (!shouldConfirmExit && pendingAction) {
            setPendingAction(null);
        }
    }, [shouldConfirmExit, pendingAction]);

    const openExitConfirm = (action) => {
        setPendingAction(action);
    };

    const closeExitConfirm = () => {
        setPendingAction(null);
    };

    const confirmExitAndContinue = () => {
        if (!pendingAction) return;

        const action = pendingAction;
        setPendingAction(null);
        endInterview();

        if (action.type === 'logout') {
            logout();
            navigate('/login', { replace: true });
            return;
        }

        if (action.type === 'navigate' && action.path && action.path !== location.pathname) {
            navigate(action.path);
        }
    };

    const navigateWithGuard = (path) => {
        if (!path || path === location.pathname) return;
        if (shouldConfirmExit) {
            openExitConfirm({ type: 'navigate', path });
            return;
        }
        navigate(path);
    };

    const logoutWithGuard = () => {
        if (shouldConfirmExit) {
            openExitConfirm({ type: 'logout' });
            return;
        }
        logout();
        navigate('/login', { replace: true });
    };

    const normalizedActive = (active === 'interview' || active === 'report' || active === 'dashboard') ? 'interviews' : active;
    const navItems = [
        { key: 'interviews', label: 'Interviews', icon: <SmartToy />, path: '/interviews', visible: showInterviews },
        { key: 'config', label: 'Configuration', icon: <Tune />, path: '/config', visible: showConfiguration },
        { key: 'history', label: 'History', icon: <History />, path: '/history', visible: showHistory },
    ].filter((item) => item.visible);

    return (
        <AppBar
            position="sticky"
            color="transparent"
            elevation={0}
            sx={{
                backdropFilter: 'blur(14px)',
                borderBottom: darkMode
                    ? '1px solid rgba(245, 158, 11, 0.22)'
                    : '1px solid rgba(217, 119, 6, 0.14)',
                bgcolor: darkMode ? 'rgba(10, 10, 10, 0.86)' : 'rgba(255, 255, 255, 0.9)',
            }}
        >
            <Container maxWidth="lg">
                <Stack
                    direction="row"
                    alignItems="center"
                    justifyContent="space-between"
                    sx={{
                        minHeight: 58,
                        py: 0.55,
                    }}
                >
                    <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 220 }}>
                        <Box
                            sx={{
                                width: 30,
                                height: 30,
                                borderRadius: '50%',
                                display: 'grid',
                                placeItems: 'center',
                                bgcolor: 'primary.main',
                                color: '#fff',
                            }}
                        >
                            <Hive sx={{ fontSize: 18 }} />
                        </Box>
                        <Typography variant="h6" sx={{ lineHeight: 1, letterSpacing: '-0.01em', fontSize: '1.08rem' }}>
                            BeePrepared
                        </Typography>
                        <Chip
                            size="small"
                            label="v0"
                            sx={{
                                height: 24,
                                borderColor: alpha('#f97316', darkMode ? 0.45 : 0.25),
                                bgcolor: alpha('#f97316', darkMode ? 0.16 : 0.08),
                            }}
                            variant="outlined"
                        />
                    </Stack>

                    <Stack direction="row" spacing={0.8} alignItems="center" sx={{ minWidth: 220, justifyContent: 'flex-end' }}>
                        {quickActionLabel && typeof onQuickAction === 'function' && (
                            <Button
                                variant="outlined"
                                size="small"
                                startIcon={quickActionIcon}
                                onClick={onQuickAction}
                                sx={{
                                    borderRadius: 999,
                                    px: 1.2,
                                    textTransform: 'none',
                                    fontWeight: 700,
                                    whiteSpace: 'nowrap',
                                    borderColor: alpha('#f97316', darkMode ? 0.42 : 0.28),
                                    bgcolor: alpha('#f97316', darkMode ? 0.1 : 0.05),
                                }}
                            >
                                {quickActionLabel}
                            </Button>
                        )}
                        <Tooltip title={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}>
                            <IconButton
                                color="inherit"
                                onClick={toggleDarkMode}
                                sx={{
                                    border: `1px solid ${alpha('#f97316', darkMode ? 0.4 : 0.22)}`,
                                    borderRadius: 1.5,
                                }}
                            >
                                {darkMode ? <LightMode /> : <DarkMode />}
                            </IconButton>
                        </Tooltip>
                        {showSignOut && (
                            <Tooltip title="Sign out">
                                <IconButton
                                    onClick={logoutWithGuard}
                                    sx={{
                                        border: `1px solid ${alpha('#ef4444', darkMode ? 0.44 : 0.22)}`,
                                        borderRadius: 1.5,
                                        color: darkMode ? '#fca5a5' : '#b91c1c',
                                    }}
                                >
                                    <Logout />
                                </IconButton>
                            </Tooltip>
                        )}
                    </Stack>
                </Stack>

                <Box
                    sx={{
                        pb: pendingAction ? 0.6 : 1.1,
                        overflowX: 'auto',
                        '&::-webkit-scrollbar': { display: 'none' },
                        scrollbarWidth: 'none',
                    }}
                >
                    <Stack direction="row" spacing={0.9} sx={{ minWidth: 'max-content' }}>
                        {navItems.map((item) => {
                            const selected = normalizedActive === item.key;
                            return (
                                <Button
                                    key={item.key}
                                    variant={selected ? 'contained' : 'outlined'}
                                    size="small"
                                    startIcon={item.icon}
                                    onClick={() => navigateWithGuard(item.path)}
                                    sx={{
                                        px: 1.25,
                                        borderRadius: 999,
                                        borderColor: selected
                                            ? 'transparent'
                                            : alpha('#f97316', darkMode ? 0.38 : 0.24),
                                        bgcolor: selected
                                            ? undefined
                                            : alpha('#f97316', darkMode ? 0.12 : 0.05),
                                        color: selected
                                            ? undefined
                                            : (darkMode ? '#fed7aa' : '#9a3412'),
                                        textTransform: 'none',
                                        fontWeight: 700,
                                        '&:hover': {
                                            bgcolor: selected
                                                ? undefined
                                                : alpha('#f97316', darkMode ? 0.18 : 0.09),
                                            borderColor: selected
                                                ? 'transparent'
                                                : alpha('#f97316', darkMode ? 0.52 : 0.34),
                                        },
                                    }}
                                >
                                    {item.label}
                                </Button>
                            );
                        })}
                    </Stack>
                </Box>

                {pendingAction && (
                    <Paper
                        sx={{
                            mb: 1.1,
                            p: 1,
                            border: `1px solid ${alpha('#f59e0b', darkMode ? 0.52 : 0.4)}`,
                            bgcolor: darkMode ? alpha('#f59e0b', 0.16) : alpha('#f59e0b', 0.08),
                        }}
                    >
                        <Stack
                            direction={{ xs: 'column', sm: 'row' }}
                            spacing={1}
                            justifyContent="space-between"
                            alignItems={{ xs: 'flex-start', sm: 'center' }}
                        >
                            <Typography variant="body2" sx={{ color: 'text.primary' }}>
                                You have an active interview. Continuing will end this session.
                            </Typography>
                            <Stack direction="row" spacing={1}>
                                <Button size="small" variant="outlined" onClick={closeExitConfirm}>
                                    Stay
                                </Button>
                                <Button size="small" color="warning" variant="contained" onClick={confirmExitAndContinue}>
                                    {pendingAction.type === 'logout' ? 'End and Sign Out' : 'End and Continue'}
                                </Button>
                            </Stack>
                        </Stack>
                    </Paper>
                )}
            </Container>
        </AppBar>
    );
}
