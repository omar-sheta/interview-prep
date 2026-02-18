/**
 * Layout Component - Sci-Fi Cinematic
 * Deep blacks, glassmorphism, ambient lighting
 */

import { useState } from 'react';
import { motion } from 'framer-motion';
import {
    ChevronLeft,
    ChevronRight,
    Mic,
    MicOff,
    Settings,
    Sparkles,
    Zap,
    Brain,
    Wifi,
    WifiOff,
} from 'lucide-react';
import useInterviewStore, { useConnectionStatus } from '@/store/useInterviewStore';
import ThinkingTerminal from './ThinkingTerminal';
import ParticleBackground from './ParticleBackground';
import GradientOrbs from './GradientOrbs';

export default function Layout({ children, sidebar }) {
    const [sidebarOpen, setSidebarOpen] = useState(true);
    const connectionStatus = useConnectionStatus();
    const { appState, isRecording } = useInterviewStore();

    return (
        <div className="relative h-screen w-screen overflow-hidden">
            {/* Background Effects */}
            <GradientOrbs />
            <ParticleBackground particleCount={30} />

            {/* Main Container */}
            <div className="relative z-10 h-full flex">
                {/* Sidebar */}
                <motion.aside
                    initial={false}
                    animate={{ width: sidebarOpen ? 300 : 0 }}
                    transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
                    className="relative h-full overflow-hidden"
                >
                    <div className="absolute inset-0 w-[300px]">
                        {/* Sidebar Glass Panel */}
                        <div className="h-full glass-panel rounded-none flex flex-col">
                            {/* Sidebar Header */}
                            <motion.div
                                className="p-5 border-b border-white/5"
                                initial={{ opacity: 0, y: -10 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: 0.1 }}
                            >
                                <div className="flex items-center gap-3">
                                    <motion.div
                                        className="relative"
                                        whileHover={{ scale: 1.05, rotate: 5 }}
                                    >
                                        <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-orange-500 via-amber-500 to-yellow-500 flex items-center justify-center shadow-lg shadow-orange-500/30">
                                            <Brain className="w-5 h-5 text-white" />
                                        </div>
                                        <motion.div
                                            className={`absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 border-black ${connectionStatus === 'connected' ? 'bg-green-400' : 'bg-red-400'
                                                }`}
                                            animate={{ scale: [1, 1.2, 1] }}
                                            transition={{ duration: 2, repeat: Infinity }}
                                        />
                                    </motion.div>
                                    <div>
                                        <h2 className="text-shine font-semibold text-lg">Insights</h2>
                                        <p className="text-xs text-zinc-500">AI-Powered Analysis</p>
                                    </div>
                                </div>
                            </motion.div>

                            {/* Sidebar Content */}
                            <div className="flex-1 p-4 overflow-auto">
                                {sidebar}
                            </div>

                            {/* Sidebar Footer */}
                            <div className="border-t border-white/5">
                                <ThinkingTerminal />
                            </div>
                        </div>
                    </div>
                </motion.aside>

                {/* Sidebar Toggle */}
                <motion.button
                    onClick={() => setSidebarOpen(!sidebarOpen)}
                    className="absolute top-1/2 -translate-y-1/2 z-20 p-1.5 rounded-r-lg 
                     glass-card text-zinc-500 hover:text-white"
                    style={{ left: sidebarOpen ? '300px' : '0' }}
                    whileHover={{ scale: 1.1 }}
                    whileTap={{ scale: 0.95 }}
                >
                    {sidebarOpen ? <ChevronLeft size={14} /> : <ChevronRight size={14} />}
                </motion.button>

                {/* Main Viewport */}
                <main className="flex-1 flex flex-col min-w-0 p-4">
                    {/* Content Area */}
                    <motion.div
                        className="flex-1 glass-panel rounded-2xl overflow-hidden relative"
                        initial={{ opacity: 0, scale: 0.98 }}
                        animate={{ opacity: 1, scale: 1 }}
                        transition={{ duration: 0.4 }}
                    >
                        {/* Top Shine Line */}
                        <div
                            className="absolute top-0 left-[15%] right-[15%] h-px"
                            style={{
                                background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.15), transparent)',
                            }}
                        />

                        {/* Content */}
                        <div className="h-full overflow-auto">
                            {children}
                        </div>
                    </motion.div>

                    {/* Control Bar */}
                    <motion.div
                        className="mt-4 px-5 py-3.5 glass-card rounded-xl flex items-center justify-between"
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.2 }}
                    >
                        {/* Left - Status */}
                        <div className="flex items-center gap-3">
                            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium ${connectionStatus === 'connected'
                                ? 'bg-green-500/10 text-green-400'
                                : 'bg-red-500/10 text-red-400'
                                }`}>
                                {connectionStatus === 'connected' ? <Wifi size={12} /> : <WifiOff size={12} />}
                                {connectionStatus === 'connected' ? 'Connected' : 'Disconnected'}
                            </div>

                            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium bg-orange-500/10 text-orange-400">
                                <Sparkles size={12} />
                                {appState.toUpperCase()}
                            </div>
                        </div>

                        {/* Center - Branding */}
                        <div className="flex items-center gap-2">
                            <Zap className="w-4 h-4 text-amber-400" />
                            <span className="text-sm font-semibold text-shine">
                                HIVE Interview Agent
                            </span>
                        </div>

                        {/* Right - Controls */}
                        <div className="flex items-center gap-2">
                            <motion.button
                                whileHover={{ scale: 1.05 }}
                                whileTap={{ scale: 0.95 }}
                                className={`p-2.5 rounded-lg transition-all ${isRecording
                                    ? 'bg-red-500/20 text-red-400 shadow-lg shadow-red-500/20'
                                    : 'glass-card text-zinc-400 hover:text-white'
                                    }`}
                            >
                                {isRecording ? <Mic size={16} /> : <MicOff size={16} />}
                            </motion.button>

                            <motion.button
                                whileHover={{ scale: 1.05 }}
                                whileTap={{ scale: 0.95 }}
                                className="p-2.5 glass-card text-zinc-400 hover:text-white"
                            >
                                <Settings size={16} />
                            </motion.button>
                        </div>
                    </motion.div>
                </main>
            </div>
        </div>
    );
}
