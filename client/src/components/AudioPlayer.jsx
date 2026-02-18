/**
 * Audio Player Component
 * Queued audio playback for TTS responses
 */

import { useEffect, useRef } from 'react';
import useInterviewStore from '@/store/useInterviewStore';

export default function AudioPlayer() {
    const audioRef = useRef(null);
    const isPlayingRef = useRef(false);
    const { ttsAudioQueue, popAudio } = useInterviewStore();

    useEffect(() => {
        const playNext = async () => {
            if (isPlayingRef.current || ttsAudioQueue.length === 0) return;

            const audioData = popAudio();
            if (!audioData) return;

            isPlayingRef.current = true;

            try {
                // Decode base64 to blob
                const binaryString = atob(audioData.audio);
                const bytes = new Uint8Array(binaryString.length);
                for (let i = 0; i < binaryString.length; i++) {
                    bytes[i] = binaryString.charCodeAt(i);
                }

                const blob = new Blob([bytes], { type: 'audio/wav' });
                const url = URL.createObjectURL(blob);

                if (audioRef.current) {
                    audioRef.current.src = url;
                    await audioRef.current.play();
                }
            } catch (error) {
                console.error('Error playing audio:', error);
                isPlayingRef.current = false;
            }
        };

        playNext();
    }, [ttsAudioQueue, popAudio]);

    const handleEnded = () => {
        isPlayingRef.current = false;
        // Check for next audio in queue
        if (useInterviewStore.getState().ttsAudioQueue.length > 0) {
            // Trigger re-render to play next
            useInterviewStore.setState({});
        }
    };

    return (
        <audio
            ref={audioRef}
            onEnded={handleEnded}
            className="hidden"
        />
    );
}
