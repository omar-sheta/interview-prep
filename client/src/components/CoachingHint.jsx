/**
 * Coaching Hint Component
 * Displays real-time hints when the user is struggling
 */

import { motion } from 'framer-motion';
import { Lightbulb, X } from 'lucide-react';

export default function CoachingHint({ hint, onDismiss }) {
    if (!hint) return null;

    return (
        <motion.div
            initial={{ opacity: 0, y: -20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="coaching-hint bg-gradient-to-r from-amber-900/90 to-orange-900/90 border border-orange-500/50 
                       backdrop-blur-sm rounded-xl p-4 shadow-lg mb-6 flex items-start gap-4"
        >
            <div className="bg-orange-500/20 p-2 rounded-lg text-orange-300">
                <Lightbulb size={24} />
            </div>

            <div className="flex-1">
                <div className="flex justify-between items-start mb-1">
                    <span className="text-xs font-bold text-orange-300 uppercase tracking-wider">
                        Coach's assist
                    </span>
                    <span className="text-xs text-orange-400/60 italic">
                        {hint.trigger === 'silence' ? 'Detected hesitation' : 'Detected struggle'}
                    </span>
                </div>
                <p className="text-orange-100 text-sm leading-relaxed">
                    {hint.message}
                </p>
            </div>

            <button
                onClick={onDismiss}
                className="text-orange-300 hover:text-white transition-colors p-1 hover:bg-white/10 rounded"
                aria-label="Dismiss hint"
            >
                <X size={16} />
            </button>
        </motion.div>
    );
}
