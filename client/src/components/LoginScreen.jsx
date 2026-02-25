import { useMemo, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import useInterviewStore from '@/store/useInterviewStore';
import {
    Container,
    Card,
    CardContent,
    Typography,
    TextField,
    Button,
    Box,
    Alert,
    CircularProgress,
    createTheme,
    ThemeProvider,
    CssBaseline,
    InputAdornment,
    IconButton,
    Tooltip,
} from '@mui/material';
import { DarkMode, LightMode } from '@mui/icons-material';
import { Key, User } from 'lucide-react';

function createAuthTheme(mode) {
    const isDark = mode === 'dark';
    return createTheme({
    palette: {
        mode,
        primary: {
            main: '#F97316',
            light: '#FB923C',
            dark: '#EA580C',
        },
        secondary: {
            main: '#FBBF24',
        },
        background: {
            default: isDark ? '#0A0A0A' : '#FFFBF0',
            paper: isDark ? '#121212' : '#FFFFFF',
        },
        text: {
            primary: isDark ? '#FAFAFA' : '#1F2937',
            secondary: isDark ? '#A3A3A3' : '#6B7280',
        },
    },
    typography: {
        fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
    },
    shape: {
        borderRadius: 16,
    },
});
}

const LoginPage = () => {
    const navigate = useNavigate();
    const { login, darkMode, toggleDarkMode } = useInterviewStore();
    const [isLoading, setIsLoading] = useState(false);
    const [form, setForm] = useState({ username: '', password: '' });
    const [error, setError] = useState('');
    const theme = useMemo(() => createAuthTheme(darkMode ? 'dark' : 'light'), [darkMode]);
    const ui = darkMode
        ? {
            pageBg: 'linear-gradient(135deg, #0A0A0A 0%, #1A1A1A 50%, #0A0A0A 100%)',
            orb1: 'rgba(249, 115, 22, 0.08)',
            orb2: 'rgba(251, 191, 36, 0.06)',
            cardBg: 'rgba(26, 26, 26, 0.9)',
            cardBorder: '1px solid rgba(249, 115, 22, 0.15)',
            textMain: '#FAFAFA',
            textSub: '#A3A3A3',
            inputBg: '#1A1A1A',
            inputText: '#FAFAFA',
        }
        : {
            pageBg: 'linear-gradient(135deg, #FFFDF4 0%, #FFF7E6 45%, #FFFDF4 100%)',
            orb1: 'rgba(249, 115, 22, 0.12)',
            orb2: 'rgba(251, 191, 36, 0.1)',
            cardBg: 'rgba(255, 255, 255, 0.92)',
            cardBorder: '1px solid rgba(249, 115, 22, 0.2)',
            textMain: '#1F2937',
            textSub: '#6B7280',
            inputBg: '#FFFFFF',
            inputText: '#111827',
        };

    const handleChange = (event) => {
        const { name, value } = event.target;
        setForm((prev) => ({ ...prev, [name]: value }));
    };

    const handleSubmit = async (event) => {
        event.preventDefault();
        setError('');

        // Quick validation
        if (!form.username || !form.password) {
            setError('Please enter your credentials');
            return;
        }

        try {
            setIsLoading(true);
            await login(form.username, form.password);
            navigate('/');
        } catch (err) {
            console.error(err);
            setError(err.message || 'Login failed. Please check your credentials.');
            setIsLoading(false);
        }
    };

    return (
        <ThemeProvider theme={theme}>
            <CssBaseline />
            {/* Full screen wrapper with dark hive background */}
            <Box
                sx={{
                    minHeight: '100vh',
                    width: '100vw',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    background: ui.pageBg,
                    position: 'relative',
                    overflow: 'hidden',
                }}
            >
                <Box sx={{ position: 'absolute', top: 14, right: 14, zIndex: 3 }}>
                    <Tooltip title={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}>
                        <IconButton onClick={toggleDarkMode} sx={{ color: ui.textMain }}>
                            {darkMode ? <LightMode /> : <DarkMode />}
                        </IconButton>
                    </Tooltip>
                </Box>
                {/* Orange glow decoration */}
                <Box
                    sx={{
                        position: 'absolute',
                        top: -100,
                        left: -100,
                        width: 400,
                        height: 400,
                        borderRadius: '50%',
                        background: ui.orb1,
                        filter: 'blur(100px)',
                    }}
                />
                <Box
                    sx={{
                        position: 'absolute',
                        bottom: -150,
                        right: -150,
                        width: 500,
                        height: 500,
                        borderRadius: '50%',
                        background: ui.orb2,
                        filter: 'blur(120px)',
                    }}
                />

                <Container maxWidth="xs" sx={{ position: 'relative', zIndex: 1 }}>
                    <Box>
                        <Card
                            elevation={0}
                            sx={{
                                p: 2,
                                borderRadius: 4,
                                boxShadow: '0 20px 60px -12px rgba(0,0,0,0.6), inset 0 1px 0 rgba(251, 191, 36, 0.05)',
                                background: ui.cardBg,
                                backdropFilter: 'blur(16px)',
                                border: ui.cardBorder,
                            }}
                        >
                            <CardContent sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', pt: 4, pb: 4 }}>

                                {/* Logo */}
                                <Box
                                    component="img"
                                    src="/logos/hive-logo.png"
                                    alt="Hive"
                                    sx={{ height: 64, mb: 3, objectFit: 'contain' }}
                                />

                                <Typography variant="h5" fontWeight="700" sx={{ color: ui.textMain, mb: 1 }}>
                                    Welcome Back
                                </Typography>
                                <Typography variant="body2" sx={{ color: ui.textSub, mb: 4 }}>
                                    Sign in to access your dashboard
                                </Typography>

                                <Box component="form" onSubmit={handleSubmit} noValidate sx={{ width: '100%' }}>
                                    <TextField
                                        margin="normal"
                                        fullWidth
                                        id="username"
                                        placeholder="Username *"
                                        name="username"
                                        autoComplete="username"
                                        autoFocus
                                        value={form.username}
                                        onChange={handleChange}
                                        disabled={isLoading}
                                        sx={{
                                            '& .MuiOutlinedInput-root': {
                                                backgroundColor: ui.inputBg,
                                                borderRadius: 3,
                                                '& fieldset': { borderColor: 'rgba(249, 115, 22, 0.2)' },
                                                '&:hover fieldset': { borderColor: 'rgba(249, 115, 22, 0.4)' },
                                                '&.Mui-focused fieldset': { borderColor: '#F97316' },
                                            },
                                            '& .MuiInputBase-input': { py: 1.5, px: 2, color: ui.inputText },
                                        }}
                                        InputProps={{
                                            endAdornment: (
                                                <InputAdornment position="end">
                                                    <User size={18} color="#F97316" />
                                                </InputAdornment>
                                            ),
                                        }}
                                    />

                                    <TextField
                                        margin="normal"
                                        fullWidth
                                        name="password"
                                        placeholder="Password *"
                                        type="password"
                                        id="password"
                                        autoComplete="current-password"
                                        value={form.password}
                                        onChange={handleChange}
                                        disabled={isLoading}
                                        sx={{
                                            '& .MuiOutlinedInput-root': {
                                                backgroundColor: ui.inputBg,
                                                borderRadius: 3,
                                                '& fieldset': { borderColor: 'rgba(249, 115, 22, 0.2)' },
                                                '&:hover fieldset': { borderColor: 'rgba(249, 115, 22, 0.4)' },
                                                '&.Mui-focused fieldset': { borderColor: '#F97316' },
                                            },
                                            '& .MuiInputBase-input': { py: 1.5, px: 2, color: ui.inputText },
                                        }}
                                        InputProps={{
                                            endAdornment: (
                                                <InputAdornment position="end">
                                                    <Key size={18} color="#F97316" />
                                                </InputAdornment>
                                            ),
                                        }}
                                    />

                                    {error && (
                                        <Alert severity="error" sx={{ mt: 2, borderRadius: 2 }}>
                                            {error}
                                        </Alert>
                                    )}

                                    <Button
                                        type="submit"
                                        fullWidth
                                        disableElevation
                                        sx={{
                                            mt: 4,
                                            mb: 2,
                                            py: 1.5,
                                            borderRadius: 3,
                                            textTransform: 'none',
                                            fontSize: '1rem',
                                            fontWeight: 600,
                                            background: 'linear-gradient(135deg, #F97316 0%, #EA580C 100%)',
                                            color: 'white',
                                            boxShadow: '0 4px 20px rgba(249, 115, 22, 0.3)',
                                            '&:hover': {
                                                background: 'linear-gradient(135deg, #EA580C 0%, #C2410C 100%)',
                                                boxShadow: '0 6px 25px rgba(249, 115, 22, 0.4)',
                                            },
                                        }}
                                        disabled={isLoading}
                                    >
                                        {isLoading ? <CircularProgress size={24} color="inherit" /> : 'Sign In'}
                                    </Button>

                                    <Box sx={{ textAlign: 'center', mt: 2 }}>
                                        <Typography variant="caption" sx={{ color: ui.textSub }}>
                                            Don't have an account?{' '}
                                            <Link to="/signup" style={{ color: '#F97316', fontWeight: 600, textDecoration: 'none' }}>
                                                Sign Up
                                            </Link>
                                        </Typography>
                                    </Box>
                                </Box>
                            </CardContent>
                        </Card>
                    </Box>
                </Container>
            </Box>
        </ThemeProvider>
    );
};

export default LoginPage;
