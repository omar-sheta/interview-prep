import { useEffect, useMemo, useState } from 'react';
import {
    ThemeProvider,
    CssBaseline,
    Box,
    Container,
    Paper,
    Stack,
    Typography,
    Button,
    Divider,
    Alert,
    FormControl,
    InputLabel,
    Select,
    MenuItem,
    TextField,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
} from '@mui/material';
import { Save, RestartAlt, DeleteForever } from '@mui/icons-material';
import useInterviewStore from '@/store/useInterviewStore';
import { createHiveTheme } from '@/theme/hiveTheme';
import HiveTopNav from '@/components/ui/HiveTopNav';

const DEFAULT_RECORDING_THRESHOLDS = {
    silence_auto_stop_seconds: 5.0,
    silence_rms_threshold: 0.008,
};

function clampNumber(value, min, max, fallback) {
    const n = Number(value);
    if (!Number.isFinite(n)) return fallback;
    return Math.max(min, Math.min(max, n));
}

function normalizeRecordingThresholds(input) {
    const src = (input && typeof input === 'object') ? input : {};
    return {
        silence_auto_stop_seconds: clampNumber(
            src.silence_auto_stop_seconds,
            1, 20,
            DEFAULT_RECORDING_THRESHOLDS.silence_auto_stop_seconds
        ),
        silence_rms_threshold: clampNumber(
            src.silence_rms_threshold,
            0.001, 0.05,
            DEFAULT_RECORDING_THRESHOLDS.silence_rms_threshold
        ),
    };
}

