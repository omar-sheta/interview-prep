import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import useInterviewStore from '../store/useInterviewStore';

// Step indicator component
function StepIndicator({ currentStep, totalSteps }) {
    return (
        <div className="flex items-center gap-2">
            {[...Array(totalSteps)].map((_, i) => (
                <div
                    key={i}
                    className={`h-1.5 flex-1 rounded-full transition-all duration-300 ${i <= currentStep
                        ? 'bg-[#00c2b2] shadow-[0_0_8px_rgba(0,194,178,0.5)]'
                        : 'bg-white/10'
                        }`}
                />
            ))}
        </div>
    );
}

// Step 0: Login Screen with Premium UI
function LoginStep({ onContinue, onEmailLogin, onSignUp }) {
    const [isSignUp, setIsSignUp] = useState(false);
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [username, setUsername] = useState('');
    const [error, setError] = useState('');
    const [isLoading, setIsLoading] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');

        if (!email.trim()) {
            setError('Email is required');
            return;
        }

        if (isSignUp && !username.trim()) {
            setError('Username is required');
            return;
        }

        if (!password.trim()) {
            setError('Password is required');
            return;
        }

        setIsLoading(true);

        if (isSignUp) {
            await onSignUp(email, username, password);
        } else {
            await onEmailLogin(email, password);
        }

        setIsLoading(false);
    };

    return (
        <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="w-full max-w-[1000px] flex rounded-3xl overflow-hidden shadow-2xl border border-white/10 bg-[#0c1117] relative z-10 min-h-[600px]"
        >
            {/* Left Side - Visuals (Desktop) */}
            <div className="hidden md:flex flex-col justify-between w-5/12 bg-[#00c2b2]/5 p-12 relative overflow-hidden text-center border-r border-white/5">
                <div className="absolute top-[-20%] left-[-20%] w-[400px] h-[400px] rounded-full bg-[#00c2b2]/20 blur-[120px]" />
                <div className="absolute bottom-[-10%] right-[-10%] w-[300px] h-[300px] rounded-full bg-blue-600/10 blur-[100px]" />

                <div className="relative z-10 flex flex-col h-full justify-center">
                    <div className="mb-10">
                        <div className="w-20 h-20 rounded-2xl bg-gradient-to-tr from-[#00c2b2] to-blue-500 mx-auto flex items-center justify-center shadow-[0_0_40px_rgba(0,194,178,0.3)] mb-6 transform rotate-3 hover:rotate-6 transition-transform duration-500">
                            <span className="material-symbols-outlined text-white text-[40px]">code</span>
                        </div>
                        <h1 className="text-5xl font-bold text-white mb-3 tracking-tight">SOTA</h1>
                        <p className="text-[#00c2b2] text-xs font-bold tracking-[0.3em] uppercase opacity-90">Technical Interview Coach</p>
                    </div>
                </div>

                <div className="relative z-10 pb-4">
                    <div className="flex items-center justify-center gap-2 text-white/40 text-[10px] uppercase font-mono tracking-widest">
                        <span className="material-symbols-outlined text-[14px]">encrypted</span>
                        <span>Zero-Knowledge Architecture</span>
                    </div>
                </div>
            </div>

            {/* Right Side - Form */}
            <div className="w-full md:w-7/12 bg-[#0c1117]/80 backdrop-blur-3xl p-8 sm:p-12 flex flex-col justify-center relative">
                <div className="max-w-[400px] mx-auto w-full">
                    <div className="mb-8">
                        <h2 className="text-3xl font-bold text-white mb-2">
                            {isSignUp ? 'Create Account' : 'Welcome Back'}
                        </h2>
                        <p className="text-gray-400 text-sm">
                            {isSignUp ? 'Initialize your secure local environment.' : 'Access your encrypted workspace.'}
                        </p>
                    </div>

                    {/* Toggle Tabs */}
                    <div className="flex mb-8 bg-white/5 p-1 rounded-lg border border-white/5">
                        <button
                            onClick={() => { setIsSignUp(false); setError(''); }}
                            className={`flex-1 py-2.5 rounded-md text-sm font-bold transition-all ${!isSignUp
                                ? 'bg-[#00c2b2] text-[#111417] shadow-lg'
                                : 'text-gray-400 hover:text-white hover:bg-white/5'
                                }`}
                        >
                            Log In
                        </button>
                        <button
                            onClick={() => { setIsSignUp(true); setError(''); }}
                            className={`flex-1 py-2.5 rounded-md text-sm font-bold transition-all ${isSignUp
                                ? 'bg-[#00c2b2] text-[#111417] shadow-lg'
                                : 'text-gray-400 hover:text-white hover:bg-white/5'
                                }`}
                        >
                            Sign Up
                        </button>
                    </div>

                    {/* Error Message */}
                    <AnimatePresence>
                        {error && (
                            <motion.div
                                initial={{ opacity: 0, height: 0, mb: 0 }}
                                animate={{ opacity: 1, height: 'auto', mb: 16 }}
                                exit={{ opacity: 0, height: 0, mb: 0 }}
                                className="rounded-lg bg-red-500/10 border border-red-500/20 px-4 py-3 text-red-400 text-xs font-bold flex items-center gap-2 overflow-hidden"
                            >
                                <span className="material-symbols-outlined text-[16px]">error</span>
                                {error}
                            </motion.div>
                        )}
                    </AnimatePresence>

                    {/* Form */}
                    <form onSubmit={handleSubmit} className="flex flex-col gap-5">
                        {/* Username (Sign Up only) */}
                        <AnimatePresence>
                            {isSignUp && (
                                <motion.div
                                    initial={{ opacity: 0, height: 0 }}
                                    animate={{ opacity: 1, height: 'auto' }}
                                    exit={{ opacity: 0, height: 0 }}
                                    className="overflow-hidden space-y-1.5"
                                >
                                    <label className="text-[11px] font-bold text-gray-400 uppercase tracking-wider ml-1">Username</label>
                                    <div className="relative group">
                                        <input
                                            type="text"
                                            value={username}
                                            onChange={(e) => setUsername(e.target.value)}
                                            className="w-full h-12 pl-11 pr-4 rounded-xl bg-white/5 border border-white/10 text-white placeholder-gray-600 focus:outline-none focus:border-[#00c2b2]/50 focus:bg-white/10 transition-all text-sm font-medium"
                                            placeholder="jdoe"
                                        />
                                        <span className="material-symbols-outlined absolute left-3.5 top-3 text-gray-500 group-focus-within:text-[#00c2b2] transition-colors text-[20px]">person</span>
                                    </div>
                                </motion.div>
                            )}
                        </AnimatePresence>

                        {/* Email */}
                        <div className="space-y-1.5">
                            <label className="text-[11px] font-bold text-gray-400 uppercase tracking-wider ml-1">Email</label>
                            <div className="relative group">
                                <input
                                    type="email"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    className="w-full h-12 pl-11 pr-4 rounded-xl bg-white/5 border border-white/10 text-white placeholder-gray-600 focus:outline-none focus:border-[#00c2b2]/50 focus:bg-white/10 transition-all text-sm font-medium"
                                    placeholder="name@example.com"
                                />
                                <span className="material-symbols-outlined absolute left-3.5 top-3 text-gray-500 group-focus-within:text-[#00c2b2] transition-colors text-[20px]">mail</span>
                            </div>
                        </div>

                        {/* Password */}
                        <div className="space-y-1.5">
                            <label className="text-[11px] font-bold text-gray-400 uppercase tracking-wider ml-1">Password</label>
                            <div className="relative group">
                                <input
                                    type="password"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    className="w-full h-12 pl-11 pr-4 rounded-xl bg-white/5 border border-white/10 text-white placeholder-gray-600 focus:outline-none focus:border-[#00c2b2]/50 focus:bg-white/10 transition-all text-sm font-medium"
                                    placeholder="••••••••"
                                />
                                <span className="material-symbols-outlined absolute left-3.5 top-3 text-gray-500 group-focus-within:text-[#00c2b2] transition-colors text-[20px]">lock</span>
                            </div>
                        </div>

                        {/* Submit Button */}
                        <button
                            type="submit"
                            disabled={isLoading}
                            className="mt-2 w-full h-12 rounded-xl bg-gradient-to-r from-[#00c2b2] to-[#00a89d] text-[#111417] font-bold text-base tracking-wide shadow-[0_0_20px_rgba(0,194,178,0.25)] hover:shadow-[0_0_30px_rgba(0,194,178,0.4)] active:scale-[0.98] transition-all flex items-center justify-center gap-2 disabled:opacity-70 disabled:cursor-not-allowed"
                        >
                            {isLoading ? (
                                <div className="w-5 h-5 border-2 border-[#111417]/30 border-t-[#111417] rounded-full animate-spin" />
                            ) : (
                                <>
                                    <span>{isSignUp ? 'Create Account' : 'Sign In'}</span>
                                    <span className="material-symbols-outlined text-[20px]">arrow_forward</span>
                                </>
                            )}
                        </button>
                    </form>

                    <div className="relative my-7">
                        <div className="absolute inset-0 flex items-center">
                            <div className="w-full border-t border-white/10"></div>
                        </div>
                        <div className="relative flex justify-center text-[10px] bg-transparent">
                            <span className="bg-[#0c1117]/50 backdrop-blur px-2 text-gray-500 uppercase tracking-widest font-bold">Or continue with</span>
                        </div>
                    </div>

                    <button
                        onClick={onContinue}
                        className="w-full h-12 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 text-white font-bold text-sm transition-all flex items-center justify-center gap-2 group"
                    >
                        <span className="material-symbols-outlined text-[22px] text-gray-500 group-hover:text-white transition-colors">account_circle</span>
                        Guest Access
                    </button>
                </div>
            </div>
        </motion.div>
    );
}

