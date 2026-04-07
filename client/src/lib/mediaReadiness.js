import {
    ensurePlaybackAudioSession,
    primeQuestionAudioPlayback,
    setSharedPlaybackAudioSource,
} from '@/lib/questionAudio';

function writeAscii(view, offset, text) {
    for (let i = 0; i < text.length; i += 1) {
        view.setUint8(offset + i, text.charCodeAt(i));
    }
}

function createSoundCheckToneBlob() {
    const sampleRate = 24000;
    const durationSeconds = 0.42;
    const totalSamples = Math.floor(sampleRate * durationSeconds);
    const buffer = new ArrayBuffer(44 + (totalSamples * 2));
    const view = new DataView(buffer);

    writeAscii(view, 0, 'RIFF');
    view.setUint32(4, 36 + (totalSamples * 2), true);
    writeAscii(view, 8, 'WAVE');
    writeAscii(view, 12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeAscii(view, 36, 'data');
    view.setUint32(40, totalSamples * 2, true);

    for (let i = 0; i < totalSamples; i += 1) {
        const progress = i / Math.max(1, totalSamples - 1);
        const fadeIn = Math.min(1, progress / 0.06);
        const fadeOut = Math.min(1, (1 - progress) / 0.18);
        const envelope = Math.min(fadeIn, fadeOut);
        const sample = Math.sin((2 * Math.PI * 880 * i) / sampleRate) * 0.35 * envelope;
        view.setInt16(44 + (i * 2), Math.max(-1, Math.min(1, sample)) * 0x7fff, true);
    }

    return new Blob([buffer], { type: 'audio/wav' });
}

async function playHtmlAudioTone() {
    const audio = setSharedPlaybackAudioSource(createSoundCheckToneBlob());
    if (!audio) {
        throw new Error('Audio playback is not available in this environment.');
    }

    await audio.play();
    await new Promise((resolve) => {
        audio.addEventListener('ended', resolve, { once: true });
        setTimeout(resolve, 600);
    });
}

function isAppleMobileDevice() {
    if (typeof navigator === 'undefined') return false;

    const userAgent = navigator.userAgent || '';
    const platform = navigator.platform || '';
    return /iPhone|iPad|iPod/i.test(userAgent) || (platform === 'MacIntel' && navigator.maxTouchPoints > 1);
}

export function getNoSoundHelpText() {
    if (isAppleMobileDevice()) {
        return 'If you did not hear the tone, turn off Silent Mode on the iPhone, raise media volume, and try again.';
    }
    return 'If you did not hear the tone, raise the volume and try again.';
}

export async function getMicrophonePermissionState() {
    if (typeof navigator === 'undefined') return 'unsupported';
    if (!navigator.mediaDevices?.getUserMedia) return 'unsupported';

    if (!navigator.permissions?.query) {
        return 'unknown';
    }

    try {
        const result = await navigator.permissions.query({ name: 'microphone' });
        return result?.state || 'unknown';
    } catch {
        return 'unknown';
    }
}

let _lastMicCheckStream = null;

export function releaseMicCheckStream() {
    if (_lastMicCheckStream) {
        _lastMicCheckStream.getTracks().forEach((t) => t.stop());
        _lastMicCheckStream = null;
    }
}

export async function requestMicrophoneAccess() {
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
        return { ok: false, state: 'unsupported', error: 'Microphone access is not supported in this browser.' };
    }

    const hadStream = !!_lastMicCheckStream;
    releaseMicCheckStream();
    if (hadStream && isAppleMobileDevice()) {
        await new Promise((r) => setTimeout(r, 300));
    }

    const attempts = isAppleMobileDevice()
        ? [{ audio: true }]
        : [
            {
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                    channelCount: 1,
                },
            },
            {
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                },
            },
            { audio: true },
        ];

    let lastError = null;

    for (const constraints of attempts) {
        try {
            const stream = await navigator.mediaDevices.getUserMedia(constraints);
            _lastMicCheckStream = stream;
            return { ok: true, state: 'granted' };
        } catch (error) {
            lastError = error;
            const fatal = error?.name === 'NotAllowedError'
                || error?.name === 'SecurityError'
                || error?.name === 'AbortError';
            if (fatal) {
                break;
            }
        }
    }

    const denied = lastError?.name === 'NotAllowedError' || lastError?.name === 'SecurityError';
    return {
        ok: false,
        state: denied ? 'denied' : 'error',
        error: denied
            ? 'Microphone access was blocked. Allow microphone access for this site, then tap Check Mic again.'
            : isAppleMobileDevice()
                ? 'Could not access the microphone on this iPhone. Tap Check Mic again and allow Safari microphone access if prompted.'
                : 'Could not access the microphone. Tap Check Mic again or check the selected input device.',
    };
}

export async function playSoundCheckTone() {
    if (typeof window === 'undefined') {
        return { ok: false, error: 'Audio playback is not available in this environment.' };
    }

    try {
        ensurePlaybackAudioSession('playback');
        await playHtmlAudioTone();
        await primeQuestionAudioPlayback();
        return { ok: true };
    } catch (error) {
        console.warn('HTML audio sound check failed, falling back to Web Audio:', error);
    }

    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) {
        return { ok: false, error: 'Audio playback is not supported in this browser.' };
    }

    try {
        let audioContext = await primeQuestionAudioPlayback();
        if (!audioContext || audioContext.state === 'closed') {
            audioContext = new AudioCtx();
            window.__beePreparedQuestionAudioContext = audioContext;
        }
        if (audioContext.state === 'suspended') {
            await audioContext.resume();
        }

        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();
        oscillator.type = 'sine';
        oscillator.frequency.value = 880;
        gainNode.gain.setValueAtTime(0.0001, audioContext.currentTime);
        gainNode.gain.exponentialRampToValueAtTime(0.12, audioContext.currentTime + 0.02);
        gainNode.gain.exponentialRampToValueAtTime(0.0001, audioContext.currentTime + 0.4);
        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);
        oscillator.start(audioContext.currentTime);
        oscillator.stop(audioContext.currentTime + 0.42);

        return { ok: true };
    } catch (error) {
        return {
            ok: false,
            error: getNoSoundHelpText(),
        };
    }
}
