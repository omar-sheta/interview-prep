import {
    Psychology,
    Code,
    AccountTree,
    AutoAwesome,
    Diversity3,
    Gavel,
} from '@mui/icons-material';

export const PERSONA_OPTIONS = [
    {
        id: 'friendly',
        label: 'Friendly',
        icon: Diversity3,
        description: 'Supportive tone, clear prompts, and collaborative pacing.',
    },
    {
        id: 'strict',
        label: 'Strict',
        icon: Gavel,
        description: 'High bar, direct wording, and precision-focused follow-ups.',
    },
];

export const QUICK_INTERVIEW_TYPES = [
    {
        id: 'behavioral',
        title: 'Behavioral',
        description: 'STAR-style storytelling, leadership, and communication.',
        icon: Psychology,
        tags: ['STAR', 'Leadership'],
    },
    {
        id: 'technical',
        title: 'Technical',
        description: 'Implementation decisions, trade-offs, and debugging.',
        icon: Code,
        tags: ['Problem Solving', 'Architecture'],
    },
    {
        id: 'system_design',
        title: 'System Design',
        description: 'Scalability, reliability, and large-scale design.',
        icon: AccountTree,
        tags: ['Scalability', 'Trade-offs'],
    },
    {
        id: 'mixed',
        title: 'Mixed',
        description: 'Balanced flow across behavioral, technical, and design.',
        icon: AutoAwesome,
        tags: ['Balanced', 'Adaptive'],
    },
];

export function getQuickSkillGaps(interviewType) {
    if (interviewType === 'behavioral') return ['communication', 'stakeholder management', 'leadership', 'conflict resolution'];
    if (interviewType === 'technical') return ['technical fundamentals', 'problem solving', 'debugging'];
    if (interviewType === 'system_design') return ['system design', 'scalability', 'reliability', 'trade-offs'];
    return [];
}

export function normalizeQuickPersona(value) {
    const normalized = String(value || '').trim().toLowerCase();
    const allowed = new Set(PERSONA_OPTIONS.map((option) => option.id));
    return allowed.has(normalized) ? normalized : 'friendly';
}

export function clampQuickQuestionCount(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return 5;
    return Math.max(1, Math.min(12, Math.trunc(n)));
}
