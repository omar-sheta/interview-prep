/**
 * Gradient Orb Background Component
 * Animated gradient blobs for ambient lighting effect
 */

import { motion } from 'framer-motion';

export default function GradientOrbs() {
    return (
        <div className="fixed inset-0 overflow-hidden pointer-events-none z-0">
            {/* Primary Purple Orb */}
            <motion.div
                className="absolute w-[600px] h-[600px] rounded-full"
                style={{
                    background: 'radial-gradient(circle, rgba(139, 92, 246, 0.15) 0%, transparent 70%)',
                    filter: 'blur(60px)',
                    top: '-10%',
                    right: '-10%',
                }}
                animate={{
                    x: [0, 50, 0],
                    y: [0, 30, 0],
                    scale: [1, 1.1, 1],
                }}
                transition={{
                    duration: 20,
                    repeat: Infinity,
                    ease: 'easeInOut',
                }}
            />

            {/* Blue Orb */}
            <motion.div
                className="absolute w-[500px] h-[500px] rounded-full"
                style={{
                    background: 'radial-gradient(circle, rgba(59, 130, 246, 0.12) 0%, transparent 70%)',
                    filter: 'blur(80px)',
                    bottom: '-15%',
                    left: '-10%',
                }}
                animate={{
                    x: [0, -30, 0],
                    y: [0, -40, 0],
                    scale: [1, 1.15, 1],
                }}
                transition={{
                    duration: 25,
                    repeat: Infinity,
                    ease: 'easeInOut',
                }}
            />

            {/* Cyan Accent Orb */}
            <motion.div
                className="absolute w-[400px] h-[400px] rounded-full"
                style={{
                    background: 'radial-gradient(circle, rgba(34, 211, 238, 0.08) 0%, transparent 70%)',
                    filter: 'blur(50px)',
                    top: '40%',
                    left: '30%',
                }}
                animate={{
                    x: [0, 60, 0],
                    y: [0, -30, 0],
                    scale: [1, 0.9, 1],
                }}
                transition={{
                    duration: 18,
                    repeat: Infinity,
                    ease: 'easeInOut',
                }}
            />

            {/* Pink Accent */}
            <motion.div
                className="absolute w-[300px] h-[300px] rounded-full"
                style={{
                    background: 'radial-gradient(circle, rgba(236, 72, 153, 0.1) 0%, transparent 70%)',
                    filter: 'blur(40px)',
                    bottom: '20%',
                    right: '20%',
                }}
                animate={{
                    x: [0, -40, 0],
                    y: [0, 20, 0],
                }}
                transition={{
                    duration: 15,
                    repeat: Infinity,
                    ease: 'easeInOut',
                }}
            />
        </div>
    );
}
