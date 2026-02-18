/**
 * Thinking Terminal Component
 * Shows internal monologue/status updates in a low-opacity terminal
 */

import { useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Terminal } from 'lucide-react';
import useInterviewStore from '@/store/useInterviewStore';

export default function ThinkingTerminal() {
    const { thinkingLog } = useInterviewStore();
    const scrollRef = useRef(null);

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [thinkingLog]);

    if (thinkingLog.length === 0) return null;

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="fixed bottom-20 left-4 right-4 max-w-xl"
        >
            <div className="glass-panel-subtle p-3 opacity-60 hover:opacity-90 transition-opacity">
                <div className="flex items-center gap-2 mb-2 text-xs text-zinc-500">
                    <Terminal size={12} />
                    <span>Internal Monologue</span>
                </div>
                <div
                    ref={scrollRef}
                    className="max-h-24 overflow-auto text-xs font-mono space-y-1"
                >
                    <AnimatePresence mode="popLayout">
                        {thinkingLog.slice(-5).map((log, i) => (
                            <motion.div
                                key={i}
                                initial={{ opacity: 0, x: -10 }}
                                animate={{ opacity: 1, x: 0 }}
                                exit={{ opacity: 0 }}
                                className="text-zinc-400"
                            >
                                <span className="text-zinc-600">[{log.time}]</span>{' '}
                                {log.message}
                            </motion.div>
                        ))}
                    </AnimatePresence>
                </div>
            </div>
        </motion.div>
    );
}
