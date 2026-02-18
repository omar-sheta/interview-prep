/**
 * Orb Visualizer Component (Realtime Streaming)
 * Captures 16kHz PCM Audio and streams to backend via 'user_audio_chunk'.
 * Also visualizes audio level.
 */

import { useRef, useEffect, useCallback, useState } from 'react';
import { motion } from 'framer-motion';
import useInterviewStore from '@/store/useInterviewStore';

export default function OrbVisualizer({ size = 200 }) {
    const canvasRef = useRef(null);
    const animationRef = useRef(null);
    const analyserRef = useRef(null);
    const audioContextRef = useRef(null);
    const processorRef = useRef(null);
    const streamRef = useRef(null);
    const dataArrayRef = useRef(null);

    const { isRecording, setRecording } = useInterviewStore();
    const socket = useInterviewStore.getState().socket; // Access socket directly

    // Start Realtime Audio
    const startAudio = useCallback(async () => {
        try {
            audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: 16000, // Request 16kHz if possible
            });

            // Resume context immediately on user gesture
            if (audioContextRef.current.state === 'suspended') {
                await audioContextRef.current.resume();
            }

            const stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                }
            });
            streamRef.current = stream;

            const source = audioContextRef.current.createMediaStreamSource(stream);
            analyserRef.current = audioContextRef.current.createAnalyser();
            analyserRef.current.fftSize = 256;

            // ScriptProcessor for PCM extraction
            processorRef.current = audioContextRef.current.createScriptProcessor(4096, 1, 1);

            processorRef.current.onaudioprocess = (e) => {
                // Check store state directly
                const state = useInterviewStore.getState();
                if (!state.isRecording) return;

                const inputData = e.inputBuffer.getChannelData(0);
                const pcmData = convertFloat32ToInt16(inputData);
                const base64 = bufferToBase64(pcmData);

                const currentSocket = state.socket;
                if (currentSocket && currentSocket.connected) {
                    currentSocket.emit('user_audio_chunk', {
                        audio: base64,
                        sample_rate: audioContextRef.current.sampleRate
                    });
                }
            };

            source.connect(analyserRef.current);
            analyserRef.current.connect(processorRef.current);
            processorRef.current.connect(audioContextRef.current.destination);

            setRecording(true);
        } catch (error) {
            console.error('Error accessing microphone:', error);
            alert('Could not access microphone: ' + error.message);
        }
    }, [setRecording]);

    // Helper: Float32 -> Int16
    const convertFloat32ToInt16 = (buffer) => {
        let l = buffer.length;
        const buf = new Int16Array(l);
        while (l--) {
            buf[l] = Math.min(1, Math.max(-1, buffer[l])) * 0x7FFF;
        }
        return buf.buffer;
    };

    // Helper: ArrayBuffer -> Base64
    const bufferToBase64 = (buffer) => {
        let binary = '';
        const bytes = new Uint8Array(buffer);
        const len = bytes.byteLength;
        for (let i = 0; i < len; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return window.btoa(binary);
    };

    // Stop audio
    const stopAudio = useCallback(() => {
        if (streamRef.current) {
            streamRef.current.getTracks().forEach(track => track.stop());
        }
        if (processorRef.current) {
            processorRef.current.disconnect();
            processorRef.current = null;
        }
        if (audioContextRef.current) {
            audioContextRef.current.close();
            audioContextRef.current = null;
        }
        setRecording(false);
    }, [setRecording]);

    // Visualization State
    const [audioLevel, setAudioLevel] = useState(0);

    // Animation Loop (High Performance)
    useEffect(() => {
        let animationFrame;

        const animate = () => {
            if (analyserRef.current && isRecording) {
                const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount);
                analyserRef.current.getByteFrequencyData(dataArray);

                // Calculate average volume
                const sum = dataArray.reduce((current, val) => current + val, 0);
                const average = sum / dataArray.length;
                // Normalize to 0-1 range with some boost
                const normalized = Math.min(1, average / 50);
                setAudioLevel(normalized);
            } else {
                setAudioLevel(0.05); // Idle breathing
            }

            animationFrame = requestAnimationFrame(animate);
        };

        animate();

        return () => {
            if (animationFrame) cancelAnimationFrame(animationFrame);
        };
    }, [isRecording]);

    return (
        <div className="relative flex items-center justify-center aspect-square flex-shrink-0" style={{ width: size, height: size }}>
            {/* Click Handler Overlay */}
            <div
                className="absolute inset-0 z-50 cursor-pointer rounded-full"
                onClick={isRecording ? stopAudio : startAudio}
            />

            {/* Ambient Glow */}
            <motion.div
                animate={{
                    scale: isRecording ? 1 + audioLevel * 0.5 : [1, 1.1, 1],
                    opacity: isRecording ? 0.6 : 0.4,
                }}
                transition={{ duration: isRecording ? 0.1 : 3, repeat: Infinity, repeatType: "reverse" }}
                className={`absolute inset-0 rounded-full blur-[60px] ${isRecording ? 'bg-orange-500/40' : 'bg-amber-900/30'}`}
            />

            {/* Outer Ring (Rotating) - Thin Tech Border */}
            <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 20, repeat: Infinity, ease: "linear" }}
                className="absolute inset-0 rounded-full border border-white/5 border-t-orange-500/50 border-r-orange-500/20"
            />

            {/* Middle Ring (Counter-Rotating) - Closer to core */}
            <motion.div
                animate={{ rotate: -360 }}
                transition={{ duration: 15, repeat: Infinity, ease: "linear" }}
                className="absolute inset-6 rounded-full border border-white/5 border-b-amber-500/50"
            />

            {/* Core Orb - Larger and glowing */}
            <motion.div
                animate={{
                    scale: isRecording ? 0.95 + audioLevel * 0.1 : 0.95, // Subtle pulse
                    backgroundColor: isRecording ? "rgba(249, 115, 22, 0.1)" : "rgba(15, 23, 42, 0.6)",
                    borderColor: isRecording ? "rgba(251, 191, 36, 0.5)" : "rgba(255, 255, 255, 0.1)"
                }}
                className="absolute inset-10 rounded-full backdrop-blur-xl border shadow-[0_0_50px_rgba(0,0,0,0.5)_inset] flex items-center justify-center overflow-hidden transition-colors duration-500"
            >
                {/* Inner Core Light */}
                <motion.div
                    animate={{ opacity: isRecording ? 0.8 : 0.2 }}
                    className="absolute inset-0 bg-gradient-to-br from-orange-400/20 via-transparent to-transparent"
                />

                {/* Status Content */}
                <div className="z-10 flex flex-col items-center justify-center gap-2">
                    {isRecording ? (
                        <div className="flex items-end gap-1 h-8">
                            {[1, 2, 3, 4, 5].map(bar => (
                                <motion.div
                                    key={bar}
                                    animate={{
                                        height: [10, 32 * Math.max(0.2, audioLevel), 10],
                                        backgroundColor: ["#f97316", "#fbbf24", "#f97316"]
                                    }}
                                    transition={{ duration: 0.4, repeat: Infinity, delay: bar * 0.1 }}
                                    className="w-1.5 rounded-full"
                                />
                            ))}
                        </div>
                    ) : (
                        <motion.div
                            animate={{ scale: [1, 1.1, 1] }}
                            transition={{ duration: 2, repeat: Infinity }}
                            className="w-12 h-12 rounded-full border border-white/10 flex items-center justify-center bg-white/5"
                        >
                            <span className="material-symbols-outlined text-white/50 text-2xl">mic</span>
                        </motion.div>
                    )}

                    <span className="text-[10px] uppercase tracking-[0.2em] text-orange-200/70 font-bold">
                        {isRecording ? 'LISTENING' : 'START'}
                    </span>
                </div>
            </motion.div>
        </div>
    );
}
