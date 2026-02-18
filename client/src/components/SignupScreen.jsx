import { useState, useEffect } from 'react';
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
    InputAdornment
} from '@mui/material';
import { motion } from 'framer-motion';
import { Key, User, Mail } from 'lucide-react';

// --- Hive & Bees Dark Theme ---
const localTheme = createTheme({
    palette: {
        mode: 'dark',
        primary: {
            main: '#F97316',
            light: '#FB923C',
            dark: '#EA580C',
        },
        secondary: {
            main: '#FBBF24',
        },
        background: {
            default: '#0A0A0A',
            paper: '#121212',
        },
        text: {
            primary: '#FAFAFA',
            secondary: '#A3A3A3',
        },
    },
    typography: {
        fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
    },
    shape: {
        borderRadius: 16,
    },
});

const SignupScreen = () => {
    const navigate = useNavigate();
    // Destructure logout to force clean session
    const { signup, logout } = useInterviewStore();
    const [isLoading, setIsLoading] = useState(false);
    const [form, setForm] = useState({ name: '', email: '', password: '' });
    const [error, setError] = useState('');

    // Force logout on mount to ensure we are creating a NEW account
    useEffect(() => {
        logout();
    }, []); // Only on mount

    const handleChange = (event) => {
        const { name, value } = event.target;
        setForm((prev) => ({ ...prev, [name]: value }));
    };

    const handleSignup = async (event) => {
        event.preventDefault();
        setError('');

        // Quick validation
        if (!form.name || !form.email || !form.password) {
            setError('Please fill in all fields');
            return;
        }

        try {
            setIsLoading(true);
            await signup(form.name, form.email, form.password);
            navigate('/dashboard');
        } catch (err) {
            console.error(err);
            setError(err.message || 'Signup failed. Please try again.');
            setIsLoading(false);
        }
    };

    return (
        <ThemeProvider theme={localTheme}>
            <CssBaseline />
            <Box
                sx={{
                    minHeight: '100vh',
                    width: '100vw',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    background: 'linear-gradient(135deg, #0A0A0A 0%, #1A1A1A 50%, #0A0A0A 100%)',
                    position: 'relative',
                    overflow: 'hidden',
                }}
            >
                {/* Orange glow decoration */}
                <Box
                    sx={{
                        position: 'absolute',
                        bottom: -100,
                        right: -100,
                        width: 400,
                        height: 400,
                        borderRadius: '50%',
                        background: 'rgba(249, 115, 22, 0.08)',
                        filter: 'blur(100px)',
                    }}
                />
                <Box
                    sx={{
                        position: 'absolute',
                        top: -150,
                        left: -150,
                        width: 500,
                        height: 500,
                        borderRadius: '50%',
                        background: 'rgba(251, 191, 36, 0.06)',
                        filter: 'blur(120px)',
                    }}
                />

                <Container maxWidth="xs" sx={{ position: 'relative', zIndex: 1 }}>
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.5 }}
                    >
                        <Card
                            elevation={0}
                            sx={{
                                p: 2,
                                borderRadius: 4,
                                boxShadow: '0 20px 60px -12px rgba(0,0,0,0.6), inset 0 1px 0 rgba(251, 191, 36, 0.05)',
                                background: 'rgba(26, 26, 26, 0.9)',
                                backdropFilter: 'blur(16px)',
                                border: '1px solid rgba(249, 115, 22, 0.15)',
                            }}
                        >
                            <CardContent sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', pt: 4, pb: 4 }}>

                                {/* Logo */}
                                <Box
                                    component="img"
                                    src="/logos/hive-logo.png"
                                    alt="Hive"
                                    sx={{ height: 56, mb: 2, objectFit: 'contain' }}
                                />

                                <Typography variant="h5" fontWeight="700" sx={{ color: '#FAFAFA', mb: 1 }}>
                                    Create Account
                                </Typography>
                                <Typography variant="body2" sx={{ color: '#A3A3A3', mb: 4 }}>
                                    Master your technical interviews
                                </Typography>

                                <Box component="form" onSubmit={handleSignup} noValidate sx={{ width: '100%' }}>
                                    <TextField
                                        margin="normal"
                                        fullWidth
                                        id="name"
                                        placeholder="Full Name *"
                                        name="name"
                                        autoComplete="name"
                                        autoFocus
                                        value={form.name}
                                        onChange={handleChange}
                                        disabled={isLoading}
                                        sx={{
                                            '& .MuiOutlinedInput-root': {
                                                backgroundColor: '#1A1A1A',
                                                borderRadius: 3,
                                                '& fieldset': { borderColor: 'rgba(249, 115, 22, 0.2)' },
                                                '&:hover fieldset': { borderColor: 'rgba(249, 115, 22, 0.4)' },
                                                '&.Mui-focused fieldset': { borderColor: '#F97316' },
                                            },
                                            '& .MuiInputBase-input': { py: 1.5, px: 2, color: '#FAFAFA' },
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
                                        id="email"
                                        placeholder="Email Address *"
                                        name="email"
                                        autoComplete="email"
                                        value={form.email}
                                        onChange={handleChange}
                                        disabled={isLoading}
                                        sx={{
                                            '& .MuiOutlinedInput-root': {
                                                backgroundColor: '#1A1A1A',
                                                borderRadius: 3,
                                                '& fieldset': { borderColor: 'rgba(249, 115, 22, 0.2)' },
                                                '&:hover fieldset': { borderColor: 'rgba(249, 115, 22, 0.4)' },
                                                '&.Mui-focused fieldset': { borderColor: '#F97316' },
                                            },
                                            '& .MuiInputBase-input': { py: 1.5, px: 2, color: '#FAFAFA' },
                                        }}
                                        InputProps={{
                                            endAdornment: (
                                                <InputAdornment position="end">
                                                    <Mail size={18} color="#FBBF24" />
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
                                        autoComplete="new-password"
                                        value={form.password}
                                        onChange={handleChange}
                                        disabled={isLoading}
                                        sx={{
                                            '& .MuiOutlinedInput-root': {
                                                backgroundColor: '#1A1A1A',
                                                borderRadius: 3,
                                                '& fieldset': { borderColor: 'rgba(249, 115, 22, 0.2)' },
                                                '&:hover fieldset': { borderColor: 'rgba(249, 115, 22, 0.4)' },
                                                '&.Mui-focused fieldset': { borderColor: '#F97316' },
                                            },
                                            '& .MuiInputBase-input': { py: 1.5, px: 2, color: '#FAFAFA' },
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
                                        {isLoading ? <CircularProgress size={24} color="inherit" /> : 'Create Account'}
                                    </Button>

                                    <Box sx={{ textAlign: 'center', mt: 2 }}>
                                        <Typography variant="caption" sx={{ color: '#A3A3A3' }}>
                                            Already have an account?{' '}
                                            <Link to="/login" style={{ color: '#F97316', fontWeight: 600, textDecoration: 'none' }}>
                                                Log In
                                            </Link>
                                        </Typography>
                                    </Box>
                                </Box>
                            </CardContent>
                        </Card>
                    </motion.div>
                </Container>
            </Box>
        </ThemeProvider>
    );
};

export default SignupScreen;
