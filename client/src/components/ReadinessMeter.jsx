
import { motion } from 'framer-motion';
import { Check, ShieldCheck } from 'lucide-react';

export default function ReadinessMeter({ score = 72 }) {
    // Circle config
    const size = 280;
    const strokeWidth = 24;
    const radius = (size - strokeWidth) / 2;
    const circumference = 2 * Math.PI * radius;
    const progress = score / 100;

    return (
        <div className="flex flex-col items-center justify-center p-8">
            <div className="relative flex items-center justify-center mb-6">
                {/* SVG Ring */}
                <div className="relative" style={{ width: size, height: size }}>
                    <svg className="w-full h-full -rotate-90">
                        {/* Background Ring */}
                        <circle
                            cx={size / 2}
                            cy={size / 2}
                            r={radius}
                            fill="none"
                            stroke="rgba(255,255,255,0.05)"
                            strokeWidth={strokeWidth}
                        />
                        {/* Progress Ring */}
                        <motion.circle
                            cx={size / 2}
                            cy={size / 2}
                            r={radius}
                            fill="none"
                            stroke="url(#gradient)"
                            strokeWidth={strokeWidth}
                            strokeLinecap="round"
                            strokeDasharray={circumference}
                            initial={{ strokeDashoffset: circumference }}
                            animate={{ strokeDashoffset: circumference * (1 - progress) }}
                            transition={{ duration: 1.5, ease: "easeOut" }}
                        />
                        <defs>
                            <linearGradient id="gradient" x1="0%" y1="0%" x2="100%" y2="0%">
                                <stop offset="0%" stopColor="#6366F1" />
                                <stop offset="100%" stopColor="#06B6D4" />
                            </linearGradient>
                        </defs>
                    </svg>

                    {/* Center Content */}
                    <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
                        <span className="text-6xl font-bold text-white tracking-tighter mb-1">
                            {score}%
                        </span>
                        <span className="text-slate-400 text-sm font-medium uppercase tracking-wide">Match Probability</span>
                    </div>
                </div>
            </div>

            {/* Status Badge */}
            <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-full px-4 py-1.5 flex items-center gap-2">
                <div className="bg-emerald-500 rounded-full p-0.5">
                    <Check className="w-3 h-3 text-slate-900 stroke-[3]" />
                </div>
                <span className="text-emerald-500 text-sm font-bold tracking-wide">Gap Analysis Complete</span>
            </div>
        </div>
    );
}
