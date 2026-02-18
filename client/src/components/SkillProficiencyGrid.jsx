
import { Plus } from 'lucide-react';
import SkillProficiencyCard from './SkillProficiencyCard';

export default function SkillProficiencyGrid({ skills }) {
    return (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 lg:gap-6 mb-8">
            {skills.map((skill, i) => (
                <SkillProficiencyCard key={i} skill={skill} />
            ))}

            {/* Add Track Placeholder */}
            <button className="border border-dashed border-white/10 rounded-2xl p-5 flex flex-col items-center justify-center gap-3 hover:bg-white/5 transition-colors group min-h-[160px]">
                <div className="w-12 h-12 rounded-full bg-slate-800 flex items-center justify-center border border-white/5 group-hover:scale-110 transition-transform">
                    <Plus className="w-6 h-6 text-slate-400" />
                </div>
                <span className="text-slate-400 font-medium font-mono text-sm">ADD SKILL TRACK</span>
            </button>
        </div>
    );
}
