/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                slate: {
                    950: '#0F172A',
                    900: '#0C1117', // Custom dark
                    800: '#1E293B',
                    700: '#334155',
                    50: '#F8FAFC',
                    300: '#CBD5E1',
                    500: '#64748B',
                },
                indigo: {
                    500: '#6366F1',
                    600: '#4F46E5',
                },
                cyan: {
                    500: '#06B6D4',
                },
                green: {
                    500: '#10B981',
                    600: '#059669',
                },
                yellow: {
                    500: '#F59E0B',
                },
                red: {
                    500: '#EF4444',
                },
                purple: {
                    500: '#8B5CF6',
                }
            },
            animation: {
                'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
                'blob': 'blob 10s infinite',
                'spin-slow': 'spin-slow 10s linear infinite',
            },
            backgroundImage: {
                'grid-pattern': 'radial-gradient(circle at 1px 1px, rgba(255,255,255,0.05) 1px, transparent 0)',
            },
            backgroundSize: {
                'grid': '40px 40px',
            }
        },
    },
    plugins: [],
}
