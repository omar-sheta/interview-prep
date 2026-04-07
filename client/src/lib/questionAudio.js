export function ensurePlaybackAudioSession(type = 'playback') {
    if (typeof navigator === 'undefined') return false;

    const audioSession = navigator.audioSession;
    if (!audioSession) return false;

    try {
        if (audioSession.type !== type) {
            audioSession.type = type;
        }
        return true;
    } catch (error) {
        console.warn('AudioSession configuration failed:', error);
        return false;
    }
}

function configurePlaybackAudioElement(audio) {
    audio.preload = 'auto';
    audio.volume = 1;
    audio.muted = false;
    audio.playsInline = true;
    audio.setAttribute('playsinline', '');
    audio.setAttribute('webkit-playsinline', '');
    audio.setAttribute('x-webkit-airplay', 'deny');
    if ('disableRemotePlayback' in audio) {
        audio.disableRemotePlayback = true;
    }
    return audio;
}

function revokeSharedPlaybackObjectUrl() {
    if (typeof window === 'undefined') return;

    const previousUrl = window.__beePreparedSharedPlaybackObjectUrl;
    if (previousUrl) {
        URL.revokeObjectURL(previousUrl);
        window.__beePreparedSharedPlaybackObjectUrl = null;
    }
}

export function getSharedPlaybackAudioElement() {
    if (typeof window === 'undefined') return null;

    let audio = window.__beePreparedSharedPlaybackAudio;
    if (!audio) {
        audio = configurePlaybackAudioElement(new Audio());
        window.__beePreparedSharedPlaybackAudio = audio;
    } else {
        configurePlaybackAudioElement(audio);
    }
    return audio;
}

export function clearSharedPlaybackAudioSource() {
    const audio = getSharedPlaybackAudioElement();
    if (!audio) return null;

    audio.pause();
    audio.removeAttribute('src');
    audio.src = '';
    revokeSharedPlaybackObjectUrl();
    return audio;
}

export function setSharedPlaybackAudioSource(source) {
    const audio = clearSharedPlaybackAudioSource();
    if (!audio || !source) return audio;

    if (source instanceof Blob) {
        const objectUrl = URL.createObjectURL(source);
        window.__beePreparedSharedPlaybackObjectUrl = objectUrl;
        audio.src = objectUrl;
    } else {
        audio.src = String(source);
    }

    return audio;
}

export function wavBase64ToBlob(audioBase64) {
    if (typeof window === 'undefined' || typeof atob !== 'function') return null;
    if (!audioBase64) return null;

    const binary = atob(audioBase64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) {
        bytes[i] = binary.charCodeAt(i);
    }
    return new Blob([bytes], { type: 'audio/wav' });
}

export async function primeQuestionAudioPlayback() {
    if (typeof window === 'undefined') return null;

    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    let audioContext = null;

    try {
        await ensurePlaybackAudioSession('playback');

        if (AudioCtx) {
            audioContext = window.__beePreparedQuestionAudioContext;
            if (!audioContext || audioContext.state === 'closed') {
                audioContext = new AudioCtx();
                window.__beePreparedQuestionAudioContext = audioContext;
            }
            if (audioContext.state === 'suspended') {
                await audioContext.resume();
            }

            const buffer = audioContext.createBuffer(1, 1, 22050);
            const source = audioContext.createBufferSource();
            source.buffer = buffer;
            source.connect(audioContext.destination);
            source.start(0);
            source.disconnect();
        }
    } catch (error) {
        console.warn('AudioContext unlock failed:', error);
    }

    try {
        const unlockAudio = setSharedPlaybackAudioSource(
            'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA',
        );
        if (!unlockAudio) return audioContext;
        await unlockAudio.play().catch(() => { });
        unlockAudio.pause();
        clearSharedPlaybackAudioSource();
    } catch (error) {
        console.warn('HTMLAudio unlock failed:', error);
    }

    return audioContext;
}

export function getQuestionAudioContext() {
    if (typeof window === 'undefined') return null;
    return window.__beePreparedQuestionAudioContext || null;
}
