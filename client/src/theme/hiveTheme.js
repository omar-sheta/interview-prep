import { createTheme } from '@mui/material/styles';

export function createHiveTheme(mode = 'light') {
    const isDark = mode === 'dark';
    const ink = '#18202C';
    const ember = '#FF6A1A';
    const amber = '#F6A100';
    const sand = '#F7F1E7';

    return createTheme({
        palette: {
            mode,
            primary: { main: ember, dark: '#D94A0D', light: '#FF9A4D' },
            secondary: { main: amber, dark: '#BE7D00', light: '#FFD36A' },
            background: isDark
                ? { default: '#080A0D', paper: '#12151B' }
                : { default: sand, paper: '#FFFDF8' },
            text: isDark
                ? { primary: '#F8F4EC', secondary: '#A9B1BC' }
                : { primary: ink, secondary: '#697386' },
            success: { main: '#22A06B' },
            warning: { main: isDark ? '#FFBE45' : '#C98000' },
            error: { main: '#D92D20' },
            divider: isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(24, 32, 44, 0.1)',
        },
        shape: { borderRadius: 20 },
        typography: {
            fontFamily: '"Manrope", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
            h3: {
                fontFamily: '"Space Grotesk", "Manrope", sans-serif',
                fontWeight: 700,
                letterSpacing: '-0.045em',
                lineHeight: 0.98,
            },
            h4: {
                fontFamily: '"Space Grotesk", "Manrope", sans-serif',
                fontWeight: 700,
                letterSpacing: '-0.04em',
                lineHeight: 1.04,
            },
            h5: {
                fontFamily: '"Space Grotesk", "Manrope", sans-serif',
                fontWeight: 700,
                letterSpacing: '-0.03em',
            },
            h6: { fontWeight: 800, letterSpacing: '-0.018em' },
            subtitle1: { fontWeight: 800 },
            body1: { lineHeight: 1.65 },
            body2: { lineHeight: 1.65 },
            button: { textTransform: 'none', fontWeight: 800, letterSpacing: '-0.01em' },
        },
        components: {
            MuiCssBaseline: {
                styleOverrides: {
                    body: {
                        backgroundColor: isDark ? '#080A0D' : sand,
                        color: isDark ? '#F8F4EC' : ink,
                        backgroundImage: isDark
                            ? 'radial-gradient(circle at 16% 0%, rgba(255,106,26,0.2), transparent 28%), radial-gradient(circle at 85% 8%, rgba(246,161,0,0.12), transparent 24%), linear-gradient(180deg, #080A0D 0%, #101318 100%)'
                            : 'radial-gradient(circle at 16% 0%, rgba(255,106,26,0.16), transparent 28%), radial-gradient(circle at 88% 6%, rgba(24,32,44,0.08), transparent 26%), linear-gradient(180deg, #F9F3EA 0%, #F5EDE0 100%)',
                        backgroundAttachment: 'fixed',
                    },
                },
            },
            MuiPaper: {
                styleOverrides: {
                    root: {
                        backgroundImage: 'none',
                        border: isDark ? '1px solid rgba(255, 255, 255, 0.09)' : '1px solid rgba(24, 32, 44, 0.09)',
                        boxShadow: isDark
                            ? '0 24px 70px rgba(0, 0, 0, 0.42)'
                            : '0 24px 70px rgba(80, 52, 22, 0.09)',
                    },
                },
            },
            MuiTextField: {
                styleOverrides: {
                    root: {
                        '& .MuiOutlinedInput-root': {
                            borderRadius: 16,
                            backgroundColor: isDark ? 'rgba(255,255,255,0.045)' : 'rgba(255,255,255,0.84)',
                            boxShadow: isDark ? 'inset 0 1px 0 rgba(255,255,255,0.04)' : 'inset 0 1px 0 rgba(255,255,255,0.72)',
                            '& fieldset': { borderColor: isDark ? 'rgba(255, 255, 255, 0.12)' : 'rgba(24, 32, 44, 0.12)' },
                            '&:hover fieldset': { borderColor: isDark ? 'rgba(255, 106, 26, 0.46)' : 'rgba(255, 106, 26, 0.38)' },
                            '&.Mui-focused fieldset': { borderColor: ember, borderWidth: 1.5 },
                        },
                    },
                },
            },
            MuiButton: {
                styleOverrides: {
                    root: {
                        borderRadius: 16,
                        minHeight: 42,
                        paddingInline: 18,
                        transition: 'transform 160ms ease, box-shadow 160ms ease, background 160ms ease, border-color 160ms ease',
                        '&:hover': {
                            transform: 'translateY(-1px)',
                        },
                    },
                    containedPrimary: {
                        color: '#FFFFFF',
                        background: `linear-gradient(135deg, ${ink} 0%, #2B1B13 46%, ${ember} 100%)`,
                        boxShadow: '0 14px 30px rgba(255, 106, 26, 0.24)',
                        '&:hover': {
                            background: `linear-gradient(135deg, #0F1723 0%, #332016 46%, ${ember} 100%)`,
                            boxShadow: '0 18px 42px rgba(255, 106, 26, 0.3)',
                        },
                    },
                    outlined: {
                        borderColor: isDark ? 'rgba(255,255,255,0.18)' : 'rgba(24,32,44,0.16)',
                        color: isDark ? '#F8F4EC' : ink,
                        backgroundColor: isDark ? 'rgba(255,255,255,0.035)' : 'rgba(255,255,255,0.68)',
                        backdropFilter: 'blur(18px)',
                        '&:hover': {
                            borderColor: ember,
                            backgroundColor: isDark ? 'rgba(255,106,26,0.1)' : 'rgba(255,106,26,0.08)',
                        },
                    },
                    text: {
                        color: isDark ? '#F8F4EC' : ink,
                    },
                },
            },
            MuiChip: {
                styleOverrides: {
                    root: {
                        borderRadius: 999,
                        fontWeight: 700,
                        letterSpacing: '-0.01em',
                    },
                    outlined: {
                        backgroundColor: isDark ? 'rgba(255,255,255,0.035)' : 'rgba(255,255,255,0.58)',
                        borderColor: isDark ? 'rgba(255,255,255,0.14)' : 'rgba(24,32,44,0.13)',
                    },
                },
            },
            MuiToggleButton: {
                styleOverrides: {
                    root: {
                        borderRadius: 14,
                        borderColor: isDark ? 'rgba(255,255,255,0.12)' : 'rgba(24,32,44,0.12)',
                        fontWeight: 800,
                        '&.Mui-selected': {
                            color: '#FFFFFF',
                            background: `linear-gradient(135deg, ${ink}, ${ember})`,
                            '&:hover': {
                                background: `linear-gradient(135deg, ${ink}, ${ember})`,
                            },
                        },
                    },
                },
            },
        },
    });
}

const hiveTheme = createHiveTheme('light');
export default hiveTheme;