export default function SettingsView() {
    const {
        darkMode,
        isConnected,
        loadPreferences,
        savePreferences,
        resetAllData,
        recordingThresholds,
        piperStyle,
        ttsProvider,
        setPiperStyle,
        setTtsProvider,
    } = useInterviewStore();

    const theme = useMemo(() => createHiveTheme(darkMode ? 'dark' : 'light'), [darkMode]);
    const [recordingDraft, setRecordingDraft] = useState(normalizeRecordingThresholds(recordingThresholds));
    const [voiceStyleDraft, setVoiceStyleDraft] = useState('interviewer');
    const [ttsProviderDraft, setTtsProviderDraft] = useState('piper');
    const [status, setStatus] = useState('');
    const [statusSeverity, setStatusSeverity] = useState('success');
    const [resetDialogOpen, setResetDialogOpen] = useState(false);

    useEffect(() => {
        if (isConnected) loadPreferences();
    }, [isConnected, loadPreferences]);

    useEffect(() => {
        setRecordingDraft(normalizeRecordingThresholds(recordingThresholds));
    }, [recordingThresholds]);

    useEffect(() => {
        const next = String(piperStyle || 'interviewer').trim().toLowerCase();
        const allowed = new Set(['interviewer', 'balanced', 'fast']);
        setVoiceStyleDraft(allowed.has(next) ? next : 'interviewer');
    }, [piperStyle]);

    useEffect(() => {
        const next = String(ttsProvider || 'piper').trim().toLowerCase();
        const allowed = new Set(['piper', 'qwen3_tts_mlx']);
        setTtsProviderDraft(allowed.has(next) ? next : 'piper');
    }, [ttsProvider]);

    const save = () => {
        const normalizedRecording = normalizeRecordingThresholds(recordingDraft);
        setRecordingDraft(normalizedRecording);
        savePreferences({
            recording_thresholds: normalizedRecording,
            piper_style: voiceStyleDraft,
            tts_provider: ttsProviderDraft,
        });
        setPiperStyle(voiceStyleDraft);
        setTtsProvider(ttsProviderDraft);
        setStatusSeverity('success');
        setStatus('Settings saved.');
        setTimeout(() => setStatus(''), 2500);
    };

    const resetDefaults = () => {
        const recordingDefaults = normalizeRecordingThresholds(DEFAULT_RECORDING_THRESHOLDS);
        const voiceDefault = 'interviewer';
        const ttsDefault = 'piper';
        setRecordingDraft(recordingDefaults);
        setVoiceStyleDraft(voiceDefault);
        setTtsProviderDraft(ttsDefault);
        savePreferences({
            recording_thresholds: recordingDefaults,
            piper_style: voiceDefault,
            tts_provider: ttsDefault,
        });
        setPiperStyle(voiceDefault);
        setTtsProvider(ttsDefault);
        setStatusSeverity('success');
        setStatus('Reset to default settings.');
        setTimeout(() => setStatus(''), 2500);
    };

    const resetWorkspace = () => {
        const started = resetAllData();
        if (!started) {
            setStatusSeverity('error');
            setStatus('Not connected. Reconnect and try again.');
            setTimeout(() => setStatus(''), 3000);
            return;
        }

        setStatusSeverity('success');
        setStatus('Reset requested. Your history and configuration are being cleared.');
        setTimeout(() => setStatus(''), 3000);
    };

    return (
        <ThemeProvider theme={theme}>
            <CssBaseline />
            <Box sx={{ minHeight: '100vh', bgcolor: 'background.default', pb: { xs: 3, md: 5 } }}>
                <HiveTopNav active="settings" />
                <Container maxWidth="lg" sx={{ pt: { xs: 2.5, md: 4 } }}>
                    <Paper sx={{ p: { xs: 2, md: 2.5 }, mb: 2.2 }}>
                        <Typography variant="h4">Settings</Typography>
                        <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                            Configure voice synthesis and recording behavior.
                        </Typography>
                    </Paper>

                    <Paper sx={{ p: { xs: 2, md: 2.5 } }}>
                        <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ xs: 'flex-start', sm: 'center' }} spacing={1.2} sx={{ mb: 1.2 }}>
                            <Typography variant="h6">Voice &amp; Recording</Typography>
                            <Stack direction="row" spacing={1}>
                                <Button variant="outlined" startIcon={<RestartAlt />} onClick={resetDefaults}>
                                    Reset Defaults
                                </Button>
                                <Button variant="contained" startIcon={<Save />} onClick={save}>
                                    Save
                                </Button>
                            </Stack>
                        </Stack>
                        <Divider sx={{ mb: 1.8 }} />

                        <Typography variant="subtitle2" sx={{ mb: 1 }}>Question Voice Style</Typography>
                        <Box sx={{ maxWidth: 420, mb: 1.2 }}>
                            <FormControl fullWidth size="small">
                                <InputLabel id="tts-provider-label">Voice Engine</InputLabel>
                                <Select
                                    labelId="tts-provider-label"
                                    label="Voice Engine"
                                    value={ttsProviderDraft}
                                    onChange={(event) => setTtsProviderDraft(String(event.target.value || 'piper'))}
                                >
                                    <MenuItem value="piper">Piper (fast + lightweight)</MenuItem>
                                    <MenuItem value="qwen3_tts_mlx">Qwen3-TTS MLX (higher quality)</MenuItem>
                                </Select>
                            </FormControl>
                        </Box>

                        <Typography variant="subtitle2" sx={{ mb: 1 }}>Piper Voice Style</Typography>
                        <Box sx={{ maxWidth: 420, mb: 2.5 }}>
                            <FormControl fullWidth size="small">
                                <InputLabel id="piper-style-label">Voice Style</InputLabel>
                                <Select
                                    labelId="piper-style-label"
                                    label="Voice Style"
                                    value={voiceStyleDraft}
                                    onChange={(event) => setVoiceStyleDraft(String(event.target.value || 'interviewer'))}
                                    disabled={ttsProviderDraft !== 'piper'}
                                >
                                    <MenuItem value="interviewer">Interviewer (clear + polished)</MenuItem>
                                    <MenuItem value="balanced">Balanced (default cadence)</MenuItem>
                                    <MenuItem value="fast">Fast (lower latency)</MenuItem>
                                </Select>
                            </FormControl>
                            {ttsProviderDraft !== 'piper' && (
                                <Typography variant="caption" sx={{ color: 'text.secondary', mt: 0.6, display: 'block' }}>
                                    Piper style presets apply only when Voice Engine is set to Piper.
                                </Typography>
                            )}
                        </Box>

                        <Typography variant="subtitle2" sx={{ mb: 1 }}>Recording</Typography>
                        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 1.2 }}>
                            <TextField
                                label="Auto-stop silence duration (seconds)"
                                value={recordingDraft.silence_auto_stop_seconds ?? ''}
                                onChange={(e) => setRecordingDraft((prev) => ({ ...prev, silence_auto_stop_seconds: e.target.value }))}
                                type="number"
                                inputProps={{ min: 1, max: 20, step: 0.5 }}
                                size="small"
                                fullWidth
                                helperText="Recording stops automatically after this many seconds of silence."
                            />
                            <TextField
                                label="Silence RMS threshold"
                                value={recordingDraft.silence_rms_threshold ?? ''}
                                onChange={(e) => setRecordingDraft((prev) => ({ ...prev, silence_rms_threshold: e.target.value }))}
                                type="number"
                                inputProps={{ min: 0.001, max: 0.05, step: 0.001 }}
                                size="small"
                                fullWidth
                                helperText="Lower = more sensitive to quiet speech. Increase if recording stops too early."
                            />
                        </Box>

                        {status && (
                            <Alert severity={statusSeverity} sx={{ mt: 1.5 }}>
                                {status}
                            </Alert>
                        )}
                    </Paper>

                    <Paper
                        sx={{
                            p: { xs: 2, md: 2.5 },
                            mt: 2.2,
                            border: '1px solid',
                            borderColor: 'error.light',
                        }}
                    >
                        <Stack
                            direction={{ xs: 'column', sm: 'row' }}
                            spacing={1.2}
                            justifyContent="space-between"
                            alignItems={{ xs: 'flex-start', sm: 'center' }}
                        >
                            <Box>
                                <Typography variant="h6" color="error.main">Danger Zone</Typography>
                                <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                    Delete interview history and clear saved configuration/analysis workspace.
                                </Typography>
                            </Box>
                            <Button
                                variant="outlined"
                                color="error"
                                startIcon={<DeleteForever />}
                                onClick={() => setResetDialogOpen(true)}
                            >
                                Reset All Data
                            </Button>
                        </Stack>
                    </Paper>
                </Container>

                <Dialog open={resetDialogOpen} onClose={() => setResetDialogOpen(false)} maxWidth="xs" fullWidth>
                    <DialogTitle>Reset All Data?</DialogTitle>
                    <DialogContent>
                        <Typography variant="body2">
                            This will permanently delete interview history and clear saved configuration and analysis data.
                        </Typography>
                    </DialogContent>
                    <DialogActions>
                        <Button onClick={() => setResetDialogOpen(false)}>Cancel</Button>
                        <Button
                            color="error"
                            variant="contained"
                            onClick={() => {
                                setResetDialogOpen(false);
                                resetWorkspace();
                            }}
                        >
                            Reset All Data
                        </Button>
                    </DialogActions>
                </Dialog>
            </Box>
        </ThemeProvider>
    );
}
