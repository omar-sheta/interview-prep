import { useEffect, useState } from 'react';
import {
    Box,
    Button,
    Chip,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    Divider,
    IconButton,
    Paper,
    Stack,
    Typography,
} from '@mui/material';
import { Close, Mic, VolumeUp } from '@mui/icons-material';
import {
    getNoSoundHelpText,
    getMicrophonePermissionState,
    playSoundCheckTone,
    releaseMicCheckStream,
    requestMicrophoneAccess,
} from '@/lib/mediaReadiness';

export default function InterviewReadinessDialog({
    open,
    onClose,
    onConfirm,
    confirming = false,
    micPermissionGranted = false,
    onMicPermissionChange,
    title = 'Before You Start',
    subtitle = 'Check microphone access and confirm sound before the interview begins.',
    summary = '',
    actionLabel = 'Start Interview',
}) {
    const [micStatus, setMicStatus] = useState(micPermissionGranted ? 'granted' : 'unknown');
    const [audioStatus, setAudioStatus] = useState('unknown');
    const [message, setMessage] = useState('');

    useEffect(() => {
        if (!open) return undefined;

        let active = true;
        setAudioStatus('unknown');
        setMessage('');

        (async () => {
            const permissionState = await getMicrophonePermissionState();
            if (!active) return;

            if (permissionState === 'granted') {
                setMicStatus('granted');
                return;
            }
            if (permissionState === 'denied') {
                setMicStatus('denied');
                return;
            }
            // Permissions API unavailable (e.g. iOS Safari) — cached flag is
            // unreliable because iOS resets mic permission each page load.
            // Always require a real check so the user taps Allow in Safari.
            setMicStatus('prompt');
        })();

        return () => {
            active = false;
            releaseMicCheckStream();
        };
    }, [open]);

    const handleMicCheck = async () => {
        setMessage('');
        setMicStatus('checking');
        const result = await requestMicrophoneAccess();
        if (result.ok) {
            setMicStatus('granted');
            onMicPermissionChange?.(true);
            setMessage('Microphone ready.');
            return;
        }

        const nextStatus = result.state === 'denied' ? 'denied' : 'error';
        setMicStatus(nextStatus);
        onMicPermissionChange?.(false);
        setMessage(result.error || 'Microphone check failed.');
    };

    const handleSoundTest = async () => {
        setMessage('');
        const result = await playSoundCheckTone();
        if (result.ok) {
            setAudioStatus('played');
            setMessage('Did you hear the tone?');
            return;
        }

        setAudioStatus('failed');
        setMessage(result.error || 'Sound test failed.');
    };

    const confirmSound = (heard) => {
        if (heard) {
            setAudioStatus('confirmed');
            setMessage('Sound confirmed.');
            return;
        }

        setAudioStatus('warning');
        setMessage(getNoSoundHelpText());
    };

    const canConfirm = micStatus === 'granted' && audioStatus === 'confirmed' && !confirming;

    return (
        <Dialog open={open} onClose={() => !confirming && onClose?.()} maxWidth="sm" fullWidth>
            <DialogTitle>
                <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
                    <Box>
                        <Typography variant="h6" sx={{ fontWeight: 700 }}>
                            {title}
                        </Typography>
                        <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.3 }}>
                            {subtitle}
                        </Typography>
                    </Box>
                    <IconButton size="small" onClick={() => onClose?.()} disabled={confirming}>
                        <Close fontSize="small" />
                    </IconButton>
                </Stack>
            </DialogTitle>
            <Divider />
            <DialogContent>
                <Stack spacing={2.2} sx={{ pt: 1 }}>
                    {summary ? (
                        <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                            {summary}
                        </Typography>
                    ) : null}
                    <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
                        <Stack spacing={1.3}>
                            <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                                Device Check
                            </Typography>
                            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} useFlexGap flexWrap="wrap" alignItems={{ sm: 'center' }}>
                                <Chip
                                    label={
                                        micStatus === 'granted'
                                            ? 'Mic ready'
                                            : micStatus === 'checking'
                                                ? 'Checking mic...'
                                                : micStatus === 'denied'
                                                    ? 'Mic blocked'
                                                    : 'Mic unchecked'
                                    }
                                    color={
                                        micStatus === 'granted'
                                            ? 'success'
                                            : micStatus === 'denied'
                                                ? 'error'
                                                : 'warning'
                                    }
                                    variant="outlined"
                                />
                                <Button
                                    size="small"
                                    variant="outlined"
                                    startIcon={<Mic />}
                                    onClick={handleMicCheck}
                                    disabled={micStatus === 'checking' || confirming}
                                >
                                    {micStatus === 'granted' ? 'Recheck Mic' : micStatus === 'checking' ? 'Checking Mic...' : 'Check Mic'}
                                </Button>
                                <Chip
                                    label={
                                        audioStatus === 'confirmed'
                                            ? 'Sound ready'
                                            : audioStatus === 'played'
                                                ? 'Confirm sound'
                                                : audioStatus === 'warning' || audioStatus === 'failed'
                                                    ? 'Sound needs attention'
                                                    : 'Sound unchecked'
                                    }
                                    color={
                                        audioStatus === 'confirmed'
                                            ? 'success'
                                            : audioStatus === 'warning' || audioStatus === 'failed'
                                                ? 'warning'
                                                : 'default'
                                    }
                                    variant="outlined"
                                />
                                <Button
                                    size="small"
                                    variant="outlined"
                                    startIcon={<VolumeUp />}
                                    onClick={handleSoundTest}
                                    disabled={confirming}
                                >
                                    Test Sound
                                </Button>
                            </Stack>
                            {audioStatus === 'played' ? (
                                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                                    <Button size="small" variant="contained" onClick={() => confirmSound(true)} disabled={confirming}>
                                        I Heard It
                                    </Button>
                                    <Button size="small" variant="outlined" color="warning" onClick={() => confirmSound(false)} disabled={confirming}>
                                        No Sound
                                    </Button>
                                </Stack>
                            ) : null}
                            {message ? (
                                <Typography
                                    variant="caption"
                                    sx={{
                                        color:
                                            audioStatus === 'warning' ||
                                            micStatus === 'denied' ||
                                            audioStatus === 'failed'
                                                ? 'warning.main'
                                                : 'text.secondary',
                                    }}
                                >
                                    {message}
                                </Typography>
                            ) : null}
                        </Stack>
                    </Paper>
                </Stack>
            </DialogContent>
            <Divider />
            <DialogActions sx={{ px: 3, py: 2 }}>
                <Button onClick={() => onClose?.()} disabled={confirming}>
                    Cancel
                </Button>
                <Button variant="contained" onClick={() => onConfirm?.()} disabled={!canConfirm}>
                    {confirming ? 'Starting...' : actionLabel}
                </Button>
            </DialogActions>
        </Dialog>
    );
}
