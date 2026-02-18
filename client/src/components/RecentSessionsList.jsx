
import SessionCard from './SessionCard';
import { ArrowRight } from 'lucide-react';

export default function RecentSessionsList({ sessions = [] }) {
    return (
        <div className="bg-slate-900/50 border border-white/5 rounded-2xl p-6 h-full backdrop-blur-sm">
            <div className="flex items-center justify-between mb-6">
                <h3 className="font-bold text-white text-lg">Recent Sessions</h3>
                {sessions.length > 0 && (
                    <button className="text-sm text-indigo-400 hover:text-indigo-300 flex items-center gap-1 font-medium transition-colors">
                        View All <ArrowRight className="w-4 h-4" />
                    </button>
                )}
            </div>

            <div className="space-y-1">
                {sessions.length > 0 ? (
                    sessions.map((session, i) => (
                        <SessionCard key={i} session={session} />
                    ))
                ) : (
                    <div className="text-center py-10 text-slate-500">
                        <p>No recent sessions found.</p>
                        <p className="text-sm mt-1">Start a new practice to see history.</p>
                    </div>
                )}
            </div>
        </div>
    );
}
