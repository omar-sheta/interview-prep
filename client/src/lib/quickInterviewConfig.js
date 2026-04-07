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

export const QUICK_JOB_PRESETS = [
    {
        id: 'software_engineer',
        title: 'Software Engineer',
        jobTitle: 'Software Engineer',
        jobDescription: [
            'Build and maintain production software across backend services and user-facing features.',
            'Design APIs, debug application issues, write tests, and improve reliability and performance.',
            'Collaborate with product, design, and engineering teammates to ship features and iterate quickly.',
            'Work with modern development tools, cloud infrastructure, databases, and code review workflows.',
        ].join(' '),
    },
    {
        id: 'ai_engineer',
        title: 'AI Engineer',
        jobTitle: 'AI Engineer',
        jobDescription: [
            'Build and deploy AI-powered product features using Python, LLM APIs, and evaluation workflows.',
            'Design prompts, retrieval pipelines, agent behavior, and guardrails for reliable model outputs.',
            'Collaborate with product and engineering teams to productionize AI systems and monitor quality.',
            'Debug latency, cost, and accuracy issues across inference, orchestration, and data pipelines.',
        ].join(' '),
    },
    {
        id: 'frontend_engineer',
        title: 'Frontend Engineer',
        jobTitle: 'Frontend Engineer',
        jobDescription: [
            'Build polished web experiences using React, TypeScript, and modern frontend tooling.',
            'Translate product requirements into accessible, responsive UI with strong performance and usability.',
            'Own component architecture, client-side state, debugging, testing, and collaboration with design.',
            'Improve page load speed, reliability, and maintainability across the frontend codebase.',
        ].join(' '),
    },
    {
        id: 'data_engineer',
        title: 'Data Engineer',
        jobTitle: 'Data Engineer',
        jobDescription: [
            'Design and maintain reliable data pipelines for analytics, machine learning, and operational reporting.',
            'Build ETL workflows using SQL and Python, manage data quality, and optimize warehouse performance.',
            'Partner with analysts, data scientists, and engineering teams to model and deliver trusted datasets.',
            'Monitor jobs, troubleshoot failures, and improve scalability, observability, and cost efficiency.',
        ].join(' '),
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
