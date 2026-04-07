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
                backdropFilter: 'blur(16px)',
                borderBottom: darkMode
                    ? '1px solid rgba(255, 255, 255, 0.08)'
                    : '1px solid rgba(0, 0, 0, 0.04)',
                bgcolor: darkMode ? 'rgba(10, 10, 10, 0.75)' : 'rgba(255, 255, 255, 0.85)',
                boxShadow: darkMode ? '0 4px 30px rgba(0, 0, 0, 0.6)' : '0 4px 30px rgba(0, 0, 0, 0.03)'
            }}
        >
            <Container maxWidth="lg">
                <Stack
                    direction="row"
                    alignItems="center"
                    justifyContent="space-between"
                    sx={{
                        minHeight: 64,
                        py: 0.5,
                    }}
                >
                    {/* LEFT SECTION: Brand & Nav Links */}
                    <Stack direction="row" spacing={4} alignItems="center">
                        {/* Brand */}
                        <Stack direction="row" spacing={1.2} alignItems="center" sx={{ cursor: 'pointer' }} onClick={() => navigateWithGuard('/interviews')}>
                            <Box
                                sx={{
                                    width: 32,
                                    height: 32,
                                    borderRadius: '50%',
                                    display: 'grid',
                                    placeItems: 'center',
                                    bgcolor: 'primary.main',
                                    color: '#fff',
                                    boxShadow: '0 2px 8px rgba(249, 115, 22, 0.4)'
                                }}
                            >
                                <Hive sx={{ fontSize: 18 }} />
                            </Box>
                            <Typography variant="h6" sx={{ lineHeight: 1, letterSpacing: '-0.02em', fontSize: '1.2rem', fontWeight: 800, color: 'text.primary' }}>
                                BeePrepared
                            </Typography>
                        </Stack>

                        {/* Desktop Navigation Links */}
                        <Stack direction="row" spacing={0.5} sx={{ display: { xs: 'none', md: 'flex' } }}>
                            {navItems.map((item) => {
                                const selected = normalizedActive === item.key;
                                return (
                                    <Button
                                        key={item.key}
                                        id={`nav-${item.key}`}
                                        onClick={() => navigateWithGuard(item.path)}
                                        disableRipple
                                        sx={{
                                            px: 1.5,
                                            py: 1,
                                            minWidth: 'auto',
                                            color: selected ? (darkMode ? '#fed7aa' : '#c2410c') : 'text.secondary',
                                            fontWeight: selected ? 700 : 500,
                                            textTransform: 'none',
                                            fontSize: '0.95rem',
                                            position: 'relative',
                                            '&:hover': {
                                                bgcolor: 'transparent',
                                                color: darkMode ? '#ffedd5' : '#9a3412',
                                            },
                                            '&::after': {
                                                content: '""',
                                                position: 'absolute',
                                                bottom: 4,
                                                left: selected ? 12 : '50%',
                                                right: selected ? 12 : '50%',
                                                height: 2,
                                                bgcolor: darkMode ? '#f97316' : '#ea580c',
                                                transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
                                                opacity: selected ? 1 : 0,
                                                borderRadius: 1,
                                            },
                                            '&:hover::after': {
                                                left: 12,
                                                right: 12,
                                                opacity: 1,
                                                bgcolor: darkMode ? '#fdba74' : '#c2410c',
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
                    <Stack direction="row" spacing={2} alignItems="center">
                        {quickActionLabel && typeof onQuickAction === 'function' && (
                            <Button
                                id="btn-quick-action"
                                variant="contained"
                                size="small"
                                startIcon={quickActionIcon}
                                onClick={onQuickAction}
                                sx={{
                                    borderRadius: 999,
                                    px: 2.5,
                                    py: 0.8,
                                    textTransform: 'none',
                                    fontWeight: 700,
                                    letterSpacing: '0.01em',
                                    boxShadow: darkMode ? '0 4px 14px rgba(249, 115, 22, 0.25)' : '0 4px 14px rgba(234, 88, 12, 0.3)',
                                    background: 'linear-gradient(135deg, #f97316 0%, #ea580c 100%)',
                                    '&:hover': {
                                        background: 'linear-gradient(135deg, #ea580c 0%, #c2410c 100%)',
                                        boxShadow: darkMode ? '0 6px 20px rgba(249, 115, 22, 0.4)' : '0 6px 20px rgba(234, 88, 12, 0.4)',
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
                                        transition: 'all 0.2s',
                                        '&:hover': { bgcolor: alpha('#f97316', 0.1), color: '#f97316', transform: 'rotate(15deg)' }
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
