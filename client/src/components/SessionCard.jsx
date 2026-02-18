
import { Calendar, Briefcase, ChevronRight } from 'lucide-react';

export default function SessionCard({ session }) {
    const { company = 'Google', title, role = 'L4 Software Engineer', date, score } = session;

    // Score Badge Color
    const getScoreColor = (s) => {
        if (s >= 80) return 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20';
        if (s >= 60) return 'bg-amber-500/10 text-amber-500 border-amber-500/20';
        return 'bg-red-500/10 text-red-500 border-red-500/20';
    };

    return (
        <div className="group flex items-center gap-4 p-4 rounded-xl border border-transparent hover:bg-slate-800 hover:border-white/5 transition-all cursor-pointer">
            {/* Company Icon Placeholder */}
            <div className="w-12 h-12 rounded-xl bg-slate-800 border border-white/5 flex items-center justify-center shrink-0 group-hover:bg-slate-700 transition-colors">
                <Briefcase className="w-5 h-5 text-indigo-400" />
            </div>

            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                    <h4 className="font-bold text-white truncate">{company} Mock</h4>
                    {title && <span className="text-slate-500 text-xs">• {title}</span>}
                </div>
                <div className="flex items-center gap-3 text-xs text-slate-400">
                    <span className="flex items-center gap-1">
                        <Briefcase className="w-3 h-3" /> {role}
                    </span>
                    <span className="w-1 h-1 rounded-full bg-slate-600" />
                    <span className="flex items-center gap-1">
                        <Calendar className="w-3 h-3" /> {date || 'Just now'}
                    </span>
                </div>
            </div>

            <div className={`px-3 py-1 rounded-full border text-xs font-bold leading-none ${getScoreColor(score)}`}>
                {score}%
            </div>

            <ChevronRight className="w-4 h-4 text-slate-600 group-hover:text-white transition-colors" />
        </div>
    );
}
