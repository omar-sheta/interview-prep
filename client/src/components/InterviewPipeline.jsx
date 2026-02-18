import React from 'react';
import { Box, Typography, Button, Chip, Stack, Card, Avatar } from '@mui/material';
import { PlayArrow, CheckCircle, AccessTime, AutoAwesome } from '@mui/icons-material';

const StatusIcon = ({ status, index }) => {
    const isCompleted = status === 'completed';
    const isActive = status === 'active';
    return (
        <Box sx={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
            <Avatar
                sx={{
                    width: 36, height: 36,
                    bgcolor: isCompleted ? 'success.main' : (isActive ? '#F97316' : '#2A2A2A'),
                    border: '3px solid', borderColor: '#1A1A1A',
                    color: isCompleted || isActive ? 'white' : '#A3A3A3',
                    fontWeight: 'bold', boxShadow: isActive ? '0 0 0 4px rgba(249, 115, 22, 0.15)' : 'none',
                    zIndex: 2
                }}
            >
                {isCompleted ? <CheckCircle fontSize="small" /> : index + 1}
            </Avatar>
            <Box sx={{
                width: 2, height: '100%', bgcolor: isCompleted ? 'success.light' : 'rgba(249, 115, 22, 0.2)',
                position: 'absolute', top: 36, bottom: -20, zIndex: 0,
                display: index === 2 ? 'none' : 'block'
            }} />
        </Box>
    );
};

const InterviewPipeline = ({ plan, onStartSession, onCustomize }) => {
    if (!plan || !plan.rounds) return null;

    return (
        <Box sx={{ p: 2 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 4 }}>
                <Box>
                    <Typography variant="h5" fontWeight="800" gutterBottom>{plan.goal}</Typography>
                    <Stack direction="row" spacing={1}>
                        <Chip label="Mission Active" color="success" size="small" variant="outlined" />
                    </Stack>
                </Box>
                <Button size="small" startIcon={<AutoAwesome />} onClick={onCustomize}>Adjust Plan</Button>
            </Box>

            <Box sx={{ pl: 1 }}>
                {plan.rounds.map((round, index) => (
                    <Box key={round.id} sx={{ display: 'flex', mb: 5 }}>
                        <Box sx={{ mr: 3 }}><StatusIcon status={round.status} index={index} /></Box>
                        <Box sx={{ flexGrow: 1, pt: 0.5 }}>
                            <Typography variant="subtitle1" fontWeight="bold" color={round.status === 'upcoming' ? 'text.secondary' : 'text.primary'}>
                                {round.name}
                            </Typography>
                            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>{round.description}</Typography>
                            <Stack spacing={2}>
                                {round.sessions.map((session) => (
                                    <Card key={session.id} elevation={0} sx={{
                                        p: 2, border: '1px solid', borderColor: session.status === 'completed' ? 'success.light' : 'rgba(249, 115, 22, 0.15)',
                                        bgcolor: session.status === 'completed' ? 'rgba(34, 197, 94, 0.1)' : '#1A1A1A',
                                        '&:hover': { borderColor: '#F97316', transform: 'translateX(4px)' }, transition: '0.2s'
                                    }}>
                                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                            <Box>
                                                <Typography variant="subtitle2" fontWeight="700">{session.title}</Typography>
                                                <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
                                                    <Chip label={session.type.toUpperCase()} size="small" sx={{ height: 20, fontSize: '0.65rem' }} />
                                                    <Typography variant="caption" sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                                        <AccessTime sx={{ fontSize: 12 }} /> {session.duration || '20m'}
                                                    </Typography>
                                                </Stack>
                                            </Box>
                                            <Button
                                                variant={session.status === 'completed' ? "text" : "contained"}
                                                color={session.status === 'completed' ? "success" : "primary"}
                                                size="small" onClick={() => onStartSession(session)}
                                                startIcon={session.status === 'completed' ? <CheckCircle /> : <PlayArrow />}
                                                disableElevation
                                            >
                                                {session.status === 'completed' ? "Review" : "Start"}
                                            </Button>
                                        </Box>
                                    </Card>
                                ))}
                            </Stack>
                        </Box>
                    </Box>
                ))}
            </Box>
        </Box>
    );
};
export default InterviewPipeline;
