import { createTheme } from '@mui/material/styles';

export function createHiveTheme(mode = 'light') {
    const isDark = mode === 'dark';

    return createTheme({
        palette: {
            mode,
            primary: { main: '#F59E0B' },
            secondary: { main: '#FF9800' },
            background: isDark
                ? { default: '#0A0A0A', paper: '#171717' }
                : { default: '#FFFBF0', paper: '#FFFFFF' },
            text: isDark
                ? { primary: '#FAFAFA', secondary: '#A3A3A3' }
                : { primary: '#1F2937', secondary: '#6B7280' },
            success: { main: '#16A34A' },
            warning: { main: isDark ? '#FBBF24' : '#D97706' },
            error: { main: '#DC2626' },
            divider: isDark ? 'rgba(245, 158, 11, 0.25)' : 'rgba(217, 119, 6, 0.18)',
        },
        shape: { borderRadius: 14 },
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
                        backgroundColor: isDark ? '#0A0A0A' : '#FFFBF0',
                        color: isDark ? '#FAFAFA' : '#1F2937',
                        backgroundImage: isDark
                            ? 'radial-gradient(rgba(245, 158, 11, 0.06) 1px, transparent 1px)'
                            : 'radial-gradient(rgba(245, 158, 11, 0.09) 1px, transparent 1px)',
                        backgroundSize: '26px 26px',
                    },
                },
            },
            MuiPaper: {
                styleOverrides: {
                    root: {
                        backgroundImage: 'none',
                        border: isDark ? '1px solid rgba(245, 158, 11, 0.2)' : '1px solid rgba(217, 119, 6, 0.14)',
                        boxShadow: isDark ? '0 2px 12px rgba(0, 0, 0, 0.36)' : '0 2px 10px rgba(0, 0, 0, 0.04)',
                    },
                },
            },
            MuiTextField: {
                styleOverrides: {
                    root: {
                        '& .MuiOutlinedInput-root': {
                            borderRadius: 12,
                            backgroundColor: isDark ? '#121212' : '#FFFFFF',
                            '& fieldset': { borderColor: isDark ? 'rgba(245, 158, 11, 0.3)' : 'rgba(217, 119, 6, 0.26)' },
                            '&:hover fieldset': { borderColor: isDark ? 'rgba(245, 158, 11, 0.45)' : 'rgba(217, 119, 6, 0.45)' },
                            '&.Mui-focused fieldset': { borderColor: '#D97706' },
                        },
                    },
                },
            },
            MuiButton: {
                styleOverrides: {
                    containedPrimary: {
                        color: '#FFFFFF',
                        boxShadow: '0 3px 12px rgba(217, 119, 6, 0.22)',
                        '&:hover': { boxShadow: '0 5px 14px rgba(217, 119, 6, 0.28)' },
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
