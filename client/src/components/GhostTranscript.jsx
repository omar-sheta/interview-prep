/**
 * Ghost Transcript Component
 * Centered scrolling transcript with fade-in effect for streaming tokens
 */

import { useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import useInterviewStore from '@/store/useInterviewStore';

export default function GhostTranscript() {
    const { transcript, currentTokens } = useInterviewStore();
    const scrollRef = useRef(null);

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [transcript, currentTokens]);

    // Parse transcript into messages
    const messages = transcript.split('\n\n').filter(Boolean).map((msg, i) => {
        const isUser = msg.startsWith('You:');
        const content = msg.replace(/^(You:|Agent:)\s*/, '');
        return { id: i, isUser, content };
    });

    return (
        <div
            ref={scrollRef}
            className="flex-1 overflow-auto px-8 py-6 flex flex-col items-center"
        >
            <div className="max-w-2xl w-full space-y-6">
                <AnimatePresence mode="popLayout">
                    {messages.map((msg) => (
                        <motion.div
                            key={msg.id}
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -10 }}
                            transition={{ duration: 0.3 }}
                            className={`flex ${msg.isUser ? 'justify-end' : 'justify-start'}`}
                        >
                            <div
                                className={`max-w-[80%] px-4 py-3 rounded-2xl ${msg.isUser
                                        ? 'bg-purple-500/20 text-purple-100'
                                        : 'bg-white/5 text-zinc-200'
                                    }`}
                            >
                                <p className="text-sm leading-relaxed">{msg.content}</p>
                            </div>
                        </motion.div>
                    ))}
                </AnimatePresence>

                {/* Streaming tokens */}
                {currentTokens && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className="flex justify-start"
                    >
                        <div className="max-w-[80%] px-4 py-3 rounded-2xl bg-white/5">
                            <p className="text-sm leading-relaxed text-zinc-200">
                                {currentTokens.split('').map((char, i) => (
                                    <motion.span
                                        key={i}
                                        initial={{ opacity: 0 }}
                                        animate={{ opacity: 1 }}
                                        transition={{ delay: i * 0.01 }}
                                    >
                                        {char}
                                    </motion.span>
                                ))}
                                <span className="inline-block w-2 h-4 bg-purple-400 ml-1 animate-pulse" />
                            </p>
                        </div>
                    </motion.div>
                )}

                {/* Empty state */}
                {messages.length === 0 && !currentTokens && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className="text-center py-20"
                    >
                        <p className="text-zinc-500 text-lg">
                            Start speaking to begin the interview
                        </p>
                        <p className="text-zinc-600 text-sm mt-2">
                            Click the orb below to activate your microphone
                        </p>
                    </motion.div>
                )}
            </div>
        </div>
    );
}
