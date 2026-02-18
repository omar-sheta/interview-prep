/**
 * Command Center - Technical Practice Hub
 * Modern Minimalistic Redesign
 */

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import useInterviewStore from '@/store/useInterviewStore';
import PDFDropzone from './PDFDropzone';
import MindmapViewer from './MindmapViewer';

export default function CommandCenter() {
    const navigate = useNavigate();
    const {
        appState,
        startCareerAnalysis,
        mindmap,
        skillMapping,
        readinessScore,
        analysisProgress,
        startInterviewPractice,
        targetRole,
        targetCompany,
        resumeData
    } = useInterviewStore();

    const [roleDesignation, setRoleDesignation] = useState(targetRole || '');
    const [targetEntity, setTargetEntity] = useState(targetCompany || '');

    // Track both uploaded resume and saved resume
    const [resumeBase64, setResumeBase64] = useState(null);
    const [resumeName, setResumeName] = useState(resumeData ? 'Existing Resume' : null);
    const [hasSavedResume, setHasSavedResume] = useState(false);

    // Check for saved preferences on mount and sync state
    useEffect(() => {
        if (targetRole) setRoleDesignation(targetRole);
        if (targetCompany) setTargetEntity(targetCompany);
        if (resumeData) {
            setResumeName('Existing Resume');
            setHasSavedResume(true);
        }
    }, [targetRole, targetCompany, resumeData]);

    const handleUpload = (base64, fileName) => {
        setResumeBase64(base64);
        setResumeName(fileName);
    };

    const handleInitialize = () => {
        // Allow starting with either a new upload OR saved preferences
        if (!roleDesignation.trim() || (!resumeBase64 && !hasSavedResume)) return;

        // If user uploaded new resume, use it; otherwise use saved preferences
        if (resumeBase64) {
            startCareerAnalysis(resumeBase64, roleDesignation, targetEntity || 'Tech Company');
        } else {
            // Use saved preferences - backend will load from database
            startCareerAnalysis(null, roleDesignation, targetEntity || 'Tech Company');
        }
    };

    const isAnalyzing = appState === 'ANALYZING';
    const hasResults = appState === 'MAP_READY';
    const canStart = roleDesignation.trim() && (resumeBase64 || hasSavedResume) && !isAnalyzing;

    return (
        <div className="min-h-screen bg-[#0c1117] text-white">
            {/* Minimal Header */}
            <header className="fixed top-0 w-full z-50 bg-[#0c1117]/80 backdrop-blur-md border-b border-white/5">
                <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
                    <div className="flex items-center gap-3 cursor-pointer" onClick={() => navigate('/')}>
                        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#00c2b2] to-teal-700 flex items-center justify-center">
                            <span className="material-symbols-outlined text-white text-lg">terminal</span>
                        </div>
                        <span className="font-bold text-lg tracking-tight">SOTA <span className="text-gray-600 font-normal">Practice</span></span>
                    </div>
                    <div className="flex items-center gap-4">
                        <button className="text-sm font-medium text-gray-400 hover:text-white transition-colors">
                            Documentation
                        </button>
                        <div className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center">
                            <span className="material-symbols-outlined text-sm">person</span>
                        </div>
                    </div>
                </div>
            </header>

            {/* Main Content */}
            <main className="pt-24 pb-12 max-w-7xl mx-auto px-6">

                {/* Page Title */}
                <div className="mb-8">
                    <h1 className="text-3xl font-bold tracking-tight mb-2">Practice Configuration</h1>
                    <p className="text-gray-400">Configure your simulation parameters or resume a previous session.</p>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">

                    {/* Left Panel: Configuration */}
                    <div className="lg:col-span-4 space-y-6">
                        {/* Configuration Card */}
                        <div className="bg-[#161b22] border border-white/5 rounded-2xl p-6">
                            <div className="flex items-center gap-2 mb-6 text-[#00c2b2]">
                                <span className="material-symbols-outlined text-sm">tune</span>
                                <span className="text-xs font-bold uppercase tracking-wider">Parameters</span>
                            </div>

                            <div className="space-y-5">
                                <div className="space-y-2">
                                    <label className="text-xs font-medium text-gray-400 uppercase tracking-wide">Target Role</label>
                                    <input
                                        type="text"
                                        value={roleDesignation}
                                        onChange={(e) => setRoleDesignation(e.target.value)}
                                        disabled={isAnalyzing}
                                        className="w-full bg-[#0d1117] border border-white/10 rounded-xl px-4 py-3 text-sm focus:border-[#00c2b2] focus:ring-1 focus:ring-[#00c2b2] focus:outline-none transition-all placeholder:text-gray-700"
                                        placeholder="e.g. Senior Frontend Engineer"
                                    />
                                </div>

                                <div className="space-y-2">
                                    <label className="text-xs font-medium text-gray-400 uppercase tracking-wide">Target Company</label>
                                    <input
                                        type="text"
                                        value={targetEntity}
                                        onChange={(e) => setTargetEntity(e.target.value)}
                                        disabled={isAnalyzing}
                                        className="w-full bg-[#0d1117] border border-white/10 rounded-xl px-4 py-3 text-sm focus:border-[#00c2b2] focus:ring-1 focus:ring-[#00c2b2] focus:outline-none transition-all placeholder:text-gray-700"
                                        placeholder="e.g. Google, Meta"
                                    />
                                </div>

                                <div className="h-px w-full bg-white/5 my-2" />

                                <div className="space-y-2">
                                    <label className="text-xs font-medium text-gray-400 uppercase tracking-wide">Reference Material (Resume)</label>
                                    <PDFDropzone onUpload={handleUpload} isLoading={isAnalyzing} />
                                    {resumeName && (
                                        <div className="flex items-center gap-2 text-xs text-[#00c2b2] bg-[#00c2b2]/5 p-2 rounded-lg border border-[#00c2b2]/10">
                                            <span className="material-symbols-outlined text-sm">description</span>
                                            <span className="truncate">{resumeName}</span>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>

                        {/* Readiness Score (Compact) */}
                        {hasResults && (
                            <div className="bg-[#161b22] border border-white/5 rounded-2xl p-6">
                                <div className="flex items-center justify-between mb-4">
                                    <span className="text-xs font-bold uppercase tracking-wider text-gray-500">Readiness Score</span>
                                    <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${readinessScore >= 0.8 ? 'bg-green-500/10 text-green-400' : 'bg-amber-500/10 text-amber-400'}`}>
                                        {readinessScore >= 0.8 ? 'HIGH' : 'MODERATE'}
                                    </span>
                                </div>
                                <div className="flex items-end gap-2">
                                    <span className="text-4xl font-bold text-white">{Math.round(readinessScore * 100)}%</span>
                                    <span className="text-sm text-gray-500 mb-1.5">match probability</span>
                                </div>
                                <div className="w-full h-1.5 bg-white/10 rounded-full mt-4 overflow-hidden">
                                    <motion.div
                                        initial={{ width: 0 }}
                                        animate={{ width: `${readinessScore * 100}%` }}
                                        className="h-full bg-[#00c2b2]"
                                    />
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Right Panel: Visualization & Action */}
                    <div className="lg:col-span-8 flex flex-col gap-6">
                        {/* Visualization Area */}
                        <div className="flex-1 bg-[#161b22] border border-white/5 rounded-2xl overflow-hidden min-h-[500px] relative">
                            {hasResults && mindmap ? (
                                <MindmapViewer mindmapCode={mindmap} skillMapping={skillMapping} />
                            ) : (
                                <div className="absolute inset-0 flex flex-col items-center justify-center p-8 text-center bg-grid-pattern">
                                    <div className="w-20 h-20 bg-gradient-to-b from-white/5 to-transparent rounded-full flex items-center justify-center mb-6 border border-white/5">
                                        <span className={`material-symbols-outlined text-3xl ${isAnalyzing ? 'animate-spin text-[#00c2b2]' : 'text-gray-600'}`}>
                                            {isAnalyzing ? 'sync' : 'hub'}
                                        </span>
                                    </div>
                                    <h3 className="text-xl font-bold text-white mb-2">
                                        {isAnalyzing ? 'Analyzing Career Profile...' : 'Knowledge Topology Empty'}
                                    </h3>
                                    <p className="text-gray-400 max-w-md mx-auto">
                                        {isAnalyzing
                                            ? analysisProgress || "Processing your resume against target requirements..."
                                            : "Upload your resume and define a target role to generate a personalized knowledge graph and gap analysis."
                                        }
                                    </p>
                                </div>
                            )}
                        </div>

                        {/* Action Bar */}
                        <div className="flex items-center justify-between bg-[#161b22] border border-white/5 rounded-2xl p-4">
                            <div className="flex items-center gap-3 px-2">
                                {hasResults ? (
                                    <>
                                        <span className="flex h-2 w-2 rounded-full bg-green-500"></span>
                                        <span className="text-sm font-medium text-gray-300">Analysis Ready</span>
                                    </>
                                ) : (
                                    <>
                                        <span className="flex h-2 w-2 rounded-full bg-gray-600"></span>
                                        <span className="text-sm font-medium text-gray-500">Awaiting Configuration</span>
                                    </>
                                )}
                            </div>

                            <div className="flex gap-3">
                                {hasResults && (
                                    <button
                                        onClick={handleInitialize}
                                        className="px-4 py-2 text-sm font-medium text-gray-400 hover:text-white transition-colors"
                                    >
                                        Re-Analyze
                                    </button>
                                )}
                                <button
                                    onClick={hasResults ? () => startInterviewPractice() : handleInitialize}
                                    disabled={!canStart && !hasResults}
                                    className={`
                                        px-8 py-3 rounded-xl font-bold flex items-center gap-2 transition-all
                                        ${(!canStart && !hasResults)
                                            ? 'bg-white/5 text-gray-500 cursor-not-allowed'
                                            : 'bg-[#00c2b2] hover:bg-[#00d6c4] text-[#111417] shadow-lg shadow-[#00c2b2]/20 hover:shadow-[#00c2b2]/40'
                                        }
                                    `}
                                >
                                    {isAnalyzing ? (
                                        <>
                                            <span className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
                                            <span>Processing</span>
                                        </>
                                    ) : hasResults ? (
                                        <>
                                            <span className="material-symbols-outlined text-xl">play_arrow</span>
                                            <span>Start Practice</span>
                                        </>
                                    ) : (
                                        <>
                                            <span className="material-symbols-outlined text-xl">rocket_launch</span>
                                            <span>Initialize Analysis</span>
                                        </>
                                    )}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </main>
        </div>
    );
}
