/**
 * SOTA Interview Agent - Main Application
 * Routes: Onboarding → Dashboard → Command Center → Active Session → Session Report
 */

import { useEffect, useRef, useState } from 'react';
import { BrowserRouter, Routes, Route, useNavigate, Navigate } from 'react-router-dom';
import useInterviewStore, { APP_STATES } from '@/store/useInterviewStore';
import CommandCenter from '@/components/CommandCenter';
import InterviewView from '@/components/InterviewView';
import SessionReport from '@/components/SessionReport';
// import OnboardingFlow from '@/components/OnboardingFlow'; // Deprecated
import LoginScreen from '@/components/LoginScreen';
import SignupScreen from '@/components/SignupScreen';
import Dashboard from '@/components/Dashboard';
import './index.css';

// Route controller that handles navigation based on app state
function AppRouter() {
  const navigate = useNavigate();
  // Use reactive state from store instead of local useState
  const {
    connect,
    appState,
    setTargetJob,
    setTargetCompany,
    setFocusAreas,
    savePreferences,
    onboardingComplete
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
      console.warn('⚠️ Detected zombie interview state. Resetting.');
      useInterviewStore.setState({
        appState: mindmap ? APP_STATES.MAP_READY : APP_STATES.IDLE,
        analysisProgress: ''
      });
      navigate('/');
    }
  }, [navigate]);

  // Auto-navigate based on app state changes
  useEffect(() => {
    if (appState === APP_STATES.INTERVIEWING) {
      navigate('/session');
    } else if (appState === APP_STATES.COMPLETE || appState === 'complete') {
      navigate('/report');
    }
  }, [appState, navigate]);

  // Handle starting practice from dashboard
  const handleStartPractice = () => {
    navigate('/session');
  };

  // Handle viewing a session from dashboard
  const handleViewSession = (session) => {
    navigate('/session');
  };

  // Derived state to determine if we should show auth screens
  const showAuth = !onboardingComplete;

  return (
    <Routes>
      <Route path="/login" element={!showAuth ? <Navigate to="/dashboard" replace /> : <LoginScreen />} />
      <Route path="/signup" element={!showAuth ? <Navigate to="/dashboard" replace /> : <SignupScreen />} />

      {/* Protected Routes */}
      <Route path="/" element={
        showAuth ? <Navigate to="/login" replace /> : (
          <Dashboard
            onStartPractice={handleStartPractice}
            onViewSession={handleViewSession}
          />
        )
      } />

      <Route path="/dashboard" element={
        showAuth ? <Navigate to="/login" replace /> : (
          <Dashboard
            onStartPractice={handleStartPractice}
            onViewSession={handleViewSession}
          />
        )
      } />

      <Route path="/practice" element={showAuth ? <Navigate to="/login" replace /> : <CommandCenter />} />
      <Route path="/session" element={showAuth ? <Navigate to="/login" replace /> : <InterviewView />} />
      <Route path="/report" element={showAuth ? <Navigate to="/login" replace /> : <SessionReport />} />
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