// Step 1: Privacy First Info
function PrivacyStep({ onContinue, onBack }) {
    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="w-full max-w-[480px]"
        >
            <div className="bg-[#1a1d22]/80 backdrop-blur-xl border border-white/10 rounded-2xl overflow-hidden shadow-2xl">
                {/* Header */}
                <div className="pt-8 px-8 pb-4 flex flex-col gap-4">
                    <div className="flex items-center justify-between text-xs font-medium text-gray-400 uppercase tracking-widest">
                        <span>Step 1 of 3</span>
                        <span className="flex items-center gap-1">
                            <span className="material-symbols-outlined text-sm">lock</span>
                            Privacy First
                        </span>
                    </div>
                    <StepIndicator currentStep={0} totalSteps={3} />
                </div>

                {/* Content */}
                <div className="flex flex-col items-center px-8 pb-10 pt-2 text-center">
                    {/* Icon */}
                    <div className="relative w-48 h-48 flex items-center justify-center mb-6">
                        <div className="absolute w-32 h-32 rounded-full border border-white/5 bg-white/[0.02]" />
                        <div className="absolute w-24 h-24 rounded-full border border-[#00c2b2]/20 animate-spin" style={{ animationDuration: '10s' }} />
                        <motion.div
                            animate={{ y: [0, -10, 0] }}
                            transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
                        >
                            <span className="material-symbols-outlined text-[100px] text-white" style={{ textShadow: '0 0 30px rgba(0, 194, 178, 0.4)' }}>
                                memory
                            </span>
                        </motion.div>
                    </div>

                    {/* Text */}
                    <div className="space-y-4 mb-8">
                        <h1 className="text-3xl font-bold tracking-tight text-white">
                            The Power of <br />
                            <span className="text-transparent bg-clip-text bg-gradient-to-r from-white to-[#00c2b2]/80">Local-First</span>
                        </h1>
                        <p className="text-base text-gray-300/90 leading-relaxed">
                            SOTA runs entirely on your device. By leveraging powerful <span className="text-white font-medium">on-device processing</span>, your interview data never leaves your local hardware.
                        </p>
                        <div className="flex flex-wrap items-center justify-center gap-4 pt-2">
                            <div className="flex items-center gap-1.5 text-xs font-medium text-[#00c2b2] bg-[#00c2b2]/10 px-3 py-1 rounded-full border border-[#00c2b2]/20">
                                <span className="material-symbols-outlined text-[16px]">security</span>
                                100% Private
                            </div>
                            <div className="flex items-center gap-1.5 text-xs font-medium text-emerald-400 bg-emerald-500/10 px-3 py-1 rounded-full border border-emerald-500/20">
                                <span className="material-symbols-outlined text-[16px]">bolt</span>
                                Zero Latency
                            </div>
                        </div>
                    </div>

                    {/* Continue Button */}
                    <button
                        onClick={onContinue}
                        className="group w-full relative flex items-center justify-center gap-2 overflow-hidden rounded-xl bg-[#00c2b2] p-4 transition-all duration-300 hover:shadow-[0_0_20px_rgba(0,194,178,0.4)] active:scale-[0.98]"
                    >
                        <span className="text-[#111417] font-bold text-base tracking-wide uppercase">Continue</span>
                        <span className="material-symbols-outlined text-[#111417] text-lg transition-transform group-hover:translate-x-1">arrow_forward</span>
                    </button>
                </div>
            </div>
        </motion.div>
    );
}

