/**
 * Evaluation Card Component
 * Displays detailed feedback for an interview answer
 */

import { motion } from 'framer-motion';

export default function EvaluationCard({ evaluation }) {
    const {
        score,
        score_breakdown,
        strengths,
        missing_concepts,
        optimized_answer,
        coaching_tip
    } = evaluation;

    // Score color
    const getScoreColor = (score) => {
        if (score >= 8) return 'text-green-400';
        if (score >= 6) return 'text-yellow-400';
        return 'text-red-400';
    };

    // Parse bold text in optimized answer
    const renderOptimizedAnswer = (text) => {
        if (!text) return null;

        // Split by **bold** markers
        const parts = text.split(/\*\*(.*?)\*\*/g);

        return parts.map((part, i) => {
            // Odd indices are bold
            if (i % 2 === 1) {
                return <strong key={i} className="text-[#00c2b2] font-semibold bg-[#00c2b2]/10 px-1 rounded">{part}</strong>;
            }
            return <span key={i}>{part}</span>;
        });
    };

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="evaluation-card bg-zinc-900/80 border border-zinc-700 rounded-xl overflow-hidden shadow-2xl"
        >
            {/* Header / Score */}
            <div className="p-6 border-b border-zinc-800 flex flex-col items-center">
                <div className={`text-5xl font-bold mb-2 ${getScoreColor(score)}`}>
                    {score}/10
                </div>
                <div className="flex gap-8 text-sm text-zinc-400 mt-2">
                    <div className="flex flex-col items-center">
                        <span className="font-semibold text-white">{score_breakdown?.clarity || 0}/3</span>
                        <span>Clarity</span>
                    </div>
                    <div className="flex flex-col items-center">
                        <span className="font-semibold text-white">{score_breakdown?.accuracy || 0}/4</span>
                        <span>Accuracy</span>
                    </div>
                    <div className="flex flex-col items-center">
                        <span className="font-semibold text-white">{score_breakdown?.completeness || 0}/3</span>
                        <span>Completeness</span>
                    </div>
                </div>
            </div>

            <div className="p-6 space-y-6">
                {/* Strengths */}
                {strengths && strengths.length > 0 && (
                    <div>
                        <h3 className="text-green-400 font-medium mb-2 flex items-center gap-2">
                            <span>✅</span> What You Got Right
                        </h3>
                        <ul className="space-y-1 ml-1">
                            {strengths.map((item, i) => (
                                <li key={i} className="text-sm text-zinc-300 flex items-start gap-2">
                                    <span className="text-zinc-600 mt-1">•</span>
                                    {item}
                                </li>
                            ))}
                        </ul>
                    </div>
                )}

                {/* Missing Concepts */}
                {missing_concepts && missing_concepts.length > 0 && (
                    <div>
                        <h3 className="text-red-400 font-medium mb-2 flex items-center gap-2">
                            <span>🎯</span> Key Points to Add
                        </h3>
                        <ul className="space-y-1 ml-1">
                            {missing_concepts.map((item, i) => (
                                <li key={i} className="text-sm text-zinc-300 flex items-start gap-2">
                                    <span className="text-zinc-600 mt-1">•</span>
                                    {item}
                                </li>
                            ))}
                        </ul>
                    </div>
                )}

                {/* Optimized Answer */}
                {score < 9 && optimized_answer && (
                    <div className="bg-zinc-800/50 rounded-lg p-4 border border-zinc-700/50">
                        <h3 className="text-[#00c2b2] font-medium mb-2 text-sm uppercase tracking-wider">
                            🚀 Optimized Answer
                        </h3>
                        <div className="text-sm text-zinc-300 leading-relaxed">
                            {renderOptimizedAnswer(optimized_answer)}
                        </div>
                    </div>
                )}

                {/* Coaching Tip */}
                {coaching_tip && (
                    <div className="flex gap-3 bg-orange-500/10 border border-orange-500/20 rounded-lg p-4">
                        <span className="text-xl">💡</span>
                        <div>
                            <p className="text-orange-200 text-sm font-medium mb-1">Coach's Tip</p>
                            <p className="text-orange-100/80 text-sm">{coaching_tip}</p>
                        </div>
                    </div>
                )}
            </div>
        </motion.div>
    );
}
