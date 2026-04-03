export async function primeQuestionAudioPlayback() {
    if (typeof window === 'undefined') return null;

    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    let audioContext = null;

    try {
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
        const unlockAudio = new Audio();
        unlockAudio.src = 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA';
        await unlockAudio.play().catch(() => { });
        unlockAudio.pause();
        unlockAudio.src = '';
    } catch (error) {
        console.warn('HTMLAudio unlock failed:', error);
    }

    return audioContext;
}

export function getQuestionAudioContext() {
    if (typeof window === 'undefined') return null;
    return window.__beePreparedQuestionAudioContext || null;
}
