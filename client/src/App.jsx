/**
 * Interview Prep v0 - Main Application
 * Routes: Configuration -> Interviews -> Session -> Report
 */

import { useEffect, useRef } from 'react';
import { BrowserRouter, Routes, Route, useNavigate, Navigate, useLocation } from 'react-router-dom';
import useInterviewStore, { APP_STATES } from '@/store/useInterviewStore';
import InterviewView from '@/components/InterviewView';
import SessionReport from '@/components/SessionReport';
import HistoryView from '@/components/HistoryView';
import ConfigurationView from '@/components/ConfigurationView';
// import OnboardingFlow from '@/components/OnboardingFlow'; // Deprecated
import LoginScreen from '@/components/LoginScreen';
import SignupScreen from '@/components/SignupScreen';
import V0Setup from '@/components/V0Setup';
import './index.css';

// Route controller that handles navigation based on app state
function AppRouter() {
  const navigate = useNavigate();
  const location = useLocation();
  // Use reactive state from store instead of local useState
  const {
    connect,
    appState,
    onboardingComplete,
    sessionToken,
    targetRole,
    jobDescription,
    skillMapping,
    readinessScore,
  } = useInterviewStore();

  const hasCheckedZombie = useRef(false);

  // Connect to Socket.IO on mount
  useEffect(() => {
    connect();
  }, [connect]);

  // Check for zombie state only on initial mount (page refresh)
  useEffect(() => {
    if (hasCheckedZombie.current) return;
    hasCheckedZombie.current = true;

    const { interviewActive, mindmap, appState: currentState } = useInterviewStore.getState();

    // Only check for zombie INTERVIEWING state (user refreshed during interview)
    const isZombieInterview = currentState === APP_STATES.INTERVIEWING && !interviewActive;

    if (isZombieInterview) {
      useInterviewStore.setState({
        appState: mindmap ? APP_STATES.MAP_READY : APP_STATES.IDLE,
        analysisProgress: ''
      });
      navigate('/interviews');
    }
  }, [navigate]);

  // Auto-navigate based on app state changes
  useEffect(() => {
    if (appState === APP_STATES.INTERVIEWING) {
      navigate('/session');
    } else if (
      (appState === APP_STATES.COMPLETE || appState === 'complete') &&
      location.pathname === '/session'
    ) {
      navigate('/report');
    }
  }, [appState, navigate, location.pathname]);

  // Show auth screens whenever there is no authenticated/restoreable session.
  const showAuth = !(Boolean(onboardingComplete) || Boolean(sessionToken));
  const hasConfigSeed = Boolean(String(targetRole || '').trim() && String(jobDescription || '').trim());
  const hasAnalysisData =
    Boolean(skillMapping && typeof skillMapping === 'object') ||
    Number.isFinite(Number(readinessScore)) && Number(readinessScore) > 0;
  const defaultAuthedRoute = (hasConfigSeed || hasAnalysisData) ? '/interviews' : '/config';

  return (
    <Routes>
      <Route path="/login" element={!showAuth ? <Navigate to="/" replace /> : <LoginScreen />} />
      <Route path="/signup" element={!showAuth ? <Navigate to="/" replace /> : <SignupScreen />} />

      {/* Protected Routes */}
      <Route path="/" element={
        showAuth ? <Navigate to="/login" replace /> : <Navigate to={defaultAuthedRoute} replace />
      } />

      <Route path="/interviews" element={showAuth ? <Navigate to="/login" replace /> : <V0Setup />} />
      <Route path="/config" element={showAuth ? <Navigate to="/login" replace /> : <ConfigurationView />} />
      <Route path="/setup" element={<Navigate to="/interviews" replace />} />
      <Route path="/dashboard" element={<Navigate to="/interviews" replace />} />
      <Route path="/rounds" element={<Navigate to="/" replace />} />
      <Route path="/improve" element={<Navigate to="/" replace />} />
      <Route path="/practice" element={<Navigate to="/interviews" replace />} />
      <Route path="/session" element={showAuth ? <Navigate to="/login" replace /> : <InterviewView />} />
      <Route path="/report" element={showAuth ? <Navigate to="/login" replace /> : <SessionReport />} />
      <Route path="/history" element={showAuth ? <Navigate to="/login" replace /> : <HistoryView />} />
      <Route path="/settings" element={showAuth ? <Navigate to="/login" replace /> : <Navigate to="/config" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AppRouter />
    </BrowserRouter>
  );
}

export default App;
