/**
 * Floating Particles Background Component
 * Creates an animated particle field for premium aesthetic
 */

import { useEffect, useRef } from 'react';

export default function ParticleBackground({ particleCount = 50 }) {
    const canvasRef = useRef(null);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        let animationId;
        let particles = [];

        const resize = () => {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
        };

        const createParticle = () => ({
            x: Math.random() * canvas.width,
            y: Math.random() * canvas.height,
            size: Math.random() * 2 + 0.5,
            speedX: (Math.random() - 0.5) * 0.3,
            speedY: (Math.random() - 0.5) * 0.3,
            opacity: Math.random() * 0.5 + 0.1,
            hue: Math.random() * 60 + 220, // Blue to purple range
        });

        const init = () => {
            resize();
            particles = Array.from({ length: particleCount }, createParticle);
        };

        const drawParticle = (p) => {
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
            ctx.fillStyle = `hsla(${p.hue}, 70%, 60%, ${p.opacity})`;
            ctx.fill();
        };

        const drawConnections = () => {
            for (let i = 0; i < particles.length; i++) {
                for (let j = i + 1; j < particles.length; j++) {
                    const dx = particles[i].x - particles[j].x;
                    const dy = particles[i].y - particles[j].y;
                    const dist = Math.sqrt(dx * dx + dy * dy);

                    if (dist < 120) {
                        ctx.beginPath();
                        ctx.moveTo(particles[i].x, particles[i].y);
                        ctx.lineTo(particles[j].x, particles[j].y);
                        ctx.strokeStyle = `rgba(139, 92, 246, ${0.1 * (1 - dist / 120)})`;
                        ctx.lineWidth = 0.5;
                        ctx.stroke();
                    }
                }
            }
        };

        const animate = () => {
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            particles.forEach((p) => {
                p.x += p.speedX;
                p.y += p.speedY;

                // Wrap around edges
                if (p.x < 0) p.x = canvas.width;
                if (p.x > canvas.width) p.x = 0;
                if (p.y < 0) p.y = canvas.height;
                if (p.y > canvas.height) p.y = 0;

                drawParticle(p);
            });

            drawConnections();
            animationId = requestAnimationFrame(animate);
        };

        init();
        animate();

        window.addEventListener('resize', init);

        return () => {
            cancelAnimationFrame(animationId);
            window.removeEventListener('resize', init);
        };
    }, [particleCount]);

    return (
        <canvas
            ref={canvasRef}
            className="fixed inset-0 pointer-events-none z-0"
            style={{ opacity: 0.6 }}
        />
    );
}
