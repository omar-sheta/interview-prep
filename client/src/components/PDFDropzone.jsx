import { useCallback, useMemo, useState } from 'react';
import { motion as Motion, AnimatePresence } from 'framer-motion';

export default function PDFDropzone({ onUpload, isLoading = false, hasSavedResume = false, savedLabel = '' }) {
    const [isDragging, setIsDragging] = useState(false);
    const [fileName, setFileName] = useState(null);
    const [error, setError] = useState(null);
    const isReady = Boolean(fileName || hasSavedResume);
    const displayLabel = useMemo(() => {
        if (isLoading) return 'Processing...';
        if (isDragging) return 'Drop resume here';
        return 'Upload Resume';
    }, [isDragging, isLoading]);

    const handleFile = useCallback(async (file) => {
        if (!file) return;
        if (file.type !== 'application/pdf') {
            setError('Please upload a PDF file');
            return;
        }
        if (file.size > 10 * 1024 * 1024) {
            setError('File size must be less than 10MB');
            return;
        }
        setError(null);
        setFileName(file.name);
        const reader = new FileReader();
        reader.onload = () => {
            const base64 = reader.result.split(',')[1];
            onUpload(base64, file.name);
        };
        reader.readAsDataURL(file);
    }, [onUpload]);

    const handleDrop = useCallback((e) => {
        e.preventDefault();
        setIsDragging(false);
        handleFile(e.dataTransfer.files[0]);
    }, [handleFile]);

    const handleDragOver = useCallback((e) => {
        e.preventDefault();
        setIsDragging(true);
    }, []);

    const handleDragLeave = useCallback((e) => {
        e.preventDefault();
        setIsDragging(false);
    }, []);

    const handleClick = useCallback(() => {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.pdf';
        input.onchange = (e) => handleFile(e.target.files?.[0]);
        input.click();
    }, [handleFile]);

    return (
        <Motion.div
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onClick={!isLoading ? handleClick : undefined}
            className={`
        relative w-full h-full min-h-[120px] border-2 border-dashed rounded-xl transition-all duration-300 cursor-pointer flex flex-col items-center justify-center
        ${isDragging
                    ? 'border-[#00c2b2] bg-[#00c2b2]/5'
                    : isReady
                        ? 'border-emerald-500/50 bg-emerald-500/5'
                        : 'border-gray-700 hover:border-[#00c2b2]/50 bg-[#0d1117]/50 hover:bg-[#0d1117]'
                }
        ${isLoading ? 'pointer-events-none opacity-70' : ''}
      `}
            whileHover={!isLoading ? { scale: 1.01 } : {}}
            whileTap={!isLoading ? { scale: 0.99 } : {}}
        >
            <div className="flex flex-col items-center justify-center p-4 text-center w-full h-full">
                {/* Icon */}
                <Motion.div
                    className={`w-12 h-12 rounded-full border flex items-center justify-center mb-3 transition-all ${isDragging
                        ? 'bg-[#00c2b2]/20 border-[#00c2b2]/50 scale-110'
                        : isReady
                            ? 'bg-emerald-500/20 border-emerald-500/50'
                            : 'bg-[#161b22] border-gray-700 group-hover:border-[#00c2b2]/50'
                        }`}
                    animate={isDragging ? { scale: 1.1 } : { scale: 1 }}
                >
                    <span className={`material-symbols-outlined transition-colors ${isDragging
                        ? 'text-[#00c2b2]'
                        : isReady
                            ? 'text-emerald-400'
                            : 'text-gray-400'
                        }`}>
                        {isReady ? 'check_circle' : 'upload_file'}
                    </span>
                </Motion.div>

                <p className={`text-sm font-medium mb-1 ${isReady ? 'text-emerald-400' : isDragging ? 'text-[#00c2b2]' : 'text-gray-300'
                    }`}>
                    {displayLabel}
                </p>
            </div>

            <AnimatePresence>
                {error && (
                    <Motion.p
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="absolute -bottom-6 left-0 right-0 text-center text-xs text-red-400"
                    >
                        {error}
                    </Motion.p>
                )}
            </AnimatePresence>
        </Motion.div>
    );
}
