import { useEffect, useMemo, useRef, useState } from 'react';
import { Joyride, STATUS } from 'react-joyride';
import useInterviewStore from '@/store/useInterviewStore';

function readTourFlagFromStorage(userId) {
    try {
        const normalizedUserId = String(userId || '').trim() || 'anonymous';
        return localStorage.getItem(`beePrepared.hasSeenTour:${normalizedUserId}`) === 'true';
    } catch {
        return false;
    }
}

export default function TourGuide() {
    const { setHasSeenTour, darkMode, onboardingComplete, hasSeenTour, userId } = useInterviewStore();
    const started = useRef(false);
    const previousUserId = useRef('');
    const persistedForCurrentRun = useRef(false);
    const [run, setRun] = useState(false);

    const skip = useMemo(
        () => hasSeenTour || readTourFlagFromStorage(userId),
        [hasSeenTour, userId],
    );

    useEffect(() => {
        const normalizedUserId = String(userId || '').trim();
        if (previousUserId.current === normalizedUserId) return;

        console.log('[TourDebug] user changed', {
            previousUserId: previousUserId.current,
            nextUserId: normalizedUserId,
        });
        previousUserId.current = normalizedUserId;
        started.current = false;
        persistedForCurrentRun.current = false;
        setRun(false);
    }, [userId]);

    useEffect(() => {
        if (onboardingComplete) return;

        console.log('[TourDebug] onboarding reset', { onboardingComplete });
        started.current = false;
        persistedForCurrentRun.current = false;
        setRun(false);
    }, [onboardingComplete]);

    useEffect(() => {
        console.log('[TourDebug] render state', {
            userId,
            onboardingComplete,
            hasSeenTour,
            skip,
            run,
            started: started.current,
        });
    }, [hasSeenTour, onboardingComplete, run, skip, userId]);

    useEffect(() => {
        if (!run || persistedForCurrentRun.current) return;

        console.log('[TourDebug] marking seen because tour opened', { userId });
        persistedForCurrentRun.current = true;
        setHasSeenTour(true);
    }, [run, setHasSeenTour, userId]);

    useEffect(() => {
        if (!onboardingComplete) {
            console.log('[TourDebug] not starting: onboarding incomplete', { userId });
            return;
        }
        if (skip) {
            console.log('[TourDebug] not starting: already seen', { userId, hasSeenTour, skip });
            return;
        }
        if (started.current) {
            console.log('[TourDebug] not starting: already started in this mount', { userId });
            return;
        }

        console.log('[TourDebug] starting tour', { userId });
        started.current = true;
        setTimeout(() => setRun(true), 500);
    }, [onboardingComplete, skip, userId]);

    const handleJoyrideCallback = (data) => {
        console.log('[TourDebug] joyride callback', data);
        if ([STATUS.FINISHED, STATUS.SKIPPED].includes(data.status)) {
            setHasSeenTour(true);
            setRun(false);
        }
    };

    if (!run) return null;

    return (
        <Joyride
            callback={handleJoyrideCallback}
            continuous
            run={run}
            scrollToFirstStep
            showProgress
            showSkipButton
            steps={[
                {
                    target: 'body',
                    content: 'Welcome to BeePrepared! Let us show you around quickly.',
                    placement: 'center',
                },
                {
                    target: '#nav-config',
                    content: 'First stop: Setup your Profile. Tell us your target role and paste your resume for a tuned mock interview.',
                    placement: 'bottom',
                },
                {
                    target: '#nav-interviews',
                    content: 'Your Dashboard. From here you can check your skills gaps and start customized mock sessions.',
                    placement: 'bottom',
                },
                {
                    target: '#nav-history',
                    content: 'After your interview, review past recordings and detailed performance metrics here. Good luck!',
                    placement: 'bottom',
                },
            ]}
            styles={{
                options: {
                    zIndex: 10000,
                    primaryColor: '#6366f1',
                    textColor: darkMode ? '#fed7aa' : '#333333',
                    backgroundColor: darkMode ? '#1f1f1f' : '#ffffff',
                    arrowColor: darkMode ? '#1f1f1f' : '#ffffff',
                },
                tooltipContainer: { textAlign: 'left' },
            }}
        />
    );
}
