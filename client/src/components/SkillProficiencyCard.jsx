
import { motion } from 'framer-motion';
import { Database, Code2, Server, Globe, Cpu, Layout } from 'lucide-react';

const iconMap = {
    'System Design': Database,
    'Algorithms': Code2,
    'Backend': Server,
    'Frontend': Layout,
    'DevOps': Cpu,
    'Network': Globe
};

export default function SkillProficiencyCard({ skill }) {
    const { name, progress, color, icon } = skill;
    const Icon = iconMap[icon] || Code2;

    // Gradient definitions based on color prop or default
    const getGradient = (c) => {
        if (c === 'blue') return 'from-blue-500 to-cyan-400';
        if (c === 'purple') return 'from-purple-500 to-pink-400';
        if (c === 'green') return 'from-emerald-500 to-teal-400';
        if (c === 'orange') return 'from-orange-500 to-amber-400';
        return 'from-indigo-500 to-purple-400';
    };

    return (
        <div className="bg-slate-800 border border-white/5 rounded-2xl p-5 hover:border-white/10 transition-colors group">
            <div className="flex justify-between items-start mb-4">
                <div className={`p-2.5 rounded-xl bg-slate-900 border border-white/5`}>
                    <Icon className="w-6 h-6 text-slate-300 group-hover:text-white transition-colors" />
                </div>
                <span className="text-xl font-bold text-white">{progress}%</span>
            </div>

            <h3 className="text-slate-200 font-medium mb-3">{name}</h3>

            {/* Progress Bar */}
            <div className="h-2 w-full bg-slate-900 rounded-full overflow-hidden">
                <motion.div
                    className={`h-full bg-gradient-to-r ${getGradient(color)}`}
                    initial={{ width: 0 }}
                    animate={{ width: `${progress}%` }}
                    transition={{ duration: 1, delay: 0.2 }}
                />
            </div>
        </div>
    );
}
