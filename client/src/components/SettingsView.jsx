import { useEffect, useMemo, useState } from 'react';
import {
    ThemeProvider,
    CssBaseline,
    Box,
    Container,
    Paper,
    Stack,
    Typography,
    TextField,
    Button,
    Divider,
    Alert,
    FormControl,
    InputLabel,
    Select,
    MenuItem,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
} from '@mui/material';
import { Save, RestartAlt, DeleteForever } from '@mui/icons-material';
import useInterviewStore from '@/store/useInterviewStore';
import { createHiveTheme } from '@/theme/hiveTheme';
import HiveTopNav from '@/components/ui/HiveTopNav';

const DEFAULT_THRESHOLDS = {
    low_relevance_threshold: 0.12,
    repetition_ratio_cap: 0.42,
    unique_word_ratio_min: 0.4,
    coverage_min: 0.4,
    structure_markers_min: 2,
    structure_sentence_cap: 2,
    gibberish_ratio_threshold: 0.28,
    low_transcript_penalty: 1.0,
    low_transcript_confidence_cap: 0.45,
    accuracy_cap_low_relevance: 3,
    clarity_cap_repetition: 3,
    completeness_cap_low_coverage: 4,
    structure_cap_weak: 4,
};

const DEFAULT_RECORDING_THRESHOLDS = {
    silence_auto_stop_seconds: 5.0,
    silence_rms_threshold: 0.008,
};

const FIELD_META = [
    { key: 'low_relevance_threshold', label: 'Low relevance threshold (0-1)', type: 'float', min: 0.01, max: 0.9 },
    { key: 'repetition_ratio_cap', label: 'Repetition cap threshold (0-1)', type: 'float', min: 0.1, max: 0.95 },
    { key: 'unique_word_ratio_min', label: 'Min lexical diversity (0-1)', type: 'float', min: 0.1, max: 0.95 },
    { key: 'coverage_min', label: 'Min rubric coverage (0-1)', type: 'float', min: 0.05, max: 0.95 },
    { key: 'structure_markers_min', label: 'Min structure markers', type: 'int', min: 0, max: 8 },
    { key: 'structure_sentence_cap', label: 'Weak structure sentence cap', type: 'int', min: 1, max: 8 },
    { key: 'gibberish_ratio_threshold', label: 'Gibberish threshold (0-1)', type: 'float', min: 0.05, max: 0.95 },
    { key: 'low_transcript_penalty', label: 'Low transcript score penalty', type: 'float', min: 0, max: 4 },
    { key: 'low_transcript_confidence_cap', label: 'Low transcript confidence cap', type: 'float', min: 0.1, max: 0.95 },
    { key: 'accuracy_cap_low_relevance', label: 'Accuracy cap (low relevance)', type: 'float', min: 0, max: 10 },
    { key: 'clarity_cap_repetition', label: 'Clarity cap (repetition)', type: 'float', min: 0, max: 10 },
    { key: 'completeness_cap_low_coverage', label: 'Completeness cap (low coverage)', type: 'float', min: 0, max: 10 },
    { key: 'structure_cap_weak', label: 'Structure cap (weak flow)', type: 'float', min: 0, max: 10 },
];

const RECORDING_FIELD_META = [
    { key: 'silence_auto_stop_seconds', label: 'Auto-stop silence duration (seconds)', type: 'float', min: 1, max: 20 },
    { key: 'silence_rms_threshold', label: 'Silence RMS threshold', type: 'float', min: 0.001, max: 0.05 },
];

function clampNumber(value, min, max, fallback) {
    const n = Number(value);
    if (!Number.isFinite(n)) return fallback;
    return Math.max(min, Math.min(max, n));
}

function normalizeThresholds(input) {
    const src = (input && typeof input === 'object') ? input : {};
    const merged = { ...DEFAULT_THRESHOLDS, ...src };
    const normalized = {};
    for (const field of FIELD_META) {
        const fallback = DEFAULT_THRESHOLDS[field.key];
        const raw = merged[field.key];
        const clamped = clampNumber(raw, field.min, field.max, fallback);
        normalized[field.key] = field.type === 'int' ? Math.round(clamped) : Number(clamped.toFixed(3));
    }
    return normalized;
}

function normalizeRecordingThresholds(input) {
    const src = (input && typeof input === 'object') ? input : {};
    const merged = { ...DEFAULT_RECORDING_THRESHOLDS, ...src };
    const normalized = {};
    for (const field of RECORDING_FIELD_META) {
        const fallback = DEFAULT_RECORDING_THRESHOLDS[field.key];
        const raw = merged[field.key];
        const clamped = clampNumber(raw, field.min, field.max, fallback);
        normalized[field.key] = Number(clamped.toFixed(3));
    }
    return normalized;
}

