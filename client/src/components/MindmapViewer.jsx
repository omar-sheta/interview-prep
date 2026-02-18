/**
 * Interactive Force-Directed Graph Visualization
 * Displays skill gaps with expandable/collapsible nodes & details panel
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import { ZoomIn, ZoomOut, Maximize2, ChevronRight, X, ExternalLink, Lightbulb } from 'lucide-react';
import * as d3 from 'd3';
import { motion, AnimatePresence } from 'framer-motion';

// Parse mindmap code to extract Root info (fallback or primary for root)
function parseRootInfo(code) {
    if (!code) return { label: 'Target Role', score: 0 };

    // Extract root info: ROOT[(Title<br/>Score: 75%)]
    const rootMatch = code.match(/ROOT\[\(([^<]+)(?:<br\/>Score: (\d+)%)?/);
    if (rootMatch) {
        return {
            label: rootMatch[1].trim(),
            score: parseInt(rootMatch[2] || '0')
        };
    }
    return { label: 'Target Role', score: 0 };
}

// Build graph data structure from rich skillMapping
function buildGraphData(mindmapCode, skillMapping) {
    const rootInfo = parseRootInfo(mindmapCode);
    const nodes = [];
    const links = [];

    // Root node
    nodes.push({
        id: 'root',
        label: rootInfo.label,
        score: rootInfo.score,
        type: 'root',
        expanded: true,
        children: []
    });

    const categoryConfig = {
        matched: {
            label: 'Strengths',
            icon: '✓',
            color: '#10b981',
            bgColor: '#065f46',
            description: "Skills you've mastered that align with the role."
        },
        partial: {
            label: 'Developing',
            icon: '◐',
            color: '#eab308',
            bgColor: '#854d0e',
            description: "Skills where you show potential but need more depth."
        },
        missing: {
            label: 'Gaps',
            icon: '✗',
            color: '#ef4444',
            bgColor: '#7f1d1d',
            description: "Critical skills missing from your profile."
        },
        bonus: {
            label: 'Bonus',
            icon: '★',
            color: '#3b82f6',
            bgColor: '#1e3a5f',
            description: "Extra skills that give you an edge."
        },
        candidate_extra_skills: { // Fallback name in backend state
            label: 'Bonus',
            icon: '★',
            color: '#3b82f6',
            bgColor: '#1e3a5f',
            description: "Extra skills that give you an edge."
        }
    };

    console.log('🔍 MindmapViewer buildGraphData called');
    console.log('🔍 mindmapCode length:', mindmapCode?.length || 0);
    console.log('🔍 skillMapping:', skillMapping);
    console.log('🔍 skillMapping keys:', skillMapping ? Object.keys(skillMapping) : 'null');

    // If we have rich data, use it
    if (skillMapping) {
        Object.entries(skillMapping).forEach(([key, skills]) => {
            if (!skills || skills.length === 0) return;
            const config = categoryConfig[key];
            if (!config) return;

            const categoryId = `cat_${key}`;

            // Category node
            nodes.push({
                id: categoryId,
                label: `${config.icon} ${config.label}`,
                type: 'category',
                category: key,
                color: config.color,
                bgColor: config.bgColor,
                expanded: true,
                count: skills.length,
                description: config.description,
                children: skills.map((_, i) => `${key}_${i}`)
            });

            links.push({
                source: 'root',
                target: categoryId,
                color: config.color
            });

            // Skill nodes
            skills.forEach((skillObj, i) => {
                const skillId = `${key}_${i}`;
                let name = "Unknown Skill";
                let reason = null;
                let resource = null;

                if (typeof skillObj === 'string') {
                    name = skillObj;
                } else if (typeof skillObj === 'object' && skillObj !== null) {
                    name = skillObj.name || "Unknown";
                    reason = skillObj.reason;
                    resource = skillObj.learning_tip;
                }

                // Truncate for graph display
                const displayLabel = name.length > 25 ? name.substring(0, 25) + '...' : name;

                nodes.push({
                    id: skillId,
                    label: displayLabel,
                    fullLabel: name,
                    type: 'skill',
                    category: key,
                    color: config.color,
                    bgColor: config.bgColor,
                    parentId: categoryId,
                    reason: reason,
                    resource: resource
                });

                links.push({
                    source: categoryId,
                    target: skillId,
                    color: config.color
                });
            });
        });
    } else {
        // Fallback: Parse from Mermaid string if skillMapping is missing
        console.log('⚠️ No skillMapping provided, using fallback');
    }

    console.log('🔍 buildGraphData result:', nodes.length, 'nodes,', links.length, 'links');
    console.log('🔍 nodes:', nodes);

    return { nodes, links };
}

export default function MindmapViewer({ mindmapCode, skillMapping }) {
    const svgRef = useRef(null);
    const containerRef = useRef(null);
    const simulationRef = useRef(null);
    const [dimensions, setDimensions] = useState({ width: 800, height: 500 });
    const [graphData, setGraphData] = useState({ nodes: [], links: [] });
    const [collapsedNodes, setCollapsedNodes] = useState(new Set());
    const [selectedNode, setSelectedNode] = useState(null);

    // Parse data
    useEffect(() => {
        const data = buildGraphData(mindmapCode, skillMapping);
        setGraphData(data);
    }, [mindmapCode, skillMapping]);

    // Resize handler
    useEffect(() => {
        if (!containerRef.current) return;
        const resizeObserver = new ResizeObserver(entries => {
            for (const entry of entries) {
                setDimensions({
                    width: entry.contentRect.width || 800,
                    height: entry.contentRect.height || 500
                });
            }
        });
        resizeObserver.observe(containerRef.current);
        return () => resizeObserver.disconnect();
    }, []);

    // Toggle node expansion
    const toggleNode = useCallback((nodeId) => {
        setCollapsedNodes(prev => {
            const newSet = new Set(prev);
            if (newSet.has(nodeId)) newSet.delete(nodeId);
            else newSet.add(nodeId);
            return newSet;
        });
    }, []);

    // Handle Click
    const handleNodeClick = useCallback((node) => {
        if (node.type === 'category') {
            toggleNode(node.id);
        } else if (node.type === 'skill') {
            setSelectedNode(node);
        }
    }, [toggleNode]);

    // D3 Force Simulation
    useEffect(() => {
        if (!svgRef.current || graphData.nodes.length === 0) return;

        const svg = d3.select(svgRef.current);
        svg.selectAll('*').remove();

        const { width, height } = dimensions;

        // Filter visible nodes/links
        const visibleNodes = graphData.nodes.filter(node => {
            if (node.type === 'root' || node.type === 'category') return true;
            const parentNode = graphData.nodes.find(n => n.id === node.parentId);
            return parentNode && !collapsedNodes.has(parentNode.id);
        });

        const visibleNodeIds = new Set(visibleNodes.map(n => n.id));
        const visibleLinks = graphData.links.filter(link =>
            visibleNodeIds.has(link.source.id || link.source) &&
            visibleNodeIds.has(link.target.id || link.target)
        );

        // Zoom Group
        const g = svg.append('g').attr('class', 'zoom-group');

        const zoomBehavior = d3.zoom()
            .scaleExtent([0.1, 4])
            .filter((event) => {
                // PC: Ctrl+Wheel, Mac: Meta+Wheel to zoom. Otherwise allow scroll.
                if (event.type === 'wheel' && !event.ctrlKey && !event.metaKey) return false;
                return !event.button; // Allow left click pan
            })
            .on('zoom', (event) => {
                g.attr('transform', event.transform);
            });

        svg.call(zoomBehavior);

        // Initial Zoom
        svg.call(zoomBehavior.transform, d3.zoomIdentity.translate(width / 2, height / 2).scale(0.8));

        // Expose zoom control to component
        svgRef.current.zoom = {
            in: () => svg.transition().duration(300).call(zoomBehavior.scaleBy, 1.2),
            out: () => svg.transition().duration(300).call(zoomBehavior.scaleBy, 0.8),
            fit: () => svg.transition().duration(750).call(zoomBehavior.transform, d3.zoomIdentity.translate(width / 2, height / 2).scale(0.8))
        };

        // Defs (Glow)
        const defs = svg.append('defs');
        const filter = defs.append('filter').attr('id', 'glow');
        filter.append('feGaussianBlur').attr('stdDeviation', '2.5').attr('result', 'coloredBlur');
        const feMerge = filter.append('feMerge');
        feMerge.append('feMergeNode').attr('in', 'coloredBlur');
        feMerge.append('feMergeNode').attr('in', 'SourceGraphic');

        // Force Simulation
        // FIX: Structured Horizontal Layout + Tighter Packing
        const simulation = d3.forceSimulation(visibleNodes)
            .force('link', d3.forceLink(visibleLinks).id(d => d.id).distance(d => d.source.type === 'root' ? 80 : 50)) // Much tighter links
            .force('charge', d3.forceManyBody().strength(d => d.type === 'root' ? -500 : -200)) // Reduced repulsion
            .force('center', d3.forceCenter(0, 0))
            // Horizontal Spread Strategy (Simplified to preventing flying nodes)
            .force('x', d3.forceX(0).strength(0.05))
            .force('y', d3.forceY(0).strength(0.05))
            .force('collide', d3.forceCollide().radius(d => {
                if (d.type === 'root') return 80;
                if (d.type === 'category') return 60;
                return (d.label?.length || 5) * 4 + 20;
            }).iterations(2))
            .alphaDecay(0.05);

        simulationRef.current = simulation;

        // Draw Links
        const link = g.append('g').selectAll('path')
            .data(visibleLinks)
            .join('path')
            .attr('fill', 'none')
            .attr('stroke', d => d.color || '#525252')
            .attr('stroke-width', 2)
            .attr('stroke-opacity', 0.5);

        // Draw Nodes
        const node = g.append('g').selectAll('g')
            .data(visibleNodes)
            .join('g')
            .attr('cursor', 'pointer')
            .call(d3.drag()
                .on('start', (e, d) => {
                    if (!e.active) simulation.alphaTarget(0.3).restart();
                    d.fx = d.x; d.fy = d.y;
                })
                .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; })
                .on('end', (e, d) => {
                    if (!e.active) simulation.alphaTarget(0);
                    d.fx = null; d.fy = null;
                })
            )
            .on('click', (e, d) => {
                e.stopPropagation();
                handleNodeClick(d);
            })
            .on('mouseenter', function () {
                d3.select(this).raise(); // Bring to front
                d3.select(this).select('rect, circle').transition().attr('filter', 'url(#glow)').attr('transform', 'scale(1.1)');
            })
            .on('mouseleave', function () {
                d3.select(this).select('rect, circle').transition().attr('filter', null).attr('transform', 'scale(1)');
            });

        // Node Shapes & Labels (Increased legibility)
        node.each(function (d) {
            const el = d3.select(this);
            if (d.type === 'root') {
                el.append('circle').attr('r', 55).attr('fill', '#4c1d95').attr('stroke', '#8b5cf6').attr('stroke-width', 3);
                el.append('text').text(d.label).attr('dy', -5).attr('text-anchor', 'middle').attr('fill', '#fff').attr('font-size', '14px').attr('font-weight', 'bold').style('pointer-events', 'none');
                el.append('text').text(`${d.score}%`).attr('dy', 16).attr('text-anchor', 'middle').attr('fill', '#a78bfa').attr('font-size', '18px').attr('font-weight', 'bold').style('pointer-events', 'none');
            } else if (d.type === 'category') {
                el.append('rect').attr('width', 120).attr('height', 38).attr('x', -60).attr('y', -19).attr('rx', 18).attr('fill', d.bgColor).attr('stroke', d.color).attr('stroke-width', 2);
                el.append('text').text(d.label).attr('dy', 5).attr('text-anchor', 'middle').attr('fill', '#fff').attr('font-size', '13px').attr('font-weight', '600').style('pointer-events', 'none');
                el.append('circle').attr('cx', 50).attr('r', 9).attr('fill', d.color).attr('stroke', 'rgba(0,0,0,0.1)'); // Badge
                el.append('text').text(collapsedNodes.has(d.id) ? '+' : d.count).attr('x', 50).attr('dy', 4).attr('text-anchor', 'middle').attr('fill', '#fff').attr('font-size', '11px').style('pointer-events', 'none');
            } else {
                // Skill
                const w = Math.max(90, (d.label?.length || 0) * 7 + 24);
                el.append('rect').attr('width', w).attr('height', 32).attr('x', -w / 2).attr('y', -16).attr('rx', 8).attr('fill', d.bgColor).attr('stroke', d.color).attr('stroke-width', 1).attr('fill-opacity', 1);
                el.append('text').text(d.label).attr('dy', 5).attr('text-anchor', 'middle').attr('fill', '#fff').attr('font-size', '12px').style('pointer-events', 'none');
            }
        });

        simulation.on('tick', () => {
            link.attr('d', d => `M${d.source.x},${d.source.y}Q${(d.source.x + d.target.x) / 2},${(d.source.y + d.target.y) / 2} ${d.target.x},${d.target.y}`);
            node.attr('transform', d => `translate(${d.x},${d.y})`);
        });

        return () => simulation.stop();
    }, [graphData, dimensions, collapsedNodes, handleNodeClick]);

    const handleZoom = (action) => {
        if (svgRef.current?.zoom?.[action]) svgRef.current.zoom[action]();
    };

    return (
        <div ref={containerRef} className="h-full w-full relative overflow-hidden touch-pan-y" style={{ minHeight: '300px' }}>
            {/* Text Hint */}
            <div className="absolute bottom-4 left-4 z-10 pointer-events-none opacity-50 text-xs text-gray-400 font-mono">
                Hold CMD/CTRL to Zoom • Drag to Pan
            </div>

            {/* Zoom Controls */}
            <div className="absolute top-4 left-4 flex flex-col gap-2 z-20">
                <button onClick={() => handleZoom('in')} className="p-2 bg-[#161b22]/80 backdrop-blur border border-white/10 rounded-lg text-gray-300 hover:text-white hover:bg-white/10 transition-colors" title="Zoom In">
                    <ZoomIn size={18} />
                </button>
                <button onClick={() => handleZoom('out')} className="p-2 bg-[#161b22]/80 backdrop-blur border border-white/10 rounded-lg text-gray-300 hover:text-white hover:bg-white/10 transition-colors" title="Zoom Out">
                    <ZoomOut size={18} />
                </button>
                <button onClick={() => handleZoom('fit')} className="p-2 bg-[#161b22]/80 backdrop-blur border border-white/10 rounded-lg text-gray-300 hover:text-white hover:bg-white/10 transition-colors" title="Fit View">
                    <Maximize2 size={18} />
                </button>
            </div>

            <svg ref={svgRef} width={dimensions.width} height={dimensions.height} className="w-full h-full" onClick={() => setSelectedNode(null)} />

            {/* Details Modal */}
            <AnimatePresence>
                {selectedNode && (
                    <motion.div
                        initial={{ opacity: 0, x: 50 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: 50 }}
                        className="absolute top-4 right-4 bottom-4 w-80 bg-[#0d1117]/95 backdrop-blur-md border border-white/10 rounded-xl shadow-2xl overflow-hidden flex flex-col z-30"
                    >
                        {/* Header */}
                        <div className="p-4 border-b border-white/5 flex justify-between items-start" style={{ borderColor: selectedNode.color }}>
                            <div>
                                <span className="text-xs font-mono uppercase opacity-70" style={{ color: selectedNode.color }}>
                                    {selectedNode.category === 'missing' ? 'Recommended Skill' : 'Skill Analysis'}
                                </span>
                                <h3 className="text-lg font-bold text-white mt-1">{selectedNode.fullLabel || selectedNode.label}</h3>
                            </div>
                            <button onClick={() => setSelectedNode(null)} className="text-zinc-400 hover:text-white">
                                <X size={20} />
                            </button>
                        </div>

                        {/* Content */}
                        <div className="p-5 overflow-auto space-y-6">
                            {/* Reason */}
                            <div>
                                <h4 className="flex items-center gap-2 text-sm font-semibold text-zinc-300 mb-2">
                                    <Lightbulb size={16} className="text-yellow-400" />
                                    Why it matters
                                </h4>
                                <p className="text-sm text-zinc-400 leading-relaxed">
                                    {selectedNode.reason || "This skill is a core requirement for the target role."}
                                </p>
                            </div>

                            {/* Resource */}
                            {selectedNode.resource && (
                                <div className="p-3 rounded-lg bg-blue-500/10 border border-blue-500/20">
                                    <h4 className="flex items-center gap-2 text-sm font-semibold text-blue-400 mb-2">
                                        <ExternalLink size={16} />
                                        How to learn
                                    </h4>
                                    <p className="text-sm text-zinc-300">
                                        {selectedNode.resource}
                                    </p>
                                </div>
                            )}

                            {!selectedNode.resource && selectedNode.category === 'missing' && (
                                <div className="text-xs text-zinc-500 italic">
                                    Ask the AI Coach for a learning plan on this topic.
                                </div>
                            )}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Controls */}
            <div className="absolute top-3 right-3 flex gap-1 bg-black/50 p-1.5 rounded-lg border border-white/10">
                <button className="p-1.5 hover:bg-white/10 rounded text-zinc-300" onClick={() => {
                    d3.select(svgRef.current).transition().call(d3.zoom().transform, d3.zoomIdentity.translate(dimensions.width / 2, dimensions.height / 2).scale(0.9));
                }}><Maximize2 size={16} /></button>
            </div>
        </div>
    );
}
