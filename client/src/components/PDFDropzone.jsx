import { useCallback, useMemo, useState } from 'react';
import {
    Alert,
    Box,
    Button,
    Stack,
    Typography,
    alpha,
} from '@mui/material';
import { CheckCircleOutline, UploadFileOutlined } from '@mui/icons-material';

export default function PDFDropzone({
    onUpload,
    isLoading = false,
    hasSavedResume = false,
    savedLabel = '',
}) {
    const [isDragging, setIsDragging] = useState(false);
    const [fileName, setFileName] = useState('');
    const [error, setError] = useState('');
    const currentLabel = fileName || savedLabel;
    const isReady = Boolean(currentLabel || hasSavedResume);
    const helperText = useMemo(() => {
        if (isLoading) return 'Reading your resume and updating the workspace...';
        if (isDragging) return 'Drop the PDF anywhere in this box.';
        if (isReady) return currentLabel || 'Resume saved to this workspace.';
        return 'Drag a PDF here, or browse from your computer.';
    }, [currentLabel, isDragging, isLoading, isReady]);

    const handleFile = useCallback(async (file) => {
        if (!file) return;
        if (file.type !== 'application/pdf') {
            setError('Please upload a PDF file.');
            return;
        }
        if (file.size > 10 * 1024 * 1024) {
            setError('File size must be less than 10MB.');
            return;
        }

        setError('');
        setFileName(file.name);
        const reader = new FileReader();
        reader.onload = () => {
            const base64 = String(reader.result || '').split(',')[1] || '';
            onUpload(base64, file.name);
        };
        reader.readAsDataURL(file);
    }, [onUpload]);

    const openFilePicker = useCallback(() => {
        if (isLoading) return;
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.pdf,application/pdf';
        input.onchange = (event) => handleFile(event.target.files?.[0]);
        input.click();
    }, [handleFile, isLoading]);

    const handleDrop = useCallback((event) => {
        event.preventDefault();
        setIsDragging(false);
        handleFile(event.dataTransfer.files?.[0]);
    }, [handleFile]);

    return (
        <Stack spacing={1.5}>
            <Box
                role="button"
                tabIndex={0}
                onClick={openFilePicker}
                onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        openFilePicker();
                    }
                }}
                onDrop={handleDrop}
                onDragOver={(event) => {
                    event.preventDefault();
                    setIsDragging(true);
                }}
                onDragLeave={(event) => {
                    event.preventDefault();
                    setIsDragging(false);
                }}
                sx={(theme) => {
                    const accent = isReady ? theme.palette.success.main : theme.palette.primary.main;
                    return {
                        minHeight: 190,
                        display: 'grid',
                        placeItems: 'center',
                        textAlign: 'center',
                        borderRadius: 3,
                        px: 3,
                        py: 3,
                        cursor: isLoading ? 'default' : 'pointer',
                        border: '1.5px dashed',
                        borderColor: isDragging ? accent : alpha(accent, isReady ? 0.42 : 0.28),
                        bgcolor: isDragging ? alpha(accent, 0.1) : alpha(accent, isReady ? 0.07 : 0.035),
                        transition: 'border-color 160ms ease, background-color 160ms ease, transform 160ms ease',
                        opacity: isLoading ? 0.72 : 1,
                        '&:hover': isLoading ? {} : {
                            borderColor: alpha(accent, 0.7),
                            bgcolor: alpha(accent, 0.08),
                            transform: 'translateY(-1px)',
                        },
                    };
                }}
            >
                <Stack spacing={1.2} alignItems="center" sx={{ maxWidth: 360 }}>
                    <Box
                        sx={(theme) => {
                            const accent = isReady ? theme.palette.success.main : theme.palette.primary.main;
                            return {
                                width: 58,
                                height: 58,
                                borderRadius: '50%',
                                display: 'grid',
                                placeItems: 'center',
                                color: accent,
                                bgcolor: alpha(accent, 0.12),
                                border: `1px solid ${alpha(accent, 0.24)}`,
                            };
                        }}
                    >
                        {isReady ? <CheckCircleOutline /> : <UploadFileOutlined />}
                    </Box>
                    <Box>
                        <Typography variant="subtitle1" sx={{ fontWeight: 800 }}>
                            {isReady ? 'Resume Ready' : 'Add Your Resume'}
                        </Typography>
                        <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.35 }}>
                            {helperText}
                        </Typography>
                    </Box>
                    <Button variant={isReady ? 'outlined' : 'contained'} size="small" disabled={isLoading}>
                        {isReady ? 'Replace PDF' : 'Browse PDF'}
                    </Button>
                </Stack>
            </Box>
            {error && <Alert severity="error">{error}</Alert>}
        </Stack>
    );
}