export default function SettingsView() {
    const {
        darkMode,
        isConnected,
        loadPreferences,
        savePreferences,
        resetAllData,
        evaluationThresholds,
        recordingThresholds,
        piperStyle,
        setPiperStyle,
    } = useInterviewStore();

    const theme = useMemo(() => createHiveTheme(darkMode ? 'dark' : 'light'), [darkMode]);
    const [strictnessDraft, setStrictnessDraft] = useState(normalizeThresholds(evaluationThresholds));
    const [recordingDraft, setRecordingDraft] = useState(normalizeRecordingThresholds(recordingThresholds));
    const [voiceStyleDraft, setVoiceStyleDraft] = useState('interviewer');
    const [status, setStatus] = useState('');
    const [statusSeverity, setStatusSeverity] = useState('success');
    const [resetDialogOpen, setResetDialogOpen] = useState(false);

    useEffect(() => {
        if (isConnected) loadPreferences();
    }, [isConnected, loadPreferences]);

    useEffect(() => {
        setStrictnessDraft(normalizeThresholds(evaluationThresholds));
    }, [evaluationThresholds]);

    useEffect(() => {
        setRecordingDraft(normalizeRecordingThresholds(recordingThresholds));
    }, [recordingThresholds]);

    useEffect(() => {
        const next = String(piperStyle || 'interviewer').trim().toLowerCase();
        const allowed = new Set(['interviewer', 'balanced', 'fast']);
        setVoiceStyleDraft(allowed.has(next) ? next : 'interviewer');
    }, [piperStyle]);

    const onStrictnessFieldChange = (key, value) => {
        setStrictnessDraft((prev) => ({ ...prev, [key]: value }));
    };

    const onRecordingFieldChange = (key, value) => {
        setRecordingDraft((prev) => ({ ...prev, [key]: value }));
    };

    const save = () => {
        const normalizedStrictness = normalizeThresholds(strictnessDraft);
        const normalizedRecording = normalizeRecordingThresholds(recordingDraft);
        setStrictnessDraft(normalizedStrictness);
        setRecordingDraft(normalizedRecording);
        savePreferences({
            evaluation_thresholds: normalizedStrictness,
            recording_thresholds: normalizedRecording,
            piper_style: voiceStyleDraft,
        });
        setPiperStyle(voiceStyleDraft);
        setStatusSeverity('success');
        setStatus('Saved settings. New evaluations and recording sessions will use these values.');
        setTimeout(() => setStatus(''), 2500);
    };

    const resetDefaults = () => {
        const strictDefaults = normalizeThresholds(DEFAULT_THRESHOLDS);
        const recordingDefaults = normalizeRecordingThresholds(DEFAULT_RECORDING_THRESHOLDS);
        const voiceDefault = 'interviewer';
        setStrictnessDraft(strictDefaults);
        setRecordingDraft(recordingDefaults);
        setVoiceStyleDraft(voiceDefault);
        savePreferences({
            evaluation_thresholds: strictDefaults,
            recording_thresholds: recordingDefaults,
            piper_style: voiceDefault,
        });
        setPiperStyle(voiceDefault);
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
                            Tune scoring strictness thresholds used by evaluation and retry scoring.
                        </Typography>
                    </Paper>

                    <Paper sx={{ p: { xs: 2, md: 2.5 } }}>
                        <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ xs: 'flex-start', sm: 'center' }} spacing={1.2} sx={{ mb: 1.2 }}>
                            <Typography variant="h6">Feedback Strictness</Typography>
                            <Stack direction="row" spacing={1}>
                                <Button variant="outlined" startIcon={<RestartAlt />} onClick={resetDefaults}>
                                    Reset Defaults
                                </Button>
                                <Button variant="contained" startIcon={<Save />} onClick={save}>
                                    Save
                                </Button>
                            </Stack>
                        </Stack>
                        <Divider sx={{ mb: 1.2 }} />

                        <Typography variant="h6" sx={{ mb: 1.2 }}>Voice Synthesis</Typography>
                        <Box sx={{ maxWidth: 360, mb: 1.8 }}>
                            <FormControl fullWidth size="small">
                                <InputLabel id="piper-style-label">Question Voice Style</InputLabel>
                                <Select
                                    labelId="piper-style-label"
                                    label="Question Voice Style"
                                    value={voiceStyleDraft}
                                    onChange={(event) => setVoiceStyleDraft(String(event.target.value || 'interviewer'))}
                                >
                                    <MenuItem value="interviewer">Interviewer (clear + polished)</MenuItem>
                                    <MenuItem value="balanced">Balanced (default cadence)</MenuItem>
                                    <MenuItem value="fast">Fast (lower latency)</MenuItem>
                                </Select>
                            </FormControl>
                        </Box>

                        <Divider sx={{ mb: 1.2 }} />

                        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 1.2 }}>
                            {FIELD_META.map((field) => (
                                <TextField
                                    key={field.key}
                                    label={field.label}
                                    value={strictnessDraft[field.key] ?? ''}
                                    onChange={(event) => onStrictnessFieldChange(field.key, event.target.value)}
                                    type="number"
                                    inputProps={{ min: field.min, max: field.max, step: field.type === 'int' ? 1 : 0.01 }}
                                    size="small"
                                    fullWidth
                                />
                            ))}
                        </Box>

                        <Divider sx={{ my: 1.8 }} />
                        <Typography variant="h6" sx={{ mb: 1.2 }}>Recording</Typography>
                        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 1.2 }}>
                            {RECORDING_FIELD_META.map((field) => (
                                <TextField
                                    key={field.key}
                                    label={field.label}
                                    value={recordingDraft[field.key] ?? ''}
                                    onChange={(event) => onRecordingFieldChange(field.key, event.target.value)}
                                    type="number"
                                    inputProps={{ min: field.min, max: field.max, step: 0.001 }}
                                    size="small"
                                    fullWidth
                                />
                            ))}
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
