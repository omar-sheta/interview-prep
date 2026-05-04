import { createTheme } from '@mui/material/styles';

export function createHiveTheme(mode = 'light') {
    const isDark = mode === 'dark';

    return createTheme({
        palette: {
            mode,
            primary: { main: '#E85D04', dark: '#B94600', light: '#FB923C' },
            secondary: { main: '#1F2937' },
            background: isDark
                ? { default: '#0A0A0A', paper: '#171717' }
                : { default: '#FBF7EF', paper: '#FFFFFF' },
            text: isDark
                ? { primary: '#FAFAFA', secondary: '#A3A3A3' }
                : { primary: '#1F2937', secondary: '#6B7280' },
            success: { main: '#16A34A' },
            warning: { main: isDark ? '#FBBF24' : '#D97706' },
            error: { main: '#DC2626' },
            divider: isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(31, 41, 55, 0.1)',
        },
        shape: { borderRadius: 16 },
        typography: {
            fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
            h4: { fontWeight: 750, letterSpacing: '-0.02em' },
            h5: { fontWeight: 700, letterSpacing: '-0.015em' },
            h6: { fontWeight: 650 },
            button: { textTransform: 'none', fontWeight: 650 },
        },
        components: {
            MuiCssBaseline: {
                styleOverrides: {
                    body: {
                        backgroundColor: isDark ? '#0A0A0A' : '#FBF7EF',
                        color: isDark ? '#FAFAFA' : '#1F2937',
                        backgroundImage: isDark
                            ? 'radial-gradient(rgba(245, 158, 11, 0.06) 1px, transparent 1px)'
                            : 'linear-gradient(180deg, rgba(255,255,255,0.62), rgba(251,247,239,0))',
                        backgroundSize: '26px 26px',
                    },
                },
            },
            MuiPaper: {
                styleOverrides: {
                    root: {
                        backgroundImage: 'none',
                        border: isDark ? '1px solid rgba(255, 255, 255, 0.08)' : '1px solid rgba(31, 41, 55, 0.08)',
                        boxShadow: isDark ? '0 16px 40px rgba(0, 0, 0, 0.32)' : '0 18px 46px rgba(31, 41, 55, 0.06)',
                    },
                },
            },
            MuiTextField: {
                styleOverrides: {
                    root: {
                        '& .MuiOutlinedInput-root': {
                            borderRadius: 14,
                            backgroundColor: isDark ? '#121212' : '#FFFFFF',
                            '& fieldset': { borderColor: isDark ? 'rgba(255, 255, 255, 0.14)' : 'rgba(31, 41, 55, 0.16)' },
                            '&:hover fieldset': { borderColor: isDark ? 'rgba(251, 146, 60, 0.45)' : 'rgba(31, 41, 55, 0.34)' },
                            '&.Mui-focused fieldset': { borderColor: '#E85D04' },
                        },
                    },
                },
            },
            MuiButton: {
                styleOverrides: {
                    root: {
                        borderRadius: 12,
                        minHeight: 40,
                        paddingInline: 18,
                        letterSpacing: '-0.01em',
                        transition: 'transform 160ms ease, box-shadow 160ms ease, background-color 160ms ease, border-color 160ms ease',
                        '&:hover': { transform: 'translateY(-1px)' },
                    },
                    containedPrimary: {
                        color: '#FFFFFF',
                        background: isDark ? '#F97316' : '#1F2937',
                        boxShadow: isDark ? '0 10px 22px rgba(249, 115, 22, 0.22)' : '0 10px 22px rgba(31, 41, 55, 0.16)',
                        '&:hover': {
                            background: isDark ? '#EA580C' : '#111827',
                            boxShadow: isDark ? '0 14px 28px rgba(249, 115, 22, 0.28)' : '0 14px 28px rgba(31, 41, 55, 0.2)',
                        },
                    },
                    outlined: {
                        borderColor: isDark ? 'rgba(255,255,255,0.16)' : 'rgba(31,41,55,0.18)',
                        color: isDark ? '#FAFAFA' : '#1F2937',
                        backgroundColor: isDark ? 'rgba(255,255,255,0.03)' : 'rgba(255,255,255,0.72)',
                        '&:hover': {
                            borderColor: '#E85D04',
                            backgroundColor: isDark ? 'rgba(249,115,22,0.08)' : 'rgba(232,93,4,0.06)',
                        },
                    },
                },
            },
            MuiChip: {
                styleOverrides: {
                    root: {
                        borderRadius: 999,
                    },
                },
            },
        },
    });
}

const hiveTheme = createHiveTheme('light');
export default hiveTheme;