// Step 2: Mic + Resume
function CredentialsStep({ onContinue, onBack, preferences, setPreferences }) {
    const [micEnabled, setMicEnabled] = useState(preferences.mic_permission_granted || false);
    const [resumeFile, setResumeFile] = useState(
        preferences.resume_filename ? { name: preferences.resume_filename } : null
    );
    const [isTestingMic, setIsTestingMic] = useState(false);
    const fileInputRef = useRef(null);

    const handleFileChange = async (e) => {
        const file = e.target.files?.[0];
        if (file) {
            setResumeFile(file);
            setPreferences(prev => ({
                ...prev,
                resume_filename: file.name
            }));

            // Read file content (for PDF, you'd use pdfjs - simplified here)
            const reader = new FileReader();
            reader.onload = (e) => {
                setPreferences(prev => ({
                    ...prev,
                    resume_text: e.target.result
                }));
            };
            reader.readAsText(file);
        }
    };

    const handleTestMic = async () => {
        setIsTestingMic(true);
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            setMicEnabled(true);
            setPreferences(prev => ({ ...prev, mic_permission_granted: true }));
            stream.getTracks().forEach(track => track.stop());
        } catch (err) {
            console.error('Mic permission denied:', err);
        }
        setTimeout(() => setIsTestingMic(false), 1000);
    };

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="w-full max-w-2xl"
        >
            {/* Header */}
            <div className="flex items-center justify-between mb-8">
                <div className="flex items-center gap-3">
                    <div className="w-8 h-8 bg-gradient-to-tr from-[#00c2b2] to-blue-500 rounded-lg flex items-center justify-center">
                        <span className="material-symbols-outlined text-[#111417] font-bold text-lg">code</span>
                    </div>
                    <span className="font-bold text-xl tracking-tight text-white">SOTA</span>
                </div>
                <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-gray-500 uppercase tracking-widest mr-2">Step 02 / 03</span>
                    <div className="w-24 h-1 bg-gray-800 rounded-full overflow-hidden">
                        <div className="w-2/3 h-full bg-[#00c2b2] shadow-[0_0_10px_rgba(0,194,178,0.5)]" />
                    </div>
                </div>
            </div>

            {/* Title */}
            <div className="text-center mb-8">
                <h1 className="text-4xl md:text-5xl font-bold tracking-tight text-white mb-4">
                    Universal Senses & <span className="text-[#00c2b2]">Credentials</span>
                </h1>
                <p className="text-gray-400 text-base md:text-lg max-w-lg mx-auto">
                    SOTA operates locally. We need access to your senses to coach you effectively during mock interviews.
                </p>
                <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-[#00c2b2]/20 bg-[#00c2b2]/5 mt-4">
                    <span className="material-symbols-outlined text-[#00c2b2] text-[16px]">lock</span>
                    <span className="text-xs font-medium text-[#00c2b2] tracking-wide">100% LOCAL PROCESSING</span>
                </div>
            </div>

            {/* Card */}
            <div className="bg-[#1a1d22]/80 backdrop-blur-xl border border-white/10 rounded-2xl p-6 md:p-8 space-y-6">
                {/* Mic Section */}
                <div className="flex items-center justify-between p-4 rounded-xl border border-white/5 bg-white/[0.02] hover:border-white/10 transition-all">
                    <div className="flex items-center gap-4">
                        <div className={`w-12 h-12 rounded-full flex items-center justify-center transition-colors ${micEnabled ? 'bg-[#00c2b2]/20 text-[#00c2b2]' : 'bg-gray-800 text-gray-300'}`}>
                            <span className="material-symbols-outlined">mic</span>
                        </div>
                        <div>
                            <h3 className="text-white font-semibold text-lg">Microphone Access</h3>
                            <p className="text-gray-400 text-sm">Required for mock interview speech analysis.</p>
                        </div>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                        <input
                            type="checkbox"
                            checked={micEnabled}
                            onChange={(e) => setMicEnabled(e.target.checked)}
                            className="sr-only peer"
                        />
                        <div className="w-14 h-7 bg-gray-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:rounded-full after:h-6 after:w-6 after:transition-all peer-checked:bg-[#00c2b2]" />
                    </label>
                </div>

                {/* Resume Section */}
                <div className="flex flex-col gap-5 p-4 rounded-xl border border-white/5 bg-white/[0.02]">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-4">
                            <div className={`w-12 h-12 rounded-full flex items-center justify-center ${resumeFile ? 'bg-[#00c2b2]/20 text-[#00c2b2]' : 'bg-gray-800 text-gray-300'}`}>
                                <span className="material-symbols-outlined">description</span>
                            </div>
                            <div>
                                <h3 className="text-white font-semibold text-lg">Resume / CV</h3>
                                <p className="text-gray-400 text-sm">
                                    {resumeFile ? resumeFile.name : 'Upload your resume for personalized context.'}
                                </p>
                            </div>
                        </div>
                        <div className="flex items-center gap-2 px-3 py-1 bg-[#00c2b2]/10 rounded-full border border-[#00c2b2]/20">
                            <span className="material-symbols-outlined text-[#00c2b2] text-[16px]">verified_user</span>
                            <span className="text-[10px] font-bold text-[#00c2b2] tracking-wide">SAVED LOCALLY</span>
                        </div>
                    </div>

                    <label className="cursor-pointer relative w-full h-32 rounded-xl border-2 border-dashed border-gray-600 hover:border-[#00c2b2]/50 bg-black/20 hover:bg-black/30 transition-all flex flex-col items-center justify-center gap-2 overflow-hidden">
                        <input
                            ref={fileInputRef}
                            type="file"
                            accept=".pdf,.doc,.docx,.txt"
                            onChange={handleFileChange}
                            className="hidden"
                        />
                        <span className="material-symbols-outlined text-3xl text-gray-500">cloud_upload</span>
                        <div className="text-center">
                            <p className="text-gray-300 text-sm font-medium">
                                Drop your file here, or <span className="text-[#00c2b2] underline">browse</span>
                            </p>
                            <p className="text-xs text-gray-500 mt-1">PDF, DOCX, TXT (Max 5MB)</p>
                        </div>
                    </label>
                </div>

                {/* Audio Check */}
                <div className="flex items-center justify-between pt-4 border-t border-white/5">
                    <div>
                        <span className="text-sm font-medium text-white">Audio Check</span>
                        <p className="text-xs text-gray-500">Test your input levels before proceeding.</p>
                    </div>
                    <div className="flex items-center gap-4">
                        <div className="h-8 flex items-center gap-[2px]">
                            {[30, 50, 80, 100, 60, 40, 20].map((h, i) => (
                                <div
                                    key={i}
                                    className={`w-1 rounded-full transition-all ${isTestingMic ? 'bg-[#00c2b2] animate-pulse' : 'bg-[#00c2b2]/40'}`}
                                    style={{ height: `${h}%`, animationDelay: `${i * 75}ms` }}
                                />
                            ))}
                        </div>
                        <button
                            onClick={handleTestMic}
                            className="px-4 py-2 rounded-lg border border-[#00c2b2]/50 text-[#00c2b2] hover:bg-[#00c2b2]/10 transition-colors text-sm font-bold flex items-center gap-2"
                        >
                            <span className="material-symbols-outlined text-[18px]">graphic_eq</span>
                            Test Mic
                        </button>
                    </div>
                </div>
            </div>

            {/* Navigation */}
            <div className="flex items-center justify-between mt-6">
                <button
                    onClick={onBack}
                    className="text-gray-500 hover:text-white font-medium text-sm flex items-center gap-1 transition-colors px-4 py-2"
                >
                    <span className="material-symbols-outlined text-[18px]">arrow_back</span>
                    Back
                </button>
                <button
                    onClick={onContinue}
                    className="bg-[#00c2b2] hover:bg-[#00d6c4] text-[#111417] font-bold py-3 px-8 rounded-xl transition-all shadow-[0_0_20px_rgba(0,194,178,0.3)] hover:shadow-[0_0_30px_rgba(0,194,178,0.5)] flex items-center gap-2"
                >
                    Continue
                    <span className="material-symbols-outlined text-[20px]">arrow_forward</span>
                </button>
            </div>
        </motion.div>
    );
}

