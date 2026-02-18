/**
 * Analysis View Component - Sci-Fi Cinematic
 * Glass cards, glow inputs, starry buttons
 */

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Briefcase,
    Building2,
    ArrowRight,
    Target,
    Sparkles,
    Loader2,
    FileText,
    CheckCircle2,
    Rocket,
    TrendingUp,
    Zap,
} from 'lucide-react';
import useInterviewStore, { APP_STATES } from '@/store/useInterviewStore';
import PDFDropzone from './PDFDropzone';
import MindmapViewer from './MindmapViewer';
import ReadinessMeter from './ReadinessMeter';

export default function AnalysisView() {
    const [jobTitle, setJobTitle] = useState('');
    const [company, setCompany] = useState('');
    const [resumeBase64, setResumeBase64] = useState(null);
    const [resumeName, setResumeName] = useState(null);

    const {
        appState,
        startCareerAnalysis,
        mindmap,
        readinessScore,
        analysisProgress,
        thinkingLog,
        startInterviewPractice,
    } = useInterviewStore();

    const handleUpload = (base64, fileName) => {
        setResumeBase64(base64);
        setResumeName(fileName);
    };

    const handleAnalyze = () => {
        if (!jobTitle.trim() || !resumeBase64) return;
        startCareerAnalysis(resumeBase64, jobTitle, company || 'a top tech company');
    };

    const isAnalyzing = appState === APP_STATES.ANALYZING;
    const hasResults = appState === APP_STATES.MAP_READY;
    const canAnalyze = jobTitle.trim() && resumeBase64 && !isAnalyzing;

    return (
        <div className="h-full flex flex-col">
            {/* Header */}
            <motion.div
                className="p-6 border-b border-white/5"
                initial={{ opacity: 0, y: -20 }}
                animate={{ opacity: 1, y: 0 }}
            >
                <div className="flex items-center gap-4">
                    <motion.div
                        className="p-3 rounded-xl bg-gradient-to-br from-indigo-500/20 to-violet-500/20"
                        whileHover={{ scale: 1.05, rotate: 5 }}
                    >
                        <Target className="w-6 h-6 text-indigo-400" />
                    </motion.div>
                    <div>
                        <h1 className="text-2xl font-bold text-shine">Career Analysis</h1>
                        <p className="text-sm text-zinc-500 mt-0.5">
                            AI-powered skill mapping and career readiness
                        </p>
                    </div>

                    {resumeName && (
                        <motion.div
                            initial={{ opacity: 0, scale: 0.8 }}
                            animate={{ opacity: 1, scale: 1 }}
                            className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-green-500/10 text-green-400"
                        >
                            <FileText size={12} />
                            Resume Ready
                        </motion.div>
                    )}
                </div>
            </motion.div>

            {/* Main Content */}
            <div className="flex-1 overflow-auto p-6">
                {!hasResults ? (
                    <motion.div
                        className="max-w-2xl mx-auto space-y-6"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                    >
                        {/* Step Indicators */}
                        <div className="flex items-center justify-center gap-2 mb-8">
                            {[1, 2, 3].map((step) => (
                                <div key={step} className="flex items-center">
                                    <motion.div
                                        className={`w-9 h-9 rounded-full flex items-center justify-center text-sm font-semibold transition-all ${(step === 1 && jobTitle) || (step === 2 && resumeBase64)
                                            ? 'bg-gradient-to-br from-green-400 to-emerald-500 text-white shadow-lg shadow-green-500/30'
                                            : step <= 2 ? 'bg-indigo-500/20 text-indigo-400' : 'bg-white/5 text-zinc-500'
                                            }`}
                                        whileHover={{ scale: 1.1 }}
                                    >
                                        {(step === 1 && jobTitle) || (step === 2 && resumeBase64) ? (
                                            <CheckCircle2 className="w-4 h-4" />
                                        ) : step}
                                    </motion.div>
                                    {step < 3 && (
                                        <div className={`w-12 h-0.5 mx-1.5 rounded-full transition-all ${(step === 1 && jobTitle) || (step === 2 && resumeBase64)
                                            ? 'bg-gradient-to-r from-green-400 to-emerald-500'
                                            : 'bg-white/10'
                                            }`} />
                                    )}
                                </div>
                            ))}
                        </div>

                        {/* Step 1: Target */}
                        <motion.div
                            className="glass-card p-5"
                            whileHover={{ scale: 1.005 }}
                        >
                            <div className="flex items-center gap-2 mb-4">
                                <div className="p-2 rounded-lg bg-orange-500/10">
                                    <Rocket className="w-4 h-4 text-orange-400" />
                                </div>
                                <h3 className="font-semibold text-white">Define Your Target</h3>
                            </div>

                            <div className="space-y-4">
                                <div>
                                    <label className="flex items-center gap-2 text-sm text-zinc-400 mb-2">
                                        <Briefcase size={14} />
                                        Target Role <span className="text-red-400">*</span>
                                    </label>
                                    <input
                                        type="text"
                                        value={jobTitle}
                                        onChange={(e) => setJobTitle(e.target.value)}
                                        placeholder="e.g., Senior Software Engineer, ML Engineer"
                                        disabled={isAnalyzing}
                                        className="w-full px-4 py-3 input-glow disabled:opacity-50"
                                    />
                                </div>

                                <div>
                                    <label className="flex items-center gap-2 text-sm text-zinc-400 mb-2">
                                        <Building2 size={14} />
                                        Target Company <span className="text-zinc-600">(optional)</span>
                                    </label>
                                    <input
                                        type="text"
                                        value={company}
                                        onChange={(e) => setCompany(e.target.value)}
                                        placeholder="e.g., Google, Meta, OpenAI"
                                        disabled={isAnalyzing}
                                        className="w-full px-4 py-3 input-glow disabled:opacity-50"
                                    />
                                </div>
                            </div>
                        </motion.div>

                        {/* Step 2: Upload */}
                        <motion.div
                            className="glass-card p-5"
                            whileHover={{ scale: 1.005 }}
                        >
                            <div className="flex items-center gap-2 mb-4">
                                <div className="p-2 rounded-lg bg-orange-500/10">
                                    <FileText className="w-4 h-4 text-orange-400" />
                                </div>
                                <h3 className="font-semibold text-white">Upload Your Resume</h3>
                            </div>

                            <PDFDropzone onUpload={handleUpload} isLoading={isAnalyzing} />
                        </motion.div>

                        {/* Analyze Button */}
                        <div className="flex justify-center pt-2">
                            <motion.button
                                onClick={handleAnalyze}
                                disabled={!canAnalyze}
                                className={`px-8 py-4 rounded-xl font-semibold text-white flex items-center gap-3 ${canAnalyze ? 'btn-starry' : 'bg-white/5 text-zinc-500 cursor-not-allowed'
                                    }`}
                                whileHover={canAnalyze ? { scale: 1.02, y: -2 } : {}}
                                whileTap={canAnalyze ? { scale: 0.98 } : {}}
                            >
                                {isAnalyzing ? (
                                    <>
                                        <Loader2 className="w-5 h-5 animate-spin" />
                                        Analyzing...
                                    </>
                                ) : (
                                    <>
                                        <Sparkles className="w-5 h-5" />
                                        Analyze My Career Fit
                                    </>
                                )}
                            </motion.button>
                        </div>

                        {/* Progress */}
                        <AnimatePresence>
                            {isAnalyzing && (
                                <motion.div
                                    initial={{ opacity: 0, height: 0 }}
                                    animate={{ opacity: 1, height: 'auto' }}
                                    exit={{ opacity: 0, height: 0 }}
                                >
                                    <div className="glass-card p-5">
                                        <div className="flex items-center gap-3 mb-4">
                                            <div className="relative w-10 h-10">
                                                <div className="absolute inset-0 rounded-full border-2 border-orange-500/30 border-t-orange-500 animate-spin" />
                                                <div className="absolute inset-2 rounded-full bg-orange-500/20 flex items-center justify-center">
                                                    <Zap className="w-4 h-4 text-orange-400" />
                                                </div>
                                            </div>
                                            <div>
                                                <p className="text-orange-400 font-medium">{analysisProgress || 'Initializing...'}</p>
                                                <p className="text-xs text-zinc-500">This may take 30-60 seconds</p>
                                            </div>
                                        </div>

                                        <div className="max-h-24 overflow-auto border-t border-white/5 pt-3 space-y-1 font-mono text-xs">
                                            {thinkingLog.slice(-4).map((log, i) => (
                                                <motion.div
                                                    key={i}
                                                    initial={{ opacity: 0, x: -10 }}
                                                    animate={{ opacity: 1, x: 0 }}
                                                    className="text-zinc-500"
                                                >
                                                    <span className="text-zinc-600">[{log.time}]</span> {log.message}
                                                </motion.div>
                                            ))}
                                        </div>
                                    </div>
                                </motion.div>
                            )}
                        </AnimatePresence>
                    </motion.div>
                ) : (
                    <motion.div
                        className="h-full flex flex-col"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                    >
                        {/* Results Header */}
                        <div className="flex items-center justify-between mb-6">
                            <div className="flex items-center gap-4">
                                <motion.div
                                    className="p-3 rounded-xl bg-gradient-to-br from-green-500/20 to-emerald-500/20"
                                    initial={{ rotate: -180, scale: 0 }}
                                    animate={{ rotate: 0, scale: 1 }}
                                    transition={{ type: 'spring', delay: 0.2 }}
                                >
                                    <TrendingUp className="w-6 h-6 text-green-400" />
                                </motion.div>
                                <div>
                                    <h2 className="text-xl font-bold text-shine">Your Skill Map</h2>
                                    <p className="text-sm text-zinc-500">
                                        Targeting <span className="text-indigo-400">{jobTitle}</span>
                                    </p>
                                </div>
                            </div>

                            <motion.button
                                onClick={() => startInterviewPractice()}
                                className="btn-starry px-6 py-3 rounded-xl font-semibold text-white flex items-center gap-2"
                                whileHover={{ scale: 1.02, y: -2 }}
                                whileTap={{ scale: 0.98 }}
                            >
                                Start Practice
                                <ArrowRight className="w-4 h-4" />
                            </motion.button>
                        </div>

                        {/* Mindmap */}
                        <div className="flex-1 glass-card overflow-hidden">
                            <MindmapViewer mindmapCode={mindmap} skillMapping={skillMapping} />
                        </div>
                    </motion.div>
                )}
            </div>
        </div>
    );
}

