/**
 * Premium Button Component
 * Gradient button with glow effect and animations
 */

import { motion } from 'framer-motion';
import { Loader2 } from 'lucide-react';

export function GradientButton({
    children,
    onClick,
    disabled = false,
    loading = false,
    variant = 'primary',
    size = 'md',
    icon: Icon,
    className = '',
}) {
    const variants = {
        primary: 'from-orange-500 via-amber-500 to-yellow-500',
        success: 'from-emerald-500 via-green-500 to-teal-500',
        danger: 'from-red-500 via-rose-500 to-pink-500',
        gold: 'from-amber-400 via-yellow-400 to-orange-400',
    };

    const sizes = {
        sm: 'px-4 py-2 text-sm',
        md: 'px-6 py-3 text-base',
        lg: 'px-8 py-4 text-lg',
    };

    return (
        <motion.button
            whileHover={!disabled ? { scale: 1.02, y: -2 } : {}}
            whileTap={!disabled ? { scale: 0.98 } : {}}
            onClick={onClick}
            disabled={disabled || loading}
            className={`
        relative group overflow-hidden rounded-xl font-semibold
        bg-gradient-to-r ${variants[variant]}
        text-white shadow-lg
        ${sizes[size]}
        ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
        ${className}
      `}
        >
            {/* Glow effect */}
            <div
                className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500"
                style={{
                    background: 'radial-gradient(circle at center, rgba(255,255,255,0.2) 0%, transparent 70%)',
                }}
            />

            {/* Shimmer effect */}
            <motion.div
                className="absolute inset-0 -translate-x-full"
                animate={{ translateX: ['100%', '-100%'] }}
                transition={{ duration: 3, repeat: Infinity, ease: 'linear' }}
                style={{
                    background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent)',
                }}
            />

            {/* Content */}
            <span className="relative z-10 flex items-center justify-center gap-2">
                {loading ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                ) : Icon ? (
                    <Icon className="w-5 h-5" />
                ) : null}
                {children}
            </span>

            {/* Bottom glow */}
            <div
                className="absolute -bottom-2 left-1/2 -translate-x-1/2 w-3/4 h-4 blur-xl opacity-50"
                style={{
                    background: `linear-gradient(to right, ${variant === 'primary' ? '#8b5cf6, #3b82f6' : '#22c55e, #14b8a6'})`,
                }}
            />
        </motion.button>
    );
}

/**
 * Glass Card Component
 * Premium glassmorphism card with gradient border
 */
export function GlassCard({ children, className = '', glow = false }) {
    return (
        <div
            className={`
        relative rounded-2xl overflow-hidden
        ${className}
      `}
        >
            {/* Gradient border */}
            <div
                className="absolute inset-0 rounded-2xl p-[1px]"
                style={{
                    background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.3), rgba(59, 130, 246, 0.2), rgba(34, 211, 238, 0.1))',
                }}
            />

            {/* Inner content */}
            <div className="relative h-full rounded-2xl bg-zinc-900/80 backdrop-blur-xl p-1">
                <div className="h-full rounded-xl bg-zinc-900/50 p-4">
                    {children}
                </div>
            </div>

            {/* Glow effect */}
            {glow && (
                <div
                    className="absolute -inset-4 -z-10 opacity-50 blur-2xl"
                    style={{
                        background: 'radial-gradient(circle, rgba(139, 92, 246, 0.15), transparent 70%)',
                    }}
                />
            )}
        </div>
    );
}

/**
 * Badge Component
 * Status badges with various styles
 */
export function Badge({
    children,
    variant = 'default',
    pulse = false,
    icon: Icon,
}) {
    const variants = {
        default: 'bg-zinc-800 text-zinc-300 border-zinc-700',
        success: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
        warning: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
        danger: 'bg-red-500/20 text-red-400 border-red-500/30',
        info: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
        purple: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
    };

    return (
        <span className={`
      inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium
      border ${variants[variant]}
    `}>
            {pulse && (
                <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-current opacity-75" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-current" />
                </span>
            )}
            {Icon && <Icon className="w-3 h-3" />}
            {children}
        </span>
    );
}

/**
 * Stat Card Component
 * For displaying metrics with icons
 */
export function StatCard({
    label,
    value,
    icon: Icon,
    trend,
    color = 'purple',
}) {
    const colors = {
        purple: 'from-purple-500 to-violet-600',
        blue: 'from-blue-500 to-cyan-500',
        green: 'from-emerald-500 to-teal-500',
        amber: 'from-amber-500 to-orange-500',
    };

    return (
        <div className="relative overflow-hidden rounded-xl bg-zinc-900/50 border border-white/5 p-4">
            {/* Background gradient */}
            <div
                className="absolute top-0 right-0 w-20 h-20 opacity-20 blur-2xl"
                style={{
                    background: `linear-gradient(135deg, ${color === 'purple' ? '#8b5cf6' : color === 'blue' ? '#3b82f6' : color === 'green' ? '#22c55e' : '#f59e0b'}, transparent)`,
                }}
            />

            <div className="relative z-10">
                <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-zinc-500 uppercase tracking-wider">{label}</span>
                    {Icon && (
                        <div className={`p-1.5 rounded-lg bg-gradient-to-br ${colors[color]}`}>
                            <Icon className="w-3.5 h-3.5 text-white" />
                        </div>
                    )}
                </div>

                <div className="flex items-end gap-2">
                    <span className="text-2xl font-bold text-white">{value}</span>
                    {trend && (
                        <span className={`text-xs ${trend > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                            {trend > 0 ? '+' : ''}{trend}%
                        </span>
                    )}
                </div>
            </div>
        </div>
    );
}
