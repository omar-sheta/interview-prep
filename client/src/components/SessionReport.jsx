/**
 * Session Report - Interview Performance Debrief
 * Modern Minimalistic Redesign
 */

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import useInterviewStore from '@/store/useInterviewStore';

export default function SessionReport() {
    const navigate = useNavigate();
    const { interviewSummary, allEvaluations, resetSession } = useInterviewStore();

    // Transform backend data to frontend format
    let sessionData;

    // Use actual data or minimal fallback
    const rawData = interviewSummary || {
        average_score: 0,
        overall_feedback: "No session data available.",
        top_strengths: [],
        areas_to_improve: [],
        duration: 0
    };

    // Calculate derived data
    const totalDuration = allEvaluations?.reduce((acc, curr) => acc + (curr.duration || 0), 0) || rawData.duration || 0;
    const durationMins = Math.round(totalDuration / 60);

    const telemetry = rawData.telemetry || {};

    const formatData = () => {
        return {
            score: Math.round((rawData.average_score || 0) * 10),
            date: new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }),
            duration: `${durationMins} min`,
            category: 'Technical Practice',
            summary: rawData.average_score >= 8 ? "Strong Performance" : (rawData.average_score >= 6 ? "Good Progress" : "Needs Improvement"),
            description: rawData.overall_feedback || "Session completed.",
            badges: [
                ...(rawData.top_strengths || []).map(s => ({ label: s, type: 'success' })),
                ...(rawData.areas_to_improve || []).map(s => ({ label: s, type: 'warn' }))
            ],
            questions: (allEvaluations || []).map((ev, idx) => ({
                id: idx + 1,
                question: ev.question?.text || "Question",
                category: ev.question?.category || "General",
                duration: ev.duration ? `${Math.round(ev.duration)}s` : "-",
                score: ev.evaluation?.score || 0,
                userAnswer: ev.answer,
                optimizedAnswer: ev.evaluation?.optimized_answer,
                issues: ev.evaluation?.missing_concepts || [],
                improvements: ev.evaluation?.coaching_tip,
            })),
            telemetry: {
                pace: telemetry.pace || 0,
                fillerWords: telemetry.fillerWords || 0,
                confidence: telemetry.confidence || 'N/A',
                wordCount: telemetry.word_count || 0,
                fillerDetail: telemetry.filler_detail || {},
                avgSentenceLength: telemetry.avg_sentence_length || 0,
            },
            actionItems: rawData.action_items || [],
            communicationFeedback: rawData.communication_feedback || '',
        };
    };

    sessionData = formatData();

    const [expandedQuestion, setExpandedQuestion] = useState(null);

    const handleNewSession = () => {
        resetSession();
        navigate('/');
    };

    const getScoreColor = (score) => {
        if (score >= 8) return 'text-green-500';
        if (score >= 6) return 'text-amber-500';
        return 'text-red-500';
    };

    // Premium UI Render
    return (
        <div className="min-h-screen bg-[#030712] text-white selection:bg-orange-500/30 selection:text-orange-200 font-sans overflow-x-hidden">
            {/* Ambient Background Gradients */}
            <div className="fixed inset-0 pointer-events-none">
                <div className="absolute top-[-10%] left-[-10%] w-[500px] h-[500px] bg-orange-500/10 rounded-full blur-[100px]" />
                <div className="absolute bottom-[-10%] right-[-10%] w-[600px] h-[600px] bg-amber-500/10 rounded-full blur-[120px]" />
            </div>

            {/* Header */}
            <header className="sticky top-0 z-50 border-b border-white/5 bg-[#030712]/80 backdrop-blur-xl">
                <div className="max-w-6xl mx-auto px-6 h-20 flex items-center justify-between">
                    <div className="flex items-center gap-3 cursor-pointer group" onClick={() => navigate('/')}>
                        <div className="relative w-10 h-10 flex items-center justify-center bg-white/5 rounded-xl border border-white/10 group-hover:border-orange-500/50 transition-colors">
                            <span className="material-symbols-outlined text-orange-400">bar_chart</span>
                        </div>
                        <div>
                            <h1 className="text-lg font-bold tracking-tight">Session Report</h1>
                            <p className="text-xs text-gray-400">{sessionData.date} • {sessionData.time || 'Completed'}</p>
                        </div>
                    </div>
                    <button
                        onClick={handleNewSession}
                        className="px-5 py-2 bg-white text-black text-sm font-bold rounded-full hover:scale-105 active:scale-95 transition-all shadow-[0_0_20px_rgba(255,255,255,0.2)]"
                    >
                        New Session
                    </button>
                </div>
            </header>

            <main className="max-w-6xl mx-auto px-6 py-12 relative z-10">
                {/* Hero Grid */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 mb-16">
                    {/* Main Score Card */}
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="lg:col-span-2 relative overflow-hidden rounded-3xl p-1 bg-gradient-to-br from-white/10 to-transparent border border-white/10"
                    >
                        <div className="absolute inset-0 bg-[#0c1117]/90 backdrop-blur-sm" />
                        <div className="relative h-full p-8 flex flex-col md:flex-row items-center gap-12">
                            {/* Score Ring */}
                            <div className="relative flex-shrink-0">
                                <svg width="200" height="200" className="-rotate-90 transform">
                                    <circle cx="100" cy="100" r="88" fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="12" strokeLinecap="round" />
                                    <motion.circle
                                        cx="100" cy="100" r="88"
                                        fill="none"
                                        stroke={sessionData.score >= 80 ? '#22c55e' : (sessionData.score >= 60 ? '#f59e0b' : '#ef4444')}
                                        strokeWidth="12"
                                        strokeLinecap="round"
                                        strokeDasharray={2 * Math.PI * 88}
                                        initial={{ strokeDashoffset: 2 * Math.PI * 88 }}
                                        animate={{ strokeDashoffset: 2 * Math.PI * 88 * (1 - sessionData.score / 100) }}
                                        transition={{ duration: 1.5, ease: "easeOut" }}
                                    />
                                </svg>
                                <div className="absolute inset-0 flex flex-col items-center justify-center">
                                    <span className="text-6xl font-bold tracking-tighter text-white">
                                        <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                                            {sessionData.score}
                                        </motion.span>
                                    </span>
                                    <span className="text-xs uppercase tracking-widest text-gray-500 mt-2 font-semibold">Total Score</span>
                                </div>
                                {/* Glow reflection */}
                                <div className="absolute -inset-4 bg-orange-500/20 blur-3xl -z-10 rounded-full" />
                            </div>

                            {/* Text Summary */}
                            <div className="text-center md:text-left">
                                <motion.div
                                    initial={{ opacity: 0, x: 20 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    transition={{ delay: 0.3 }}
                                >
                                    <h2 className="text-3xl md:text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-br from-white to-gray-400 mb-4">
                                        {sessionData.summary}
                                    </h2>
                                    <p className="text-gray-400 leading-relaxed text-lg mb-6">
                                        {sessionData.description}
                                    </p>
                                    <div className="flex flex-wrap justify-center md:justify-start gap-3">
                                        {sessionData.badges.map((badge, i) => (
                                            <span
                                                key={i}
                                                className={`px-3 py-1.5 rounded-lg text-xs font-bold tracking-wide uppercase border ${badge.type === 'success'
                                                    ? 'bg-green-500/10 border-green-500/20 text-green-400'
                                                    : 'bg-amber-500/10 border-amber-500/20 text-amber-400'
                                                    }`}
                                            >
                                                {badge.label}
                                            </span>
                                        ))}
                                    </div>
                                </motion.div>
                            </div>
                        </div>
                    </motion.div>

                    {/* Stats Vertical Stack */}
                    <div className="space-y-4">
                        {[
                            { label: 'Duration', value: sessionData.duration, icon: 'schedule', color: 'text-orange-400', bg: 'bg-orange-500/10' },
                            { label: 'Speaking Pace', value: `${sessionData.telemetry.pace} WPM`, icon: 'speed', color: 'text-amber-400', bg: 'bg-amber-500/10' },
                            { label: 'Confidence', value: sessionData.telemetry.confidence, icon: 'psychology', color: 'text-yellow-400', bg: 'bg-yellow-500/10' },
                            { label: 'Filler Words', value: sessionData.telemetry.fillerWords, icon: 'graphic_eq', color: 'text-rose-400', bg: 'bg-rose-500/10' },
                        ].map((stat, i) => (
                            <motion.div
                                key={stat.label}
                                initial={{ opacity: 0, x: 20 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ delay: 0.2 + i * 0.1 }}
                                className="p-4 rounded-2xl bg-white/5 border border-white/5 hover:bg-white/10 transition-colors flex items-center gap-4 group"
                            >
                                <div className={`w-12 h-12 rounded-xl ${stat.bg} ${stat.color} flex items-center justify-center group-hover:scale-110 transition-transform`}>
                                    <span className="material-symbols-outlined">{stat.icon}</span>
                                </div>
                                <div>
                                    <div className="text-xl font-bold text-white">{stat.value}</div>
                                    <div className="text-xs text-gray-500 uppercase font-semibold">{stat.label}</div>
                                </div>
                            </motion.div>
                        ))}
                    </div>
                </div>

                {/* Communication Feedback + Action Items Row */}
                {(sessionData.communicationFeedback || sessionData.actionItems.length > 0) && (
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-16">
                        {/* Communication Feedback */}
                        {sessionData.communicationFeedback && (
                            <motion.div
                                initial={{ opacity: 0, y: 20 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: 0.5 }}
                                className="p-6 rounded-2xl bg-white/5 border border-white/5"
                            >
                                <div className="flex items-center gap-2 mb-4">
                                    <span className="material-symbols-outlined text-amber-400">record_voice_over</span>
                                    <h3 className="text-lg font-bold text-white">Communication Style</h3>
                                </div>
                                <p className="text-gray-300 leading-relaxed">{sessionData.communicationFeedback}</p>

                                {/* Filler word breakdown */}
                                {Object.keys(sessionData.telemetry.fillerDetail || {}).length > 0 && (
                                    <div className="mt-4 pt-4 border-t border-white/5">
                                        <p className="text-xs text-gray-500 uppercase font-semibold mb-2">Filler Word Breakdown</p>
                                        <div className="flex flex-wrap gap-2">
                                            {Object.entries(sessionData.telemetry.fillerDetail).map(([word, count]) => (
                                                <span key={word} className="px-2.5 py-1 rounded-lg text-xs font-mono bg-rose-500/10 border border-rose-500/20 text-rose-400">
                                                    "{word}" x{count}
                                                </span>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </motion.div>
                        )}

                        {/* Action Items */}
                        {sessionData.actionItems.length > 0 && (
                            <motion.div
                                initial={{ opacity: 0, y: 20 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: 0.6 }}
                                className="p-6 rounded-2xl bg-white/5 border border-white/5"
                            >
                                <div className="flex items-center gap-2 mb-4">
                                    <span className="material-symbols-outlined text-green-400">task_alt</span>
                                    <h3 className="text-lg font-bold text-white">Action Items</h3>
                                </div>
                                <ul className="space-y-3">
                                    {sessionData.actionItems.map((item, i) => (
                                        <li key={i} className="flex items-start gap-3 text-gray-300 text-sm">
                                            <span className="mt-0.5 w-5 h-5 rounded-full bg-green-500/10 border border-green-500/20 text-green-400 flex items-center justify-center text-xs font-bold flex-shrink-0">
                                                {i + 1}
                                            </span>
                                            <span>{item}</span>
                                        </li>
                                    ))}
                                </ul>
                            </motion.div>
                        )}
                    </div>
                )}

                {/* Questions Section */}
                <div className="space-y-6">
                    <div className="flex items-center gap-3 mb-8">
                        <div className="w-1 h-8 bg-gradient-to-b from-orange-400 to-amber-600 rounded-full" />
                        <h2 className="text-2xl font-bold text-white">Question Detailed Analysis</h2>
                    </div>

                    <div className="space-y-4">
                        {sessionData.questions.length === 0 ? (
                            <div className="p-12 rounded-3xl border border-dashed border-white/10 text-center text-gray-500">
                                No questions recorded.
                            </div>
                        ) : (
                            sessionData.questions.map((q, idx) => (
                                <motion.div
                                    key={q.id}
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    transition={{ delay: 0.4 + idx * 0.1 }}
                                    onClick={() => setExpandedQuestion(expandedQuestion === q.id ? null : q.id)}
                                    className={`group rounded-2xl border transition-all duration-300 overflow-hidden cursor-pointer ${expandedQuestion === q.id
                                        ? 'bg-[#161b22] border-orange-500/30 shadow-[0_0_30px_rgba(249,115,22,0.1)] ring-1 ring-orange-500/30'
                                        : 'bg-white/5 border-white/5 hover:border-white/20 hover:bg-white/10'
                                        }`}
                                >
                                    <div className="p-6 flex items-start gap-5">
                                        <div className={`mt-1 flex-shrink-0 w-12 h-12 rounded-xl flex items-center justify-center text-lg font-bold border ${q.score >= 8
                                            ? 'bg-green-500/10 border-green-500/20 text-green-400'
                                            : q.score >= 5
                                                ? 'bg-amber-500/10 border-amber-500/20 text-amber-400'
                                                : 'bg-red-500/10 border-red-500/20 text-red-400'
                                            }`}>
                                            {q.score}
                                        </div>

                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center justify-between mb-2">
                                                <h3 className="text-lg font-semibold text-gray-200 group-hover:text-white transition-colors line-clamp-2">
                                                    {q.question}
                                                </h3>
                                                <span className={`material-symbols-outlined text-gray-500 transition-transform duration-300 mr-2 ${expandedQuestion === q.id ? 'rotate-180 text-orange-400' : ''}`}>
                                                    expand_more
                                                </span>
                                            </div>
                                            <div className="flex items-center gap-4 text-xs font-medium text-gray-500 uppercase tracking-wider">
                                                <span className="flex items-center gap-1">
                                                    <span className="w-2 h-2 rounded-full bg-gray-600" />
                                                    {q.category}
                                                </span>
                                                <span>•</span>
                                                <span className="flex items-center gap-1">
                                                    <span className="material-symbols-outlined text-sm">timer</span>
                                                    {q.duration}
                                                </span>
                                            </div>
                                        </div>
                                    </div>

                                    <AnimatePresence>
                                        {expandedQuestion === q.id && (
                                            <motion.div
                                                initial={{ height: 0, opacity: 0 }}
                                                animate={{ height: 'auto', opacity: 1 }}
                                                exit={{ height: 0, opacity: 0 }}
                                                className="border-t border-white/5 bg-black/20"
                                            >
                                                <div className="p-6 md:p-8 grid md:grid-cols-2 gap-8">
                                                    {/* User Answer */}
                                                    <div className="space-y-4">
                                                        <div className="flex items-center gap-2 text-xs font-bold text-gray-500 uppercase tracking-widest">
                                                            <span className="w-2 h-2 rounded-full bg-gray-500"></span>
                                                            Your Response
                                                        </div>
                                                        <div className="p-5 rounded-2xl bg-[#0c1117] border border-white/5 text-gray-300 text-sm leading-relaxed font-mono relative overflow-hidden group/text">
                                                            <div className="absolute top-0 left-0 w-1 h-full bg-gray-700" />
                                                            "{q.userAnswer || "No answer recorded."}"
                                                        </div>
                                                    </div>

                                                    {/* AI Feedback */}
                                                    <div className="space-y-4">
                                                        <div className="flex items-center gap-2 text-xs font-bold text-orange-500 uppercase tracking-widest">
                                                            <span className="w-2 h-2 rounded-full bg-orange-500 animate-pulse"></span>
                                                            AI Analysis
                                                        </div>

                                                        {q.improvements && (
                                                            <div className="p-4 rounded-xl bg-orange-900/10 border border-orange-500/20 flex gap-3 text-orange-100 text-sm">
                                                                <span className="material-symbols-outlined text-orange-400 shrink-0">tips_and_updates</span>
                                                                <p>{q.improvements}</p>
                                                            </div>
                                                        )}

                                                        <div className="p-5 rounded-2xl bg-[#0c1117] border border-orange-900/30 relative overflow-hidden">
                                                            <div className="absolute top-0 left-0 w-1 h-full bg-gradient-to-b from-orange-500 to-amber-600" />
                                                            <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">Optimal Approach</h4>
                                                            <p className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap">
                                                                {q.optimizedAnswer || "Generating optimization..."}
                                                            </p>
                                                        </div>
                                                    </div>
                                                </div>
                                            </motion.div>
                                        )}
                                    </AnimatePresence>
                                </motion.div>
                            ))
                        )}
                    </div>
                </div>
            </main>
        </div>
    );
}