// Sidebar
export function AnalysisSidebar() {
    const { readinessScore, skillMapping, bridgeRoles, appState, thinkingLog } = useInterviewStore();
    const hasResults = appState === APP_STATES.MAP_READY;
    const isAnalyzing = appState === APP_STATES.ANALYZING;

    if (isAnalyzing) {
        return (
            <div className="space-y-4">
                <div className="text-center py-6">
                    <motion.div
                        className="inline-block w-14 h-14 rounded-full border-2 border-indigo-500/30 border-t-indigo-500"
                        animate={{ rotate: 360 }}
                        transition={{ duration: 1.5, repeat: Infinity, ease: 'linear' }}
                    />
                    <p className="mt-4 text-sm text-indigo-400 font-medium">Analyzing...</p>
                </div>
                <div className="space-y-1">
                    {thinkingLog.slice(-4).map((log, i) => (
                        <p key={i} className="text-xs text-zinc-500 truncate">{log.message}</p>
                    ))}
                </div>
            </div>
        );
    }

    if (!hasResults) {
        return (
            <div className="text-center py-8">
                <div className="w-16 h-16 rounded-2xl bg-white/5 flex items-center justify-center mx-auto mb-4">
                    <Target className="w-7 h-7 text-orange-400/40" />
                </div>
                <p className="text-zinc-400 text-sm font-medium">No Analysis Yet</p>
                <p className="text-zinc-600 text-xs mt-1">Upload your resume to begin</p>
            </div>
        );
    }

    return (
        <div className="space-y-5">
            {/* Readiness */}
            <motion.div
                className="flex justify-center py-2"
                initial={{ scale: 0.5, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ type: 'spring', delay: 0.3 }}
            >
                <ReadinessMeter score={readinessScore} />
            </motion.div>

            {/* Stats */}
            <div className="grid grid-cols-2 gap-2">
                <motion.div className="glass-card p-3 text-center" whileHover={{ scale: 1.02 }}>
                    <p className="text-2xl font-bold text-green-400">{skillMapping?.matched?.length || 0}</p>
                    <p className="text-xs text-zinc-500">Matched</p>
                </motion.div>
                <motion.div className="glass-card p-3 text-center" whileHover={{ scale: 1.02 }}>
                    <p className="text-2xl font-bold text-yellow-400">{skillMapping?.missing?.length || 0}</p>
                    <p className="text-xs text-zinc-500">Gaps</p>
                </motion.div>
            </div>

            {/* Skills */}
            {skillMapping && (
                <div className="space-y-4">
                    {skillMapping.matched?.length > 0 && (
                        <div>
                            <p className="text-xs uppercase text-zinc-500 mb-2 flex items-center gap-1">
                                <CheckCircle2 className="w-3 h-3 text-green-400" />
                                Strengths
                            </p>
                            <div className="flex flex-wrap gap-1.5">
                                {skillMapping.matched.slice(0, 5).map((skill, i) => (
                                    <span key={i} className="text-xs px-2 py-1 rounded-md bg-green-500/10 text-green-400">{skill}</span>
                                ))}
                            </div>
                        </div>
                    )}
                    {skillMapping.missing?.length > 0 && (
                        <div>
                            <p className="text-xs uppercase text-zinc-500 mb-2 flex items-center gap-1">
                                <Target className="w-3 h-3 text-red-400" />
                                To Develop
                            </p>
                            <div className="flex flex-wrap gap-1.5">
                                {skillMapping.missing.slice(0, 5).map((skill, i) => (
                                    <span key={i} className="text-xs px-2 py-1 rounded-md bg-red-500/10 text-red-400">{skill}</span>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