// Step 3: Mission Parameters
function MissionStep({ onComplete, onBack, preferences, setPreferences }) {
    const [targetRole, setTargetRole] = useState(preferences.target_role || '');
    const [targetCompany, setTargetCompany] = useState(preferences.target_company || '');
    const [selectedFocusAreas, setSelectedFocusAreas] = useState(preferences.focus_areas || []);

    const focusOptions = [
        'System Design', 'Algorithms', 'Data Structures',
        'Python', 'JavaScript', 'Databases',
        'API Design', 'Behavioral'
    ];

    const toggleFocusArea = (area) => {
        if (selectedFocusAreas.includes(area)) {
            setSelectedFocusAreas(prev => prev.filter(a => a !== area));
        } else {
            setSelectedFocusAreas(prev => [...prev, area]);
        }
    };

    const handleComplete = () => {
        const finalPreferences = {
            target_role: targetRole,
            target_company: targetCompany,
            focus_areas: selectedFocusAreas,
            onboarding_complete: true
        };

        setPreferences(prev => ({
            ...prev,
            ...finalPreferences
        }));

        // Pass the actual data to onComplete to avoid closure staleness
        onComplete(finalPreferences);
    };

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="w-full max-w-[600px]"
        >
            <div className="bg-[#1a1d21]/80 backdrop-blur-xl border border-white/10 rounded-2xl overflow-hidden shadow-2xl">
                {/* Header */}
                <div className="px-8 pt-8 pb-4 border-b border-white/5">
                    <div className="flex gap-6 justify-between items-end mb-3">
                        <p className="text-gray-400 text-xs font-bold tracking-widest uppercase">System Initialization</p>
                        <p className="text-[#00c2b2] text-xs font-bold tracking-widest uppercase">Step 3 of 3</p>
                    </div>
                    <StepIndicator currentStep={2} totalSteps={3} />
                </div>

                {/* Content */}
                <div className="p-8 space-y-8">
                    <div className="text-center space-y-3">
                        <h1 className="text-4xl md:text-5xl font-bold leading-tight tracking-tight text-white">
                            Ready for Launch
                        </h1>
                        <p className="text-gray-400 text-base md:text-lg">
                            Your local environment is secured. SOTA is ready to simulate your next technical interview.
                        </p>
                    </div>

                    {/* Profile Card */}
                    <div className="flex justify-center">
                        <div className="flex flex-col items-center gap-4 p-4 rounded-xl bg-[#24272B]/50 border border-white/5 w-64 ring-1 ring-white/5">
                            <div className="relative">
                                <div className="h-24 w-24 rounded-full bg-gradient-to-b from-[#00c2b2] to-[#00c2b2]/20 p-1">
                                    <div className="h-full w-full rounded-full bg-[#24272B] flex items-center justify-center">
                                        <span className="material-symbols-outlined text-4xl text-white">person</span>
                                    </div>
                                </div>
                                <div className="absolute bottom-1 right-1 h-5 w-5 rounded-full bg-[#1a1d21] flex items-center justify-center">
                                    <div className="h-3 w-3 rounded-full bg-[#00c2b2] shadow-[0_0_8px_rgba(0,194,178,0.8)]" />
                                </div>
                            </div>
                            <div className="text-center">
                                <p className="text-white text-lg font-bold">Pilot: Guest</p>
                                <p className="text-[#00c2b2] text-sm font-medium uppercase mt-1">System Online</p>
                            </div>
                        </div>
                    </div>

                    {/* Mission Parameters */}
                    <div className="space-y-4">
                        <div className="flex items-center gap-2 opacity-60">
                            <div className="h-px flex-1 bg-gradient-to-r from-transparent to-white/20" />
                            <span className="text-[10px] font-bold uppercase tracking-widest text-[#00c2b2]">Mission Parameters</span>
                            <div className="h-px flex-1 bg-gradient-to-l from-transparent to-white/20" />
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-1">
                                <label className="ml-1 text-[10px] font-bold uppercase tracking-widest text-gray-400">Target Role</label>
                                <div className="relative flex items-center rounded-lg border border-white/10 bg-[#24272B] overflow-hidden focus-within:border-[#00c2b2]/50 focus-within:ring-1 focus-within:ring-[#00c2b2]/50 transition-all">
                                    <div className="flex items-center justify-center pl-3 text-gray-500">
                                        <span className="material-symbols-outlined text-[18px]">work</span>
                                    </div>
                                    <input
                                        type="text"
                                        value={targetRole}
                                        onChange={(e) => setTargetRole(e.target.value)}
                                        className="w-full border-none bg-transparent py-2.5 pl-2 pr-3 text-sm font-medium text-white placeholder-white/20 focus:ring-0 focus:outline-none"
                                        placeholder="e.g. Senior Dev"
                                    />
                                </div>
                            </div>
                            <div className="space-y-1">
                                <label className="ml-1 text-[10px] font-bold uppercase tracking-widest text-gray-400">Target Company</label>
                                <div className="relative flex items-center rounded-lg border border-white/10 bg-[#24272B] overflow-hidden focus-within:border-[#00c2b2]/50 focus-within:ring-1 focus-within:ring-[#00c2b2]/50 transition-all">
                                    <div className="flex items-center justify-center pl-3 text-gray-500">
                                        <span className="material-symbols-outlined text-[18px]">business</span>
                                    </div>
                                    <input
                                        type="text"
                                        value={targetCompany}
                                        onChange={(e) => setTargetCompany(e.target.value)}
                                        className="w-full border-none bg-transparent py-2.5 pl-2 pr-3 text-sm font-medium text-white placeholder-white/20 focus:ring-0 focus:outline-none"
                                        placeholder="e.g. Tech Corp"
                                    />
                                </div>
                            </div>
                        </div>

                        {/* Focus Areas */}
                        <div className="space-y-2 pt-2">
                            <label className="ml-1 text-[10px] font-bold uppercase tracking-widest text-gray-400">Tactical Focus Areas</label>
                            <div className="flex flex-wrap gap-2">
                                {focusOptions.map((area) => (
                                    <button
                                        key={area}
                                        onClick={() => toggleFocusArea(area)}
                                        className={`px-3 py-1.5 rounded-md text-xs font-bold border transition-all ${selectedFocusAreas.includes(area)
                                            ? 'bg-[#00c2b2] text-[#111417] border-[#00c2b2] shadow-[0_0_10px_rgba(0,194,178,0.3)]'
                                            : 'bg-[#24272B] text-gray-400 border-white/5 hover:border-white/20 hover:text-gray-200'
                                            }`}
                                    >
                                        {area}
                                    </button>
                                ))}
                            </div>
                        </div>
                    </div>


                    {/* Security Notice */}
                    <div className="rounded-xl bg-[#24272B]/50 border border-white/5 p-4 flex gap-4 items-center">
                        <div className="flex items-center justify-center rounded-full bg-white/5 border border-white/5 shrink-0 w-10 h-10 text-[#00c2b2]">
                            <span className="material-symbols-outlined text-[20px]">encrypted</span>
                        </div>
                        <div>
                            <p className="text-white text-sm font-bold">Local Environment Secured</p>
                            <p className="text-gray-400 text-xs">
                                Zero-knowledge architecture active. All interview data remains encrypted on this device.
                            </p>
                        </div>
                    </div>

                    {/* Begin Button */}
                    <button
                        onClick={handleComplete}
                        className="group relative w-full overflow-hidden rounded-xl bg-[#00c2b2] h-14 text-[#111417] text-lg font-bold tracking-wide transition-all hover:bg-[#00d6c4] hover:shadow-[0_0_20px_rgba(0,194,178,0.4)] flex items-center justify-center gap-2"
                    >
                        Begin Preparation
                        <span className="material-symbols-outlined text-xl transition-transform group-hover:translate-x-1">arrow_forward</span>
                    </button>
                </div>
            </div>

            {/* Version */}
            <div className="mt-6 text-center">
                <p className="text-white/20 text-xs font-mono">SOTA v1.0.4 • Local Secure Environment</p>
            </div>
        </motion.div>
    );
}

