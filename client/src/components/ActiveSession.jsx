/**
 * Active Session - Live Interview Room
 * SOTA Interview Agent
 */

import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import useInterviewStore from '@/store/useInterviewStore';

export default function ActiveSession() {
    const [elapsedTime, setElapsedTime] = useState(0);
    const [isPaused, setIsPaused] = useState(false);
    const [isMuted, setIsMuted] = useState(false);
    const audioLevelRef = useRef(1);

    const {
        isRecording,
        transcript,
        currentQuestion,
        aiThinking,
        thinkingLog,
        endInterview,
        toggleRecording,
    } = useInterviewStore();

    // Timer
    useEffect(() => {
        if (isPaused) return;
        const interval = setInterval(() => {
            setElapsedTime((prev) => prev + 1);
        }, 1000);
        return () => clearInterval(interval);
    }, [isPaused]);

    const formatTime = (seconds) => {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    };

    const handleEnd = () => {
        if (confirm('Are you sure you want to end the session?')) {
            endInterview();
        }
    };

    // Simulated audio level for orb animation
    const [audioLevel, setAudioLevel] = useState(1);
    useEffect(() => {
        const interval = setInterval(() => {
            if (isRecording && !isMuted) {
                setAudioLevel(0.95 + Math.random() * 0.1);
            } else {
                setAudioLevel(1);
            }
        }, 100);
        return () => clearInterval(interval);
    }, [isRecording, isMuted]);

    return (
        <div className="bg-[#0c1117] text-white font-display overflow-hidden h-screen w-full relative">
            {/* Ambient Background Effects */}
            <div className="absolute inset-0 z-0 pointer-events-none overflow-hidden">
                {/* Vignette */}
                <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_0%,rgba(12,17,23,0.8)_80%,#0c1117_100%)]" />
                {/* Scanlines Texture */}
                <div className="absolute inset-0 opacity-[0.03] scanlines pointer-events-none" />
                {/* Deep Ambient Glow */}
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] bg-[#00c2b2]/5 rounded-full blur-[120px]" />
            </div>

            <div className="relative z-10 flex flex-col h-full w-full max-w-[1440px] mx-auto p-6 md:p-10">
                {/* Header: Timer & Security Status */}
                <header className="flex justify-between items-start w-full">
                    {/* Timer Component */}
                    <div className="flex flex-col gap-1">
                        <div className="flex items-center gap-3">
                            <span className="material-symbols-outlined text-[#00c2b2]/80 animate-pulse text-sm">
                                radio_button_checked
                            </span>
                            <span className="text-white/40 text-sm tracking-widest font-medium uppercase">
                                Session Active
                            </span>
                        </div>
                        <div className="text-4xl md:text-5xl font-bold text-white/90 tracking-tighter tabular-nums leading-none">
                            {formatTime(elapsedTime)}
                        </div>
                    </div>

                    {/* Security Chip & Mini Terminal */}
                    <div className="flex flex-col items-end gap-4">
                        {/* Chip */}
                        <div className="glass-panel flex items-center gap-2 px-3 py-1.5 rounded-full shadow-lg shadow-black/20">
                            <span className="material-symbols-outlined text-[#00c2b2] text-sm">lock</span>
                            <span className="text-[#00c2b2] text-xs font-bold tracking-wider">LOCAL SECURE</span>
                        </div>

                        {/* Mini Status Terminal */}
                        <div className="hidden md:flex flex-col items-end gap-1 text-right">
                            <div className="glass-panel rounded-lg p-3 min-w-[240px]">
                                <div className="flex flex-col gap-1 font-mono text-xs leading-relaxed text-white/50">
                                    <p className="flex justify-between">
                                        <span>&gt; [SYS]:</span>
                                        <span className="text-[#00c2b2]">
                                            {isRecording ? 'Voice Activity Detected' : 'Waiting for input'}
                                        </span>
                                    </p>
                                    <p className="flex justify-between">
                                        <span>&gt; [NET]:</span>
                                        <span>Offline Mode</span>
                                    </p>
                                    <p className="flex justify-between animate-pulse">
                                        <span>&gt; [AI]:</span>
                                        <span className="text-white/80">
                                            {aiThinking ? 'Processing...' : 'Ready'}
                                        </span>
                                    </p>
                                </div>
                            </div>
                        </div>
                    </div>
                </header>

                {/* Main Content: The Orb */}
                <main className="flex-1 flex flex-col justify-center items-center relative w-full">
                    {/* The Orb Visualizer */}
                    <div className="relative w-[300px] h-[300px] md:w-[500px] md:h-[500px] flex items-center justify-center">
                        {/* Outer Rings */}
                        <div className="absolute inset-0 border border-[#00c2b2]/10 rounded-full scale-125 opacity-20 animate-spin-slow" />
                        <div className="absolute inset-0 border border-[#00c2b2]/5 rounded-full scale-150 opacity-10 animate-spin-slow" style={{ animationDirection: 'reverse', animationDuration: '15s' }} />

                        {/* Dynamic Blobs */}
                        <div className="absolute top-0 -left-4 w-72 h-72 bg-[#00c2b2]/20 rounded-full mix-blend-screen filter blur-3xl opacity-50 animate-blob" />
                        <div className="absolute top-0 -right-4 w-72 h-72 bg-teal-600/20 rounded-full mix-blend-screen filter blur-3xl opacity-50 animate-blob animation-delay-2000" />
                        <div className="absolute -bottom-8 left-20 w-72 h-72 bg-emerald-500/20 rounded-full mix-blend-screen filter blur-3xl opacity-50 animate-blob animation-delay-4000" />

                        {/* The Core */}
                        <motion.div
                            className="relative w-64 h-64 bg-black rounded-full flex items-center justify-center shadow-[0_0_80px_-20px_rgba(0,194,178,0.5)] z-10"
                            animate={{
                                scale: audioLevel,
                                boxShadow: isRecording
                                    ? '0 0 100px -10px rgba(0,194,178,0.7)'
                                    : '0 0 80px -20px rgba(0,194,178,0.5)'
                            }}
                            transition={{ duration: 0.1 }}
                        >
                            {/* Inner fluid gradient texture */}
                            <div className="absolute inset-2 rounded-full overflow-hidden opacity-80">
                                <div className="w-full h-full orb-core animate-spin-slow opacity-60" style={{ animationDuration: '8s' }} />
                            </div>
                            {/* Specular reflection */}
                            <div className="absolute top-4 left-8 w-24 h-12 bg-white/5 rounded-[100%] rotate-[-45deg] blur-md" />
                        </motion.div>
                    </div>
                </main>

                {/* Footer: Transcript & Controls */}
                <footer className="relative z-20 flex flex-col items-center gap-6 w-full max-w-3xl mx-auto">
                    {/* Ghost Transcript */}
                    <div className="w-full text-center px-4 md:px-12 fade-mask-top min-h-[120px] flex flex-col justify-end pb-4">
                        {currentQuestion && (
                            <p className="text-white/40 text-lg md:text-xl font-normal leading-relaxed blur-[0.5px] transition-all duration-500">
                                "{currentQuestion}"
                            </p>
                        )}
                        <AnimatePresence mode="wait">
                            {transcript && (
                                <motion.p
                                    key={transcript}
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    exit={{ opacity: 0 }}
                                    className="text-white text-xl md:text-2xl font-normal leading-relaxed mt-2 drop-shadow-lg"
                                >
                                    {transcript}
                                </motion.p>
                            )}
                        </AnimatePresence>
                    </div>

                    {/* Control Dock */}
                    <div className="group relative pt-4">
                        <div className="glass-panel rounded-full px-6 py-3 flex items-center gap-6 transition-all duration-300 transform group-hover:-translate-y-1 group-hover:bg-[#161b22]/90 group-hover:shadow-[0_0_30px_-5px_rgba(0,0,0,0.5)]">
                            {/* Mute */}
                            <button
                                onClick={() => setIsMuted(!isMuted)}
                                className="relative flex flex-col items-center gap-1 text-white/60 hover:text-white transition-colors"
                            >
                                <div className="p-3 rounded-full hover:bg-white/10 transition-colors">
                                    <span className="material-symbols-outlined text-2xl">
                                        {isMuted ? 'mic_off' : 'mic'}
                                    </span>
                                </div>
                            </button>

                            {/* Pause */}
                            <button
                                onClick={() => setIsPaused(!isPaused)}
                                className="relative flex flex-col items-center gap-1 text-white/60 hover:text-white transition-colors"
                            >
                                <div className="p-3 rounded-full hover:bg-white/10 transition-colors">
                                    <span className="material-symbols-outlined text-2xl">
                                        {isPaused ? 'play_arrow' : 'pause'}
                                    </span>
                                </div>
                            </button>

                            <div className="w-px h-8 bg-white/10" />

                            {/* End Session */}
                            <button
                                onClick={handleEnd}
                                className="relative flex items-center gap-2 bg-red-500/10 hover:bg-red-500/20 text-red-400 hover:text-red-300 pl-3 pr-5 py-2 rounded-full transition-all border border-red-500/20"
                            >
                                <span className="material-symbols-outlined text-xl">call_end</span>
                                <span className="text-sm font-bold tracking-wide">END</span>
                            </button>
                        </div>

                        {/* Helper text */}
                        <p className="absolute -bottom-8 left-0 right-0 text-center text-[10px] text-white/20 uppercase tracking-[0.2em] transition-opacity duration-300 group-hover:opacity-0">
                            Controls
                        </p>
                    </div>
                </footer>
            </div>
        </div>
    );
}
