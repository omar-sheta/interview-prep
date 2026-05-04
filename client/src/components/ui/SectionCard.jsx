import { Box, Paper, Stack, Typography } from '@mui/material';

export default function SectionCard({
    eyebrow = '',
    title,
    description = '',
    action = null,
    children,
    sx = {},
    contentSx = {},
}) {
    return (
        <Paper
            sx={{
                p: { xs: 2.4, md: 3.4 },
                borderRadius: { xs: 4, md: 5 },
                overflow: 'hidden',
                position: 'relative',
                background: (theme) => theme.palette.mode === 'dark'
                    ? 'linear-gradient(145deg, rgba(18,21,27,0.92), rgba(18,21,27,0.76))'
                    : 'linear-gradient(145deg, rgba(255,253,248,0.94), rgba(255,255,255,0.78))',
                backdropFilter: 'blur(24px)',
                ...sx,
            }}
        >
            {(title || description || action) && (
                <Stack
                    direction={{ xs: 'column', md: 'row' }}
                    justifyContent="space-between"
                    alignItems={{ xs: 'flex-start', md: 'center' }}
                    spacing={2}
                    sx={{ mb: children ? 2.4 : 0 }}
                >
                    <Box sx={{ minWidth: 0 }}>
                        {eyebrow && (
                            <Typography
                                variant="overline"
                                sx={{
                                    color: 'primary.main',
                                    letterSpacing: '0.18em',
                                    fontWeight: 800,
                                }}
                            >
                                {eyebrow}
                            </Typography>
                        )}
                        {title && (
                            <Typography variant="h5" sx={{ mt: eyebrow ? -0.35 : 0 }}>
                                {title}
                            </Typography>
                        )}
                        {description && (
                            <Typography
                                variant="body2"
                                sx={{ color: 'text.secondary', mt: 0.85, maxWidth: 740 }}
                            >
                                {description}
                            </Typography>
                        )}
                    </Box>
                    {action}
                </Stack>
            )}
            {children && <Box sx={contentSx}>{children}</Box>}
        </Paper>
    );
}
