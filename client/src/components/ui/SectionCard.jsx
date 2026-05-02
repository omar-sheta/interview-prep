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
                p: { xs: 2.25, md: 3 },
                borderRadius: 4,
                overflow: 'hidden',
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
                                    color: 'text.secondary',
                                    letterSpacing: '0.14em',
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
                                sx={{ color: 'text.secondary', mt: 0.7, maxWidth: 720 }}
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
