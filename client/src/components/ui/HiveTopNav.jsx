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
import { Hive, History, SmartToy, Tune, AdminPanelSettings, DarkMode, LightMode, Logout } from '@mui/icons-material';
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
    const { darkMode, toggleDarkMode, logout, endInterview, interviewActive, isAdmin } = useInterviewStore();
    const isInterviewRoute = location.pathname === '/session';
    const shouldConfirmExit = Boolean(isInterviewRoute && interviewActive);
    const [pendingAction, setPendingAction] = useState(null);

    useEffect(() => {
        if (!shouldConfirmExit && pendingAction) {
            // eslint-disable-next-line react-hooks/set-state-in-effect -- Leaving the guarded session clears the pending navigation confirmation.
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
        { key: 'config', label: 'Profile', icon: <Tune />, path: '/config', visible: showConfiguration },
        { key: 'history', label: 'History', icon: <History />, path: '/history', visible: showHistory },
        { key: 'admin', label: 'Admin', icon: <AdminPanelSettings />, path: '/admin', visible: Boolean(isAdmin) },
    ].filter((item) => item.visible);

    return (
        <AppBar
            position="sticky"
            color="transparent"
            elevation={0}
            sx={{
                backdropFilter: 'blur(22px)',
                borderBottom: darkMode
                    ? '1px solid rgba(255, 255, 255, 0.08)'
                    : '1px solid rgba(24, 32, 44, 0.08)',
                bgcolor: darkMode ? 'rgba(8, 10, 13, 0.72)' : 'rgba(255, 253, 248, 0.78)',
                boxShadow: darkMode ? '0 10px 40px rgba(0, 0, 0, 0.45)' : '0 10px 40px rgba(80, 52, 22, 0.06)'
            }}
        >
            <Container maxWidth="xl">
                <Stack
                    direction={{ xs: 'column', md: 'row' }}
                    alignItems="center"
                    justifyContent="space-between"
                    sx={{
                        minHeight: 78,
                        py: { xs: 1, md: 0.8 },
                        gap: { xs: 1, md: 0 },
                    }}
                >
                    {/* LEFT SECTION: Brand & Nav Links */}
                    <Stack
                        direction="row"
                        spacing={{ xs: 1.5, md: 4 }}
                        alignItems="center"
                        sx={{ minWidth: 0, width: { xs: '100%', md: 'auto' }, flex: { xs: '1 1 auto', md: '0 1 auto' } }}
                    >
                        {/* Brand */}
                        <Stack
                            direction="row"
                            spacing={1.25}
                            alignItems="center"
                            sx={{ cursor: 'pointer', minWidth: 0, flexShrink: 1 }}
                            onClick={() => navigateWithGuard('/interviews')}
                        >
                            <Box
                                sx={{
                                    width: { xs: 34, md: 38 },
                                    height: { xs: 34, md: 38 },
                                    borderRadius: 3,
                                    display: 'grid',
                                    placeItems: 'center',
                                    background: darkMode
                                        ? 'linear-gradient(135deg, #FF6A1A, #F6A100)'
                                        : 'linear-gradient(135deg, #18202C, #FF6A1A)',
                                    color: '#fff',
                                    boxShadow: darkMode
                                        ? '0 12px 26px rgba(255, 106, 26, 0.28)'
                                        : '0 12px 26px rgba(24, 32, 44, 0.18)'
                                }}
                            >
                                <Hive sx={{ fontSize: { xs: 17, md: 18 } }} />
                            </Box>
                            <Typography
                                variant="h6"
                                sx={{
                                    lineHeight: 1,
                                    letterSpacing: '-0.02em',
                                    fontSize: { xs: '1.02rem', sm: '1.1rem', md: '1.18rem' },
                                    fontWeight: 800,
                                    color: 'text.primary',
                                    whiteSpace: 'nowrap',
                                }}
                            >
                                BeePrepared
                            </Typography>
                        </Stack>

                        {/* Desktop Navigation Links */}
                        <Stack
                            direction="row"
                            spacing={0.25}
                            sx={{
                                display: { xs: 'none', md: 'flex' },
                                p: 0.45,
                                borderRadius: 999,
                                bgcolor: darkMode ? 'rgba(255,255,255,0.055)' : 'rgba(24,32,44,0.055)',
                                border: darkMode ? '1px solid rgba(255,255,255,0.08)' : '1px solid rgba(24,32,44,0.07)',
                            }}
                        >
                            {navItems.map((item) => {
                                const selected = normalizedActive === item.key;
                                return (
                                    <Button
                                        key={item.key}
                                        id={`nav-${item.key}`}
                                        onClick={() => navigateWithGuard(item.path)}
                                        disableRipple
                                        sx={{
                                            px: 1.75,
                                            py: 0.9,
                                            minWidth: 'auto',
                                            borderRadius: 999,
                                            color: selected ? (darkMode ? '#111827' : '#FFFFFF') : 'text.secondary',
                                            bgcolor: selected
                                                ? (darkMode ? '#F8F4EC' : '#18202C')
                                                : 'transparent',
                                            fontWeight: selected ? 800 : 700,
                                            textTransform: 'none',
                                            fontSize: '0.92rem',
                                            position: 'relative',
                                            boxShadow: selected
                                                ? (darkMode ? '0 8px 18px rgba(0,0,0,0.28)' : '0 10px 22px rgba(24,32,44,0.12)')
                                                : 'none',
                                            '&:hover': {
                                                bgcolor: selected
                                                    ? (darkMode ? '#F8F4EC' : '#18202C')
                                                    : (darkMode ? 'rgba(255,255,255,0.07)' : 'rgba(24,32,44,0.06)'),
                                                color: selected ? (darkMode ? '#111827' : '#FFFFFF') : 'text.primary',
                                            }
                                        }}
                                    >
                                        {item.label}
                                    </Button>
                                );
                            })}
                        </Stack>
                    </Stack>

                    {/* RIGHT SECTION: Quick Action & Icons */}
                    <Stack
                        direction="row"
                        spacing={{ xs: 0.75, sm: 1.25, md: 2 }}
                        alignItems="center"
                        justifyContent={{ xs: 'space-between', md: 'flex-end' }}
                        sx={{ flexShrink: 0, width: { xs: '100%', md: 'auto' }, ml: { xs: 0, md: 'auto' } }}
                    >
                        {quickActionLabel && typeof onQuickAction === 'function' && (
                            <Button
                                id="btn-quick-action"
                                variant="contained"
                                size="small"
                                startIcon={quickActionIcon}
                                onClick={onQuickAction}
                                sx={{
                                    borderRadius: 4,
                                    minWidth: 0,
                                    px: { xs: 1.5, sm: 1.8, md: 2.2 },
                                    py: { xs: 0.8, md: 1 },
                                    textTransform: 'none',
                                    fontWeight: 850,
                                    letterSpacing: '-0.01em',
                                    fontSize: { xs: '0.82rem', sm: '0.9rem' },
                                    boxShadow: darkMode ? '0 12px 26px rgba(255, 106, 26, 0.22)' : '0 12px 26px rgba(255, 106, 26, 0.2)',
                                    background: darkMode
                                        ? 'linear-gradient(135deg, #F8F4EC 0%, #FF6A1A 100%)'
                                        : 'linear-gradient(135deg, #18202C 0%, #FF6A1A 100%)',
                                    '& .MuiButton-startIcon': {
                                        marginLeft: 0,
                                        marginRight: 0.75,
                                    },
                                    '&:hover': {
                                        background: darkMode
                                            ? 'linear-gradient(135deg, #FFFFFF 0%, #FF6A1A 100%)'
                                            : 'linear-gradient(135deg, #0F1723 0%, #FF6A1A 100%)',
                                        boxShadow: darkMode ? '0 16px 32px rgba(255, 106, 26, 0.3)' : '0 16px 32px rgba(255, 106, 26, 0.3)',
                                        transform: 'translateY(-1px)',
                                    },
                                    transition: 'all 0.2s ease',
                                }}
                            >
                                {quickActionLabel}
                            </Button>
                        )}
                        
                        <Stack direction="row" spacing={0.5} alignItems="center">
                            <Tooltip title={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}>
                                <IconButton
                                    onClick={toggleDarkMode}
                                    size="small"
                                    sx={{
                                        color: 'text.secondary',
                                        bgcolor: darkMode ? 'rgba(255,255,255,0.05)' : 'rgba(24,32,44,0.055)',
                                        transition: 'all 0.2s',
                                        '&:hover': { bgcolor: alpha('#ff6a1a', 0.1), color: '#FF6A1A', transform: 'rotate(12deg)' }
                                    }}
                                >
                                    {darkMode ? <LightMode fontSize="small" /> : <DarkMode fontSize="small" />}
                                </IconButton>
                            </Tooltip>
                            {showSignOut && (
                                <Tooltip title="Sign out">
                                    <IconButton
                                        onClick={logoutWithGuard}
                                        size="small"
                                        sx={{
                                            color: 'text.secondary',
                                            bgcolor: darkMode ? 'rgba(255,255,255,0.05)' : 'rgba(24,32,44,0.055)',
                                            transition: 'all 0.2s',
                                            '&:hover': { bgcolor: alpha('#ef4444', 0.1), color: '#ef4444', transform: 'translateX(2px)' }
                                        }}
                                    >
                                        <Logout fontSize="small" />
                                    </IconButton>
                                </Tooltip>
                            )}
                        </Stack>
                    </Stack>
                </Stack>

                {/* Mobile Navigation Links (Hidden on md and up) */}
                <Box
                    sx={{
                        display: { xs: 'block', md: 'none' },
                        pb: pendingAction ? 0.6 : 1.2,
                        pt: 0.5,
                        overflowX: 'auto',
                        '&::-webkit-scrollbar': { display: 'none' },
                        scrollbarWidth: 'none',
                    }}
                >
                    <Stack direction="row" spacing={1} sx={{ minWidth: 'max-content' }}>
                        {navItems.map((item) => {
                            const selected = normalizedActive === item.key;
                            return (
                                <Button
                                    key={`mobile-${item.key}`}
                                    id={`nav-${item.key}-mobile`}
                                    size="small"
                                    onClick={() => navigateWithGuard(item.path)}
                                    sx={{
                                        px: 2,
                                        py: 0.5,
                                        borderRadius: 999,
                                        bgcolor: selected ? alpha('#f97316', darkMode ? 0.2 : 0.1) : 'transparent',
                                        color: selected ? (darkMode ? '#fed7aa' : '#c2410c') : 'text.secondary',
                                        textTransform: 'none',
                                        fontWeight: selected ? 700 : 500,
                                        '&:hover': {
                                            bgcolor: alpha('#f97316', 0.1),
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
                            mb: 1.5,
                            mt: { xs: 0, md: 1 },
                            p: 1.5,
                            borderRadius: 2,
                            border: `1px solid ${alpha('#f59e0b', darkMode ? 0.5 : 0.3)}`,
                            bgcolor: darkMode ? alpha('#f59e0b', 0.1) : alpha('#f59e0b', 0.05),
                            boxShadow: 'none'
                        }}
                    >
                        <Stack
                            direction={{ xs: 'column', sm: 'row' }}
                            spacing={2}
                            justifyContent="space-between"
                            alignItems={{ xs: 'flex-start', sm: 'center' }}
                        >
                            <Typography variant="body2" sx={{ color: 'text.primary', fontWeight: 500 }}>
                                ⚠️ You have an active interview. Continuing will end this session.
                            </Typography>
                            <Stack direction="row" spacing={1.5}>
                                <Button size="small" variant="outlined" color="inherit" onClick={closeExitConfirm} sx={{ borderRadius: 999 }}>
                                    Stay
                                </Button>
                                <Button size="small" color="warning" variant="contained" onClick={confirmExitAndContinue} sx={{ borderRadius: 999, boxShadow: 'none' }}>
                                    {pendingAction.type === 'logout' ? 'End & Sign Out' : 'End & Continue'}
                                </Button>
                            </Stack>
                        </Stack>
                    </Paper>
                )}
            </Container>
        </AppBar>
    );
}