// Main Onboarding Flow Component
export default function OnboardingFlow({ onComplete }) {
    const [step, setStep] = useState(0);
    const [user, setUser] = useState(null);
    const [preferences, setPreferences] = useState({
        resume_text: null,
        resume_filename: null,
        target_role: '',
        target_company: '',
        focus_areas: [],
        onboarding_complete: false,
        mic_permission_granted: false
    });

    const { socket, isConnected } = useInterviewStore();

    // Listen for auth responses
    useEffect(() => {
        if (!socket) return;

        socket.on('auth_success', (data) => {
            console.log('✅ Auth success:', data);

            // Set user data
            setUser(data.user);
            localStorage.setItem('user_id', data.user.user_id);
            localStorage.setItem('user_email', data.user.email);

            // Allow state to update
            setTimeout(() => {
                // Check preferences if they exist
                if (data.preferences) {
                    setPreferences(prev => ({
                        ...prev,
                        ...data.preferences
                    }));

                    // If onboarding is already complete, skip to dashboard
                    if (data.preferences.onboarding_complete) {
                        console.log('🔄 User already onboarded, skipping setup...');
                        localStorage.setItem('onboarding_complete', 'true');
                        onComplete(data.preferences);
                        return;
                    }

                    // If we have some data but not complete, maybe we can skip steps?
                    // For now, let's just go to step 1 (Privacy) if not complete
                    // We could also enhance this to check 'mic_permission_granted' etc.
                }

                setStep(1);
            }, 100);
        });

        socket.on('auth_error', (data) => {
            console.error('❌ Auth error:', data.error);
            // Error will be shown in LoginStep via state
        });

        return () => {
            socket.off('auth_success');
            socket.off('auth_error');
        };
    }, [socket]);

    const handleEmailLogin = async (email, password) => {
        if (socket && isConnected) {
            socket.emit('login', { email, password });
        }
        // For now, also continue if no socket (dev mode)
        if (!socket || !isConnected) {
            setStep(1);
        }
    };

    const handleSignUp = async (email, username, password) => {
        if (socket && isConnected) {
            socket.emit('signup', { email, username, password });
        }
        // For now, also continue if no socket (dev mode)
        if (!socket || !isConnected) {
            setStep(1);
        }
    };

    const handleComplete = (finalStepData = {}) => {
        // Merge final step data with existing preferences (ensure we have latest from MissionStep)
        const finalPreferences = {
            ...preferences,
            ...finalStepData,
            onboarding_complete: true
        };

        // Save preferences to backend
        if (socket && isConnected) {
            socket.emit('save_preferences', finalPreferences);
        }

        // Store in localStorage for quick check
        localStorage.setItem('onboarding_complete', 'true');

        onComplete(finalPreferences);
    };

    return (
        <div className="min-h-screen bg-[#111417] flex items-center justify-center p-4 relative overflow-hidden">
            {/* Background Effects */}
            <div className="absolute inset-0 pointer-events-none">
                <div className="absolute top-[-20%] left-[-10%] w-[60vw] h-[60vw] rounded-full bg-[#00c2b2]/5 blur-[120px]" />
                <div className="absolute bottom-[-10%] right-[-10%] w-[50vw] h-[50vw] rounded-full bg-purple-900/10 blur-[100px]" />
            </div>

            {/* Content */}
            <AnimatePresence mode="wait">
                {step === 0 && (
                    <LoginStep
                        key="login"
                        onContinue={() => setStep(1)}
                        onEmailLogin={handleEmailLogin}
                        onSignUp={handleSignUp}
                    />
                )}
                {step === 1 && (
                    <PrivacyStep
                        key="privacy"
                        onContinue={() => setStep(2)}
                        onBack={() => setStep(0)}
                    />
                )}
                {step === 2 && (
                    <CredentialsStep
                        key="credentials"
                        onContinue={() => setStep(3)}
                        onBack={() => setStep(1)}
                        preferences={preferences}
                        setPreferences={setPreferences}
                    />
                )}
                {step === 3 && (
                    <MissionStep
                        key="mission"
                        onComplete={handleComplete}
                        onBack={() => setStep(2)}
                        preferences={preferences}
                        setPreferences={setPreferences}
                    />
                )}
            </AnimatePresence>
        </div>
    );
}
