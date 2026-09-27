import React, { useState, useEffect } from 'react';
import { ArrowRight, Network, MessageSquare, ShieldCheck } from 'lucide-react';
import { createGuestProfile, createUserProfile, SessionProfile } from '../lib/session.js';

interface LandingPageProps {
  onEnter: (profile: SessionProfile) => void;
}

export const LandingPage: React.FC<LandingPageProps> = ({ onEnter }) => {
  const [mode, setMode] = useState<'signin' | 'signup'>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  // Match the app's theme (light default, unless an explicit dark choice is saved).
  useEffect(() => {
    let dark = false;
    try {
      dark = localStorage.getItem('dm-theme') === 'dark';
    } catch (e) {}
    document.documentElement.classList.toggle('dark', dark);
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onEnter(createUserProfile(email));
  };

  const handleGuest = () => {
    onEnter(createGuestProfile());
  };

  const features = [
    {
      icon: ShieldCheck,
      title: 'Catch duplicates & conflicts',
      body: 'Every new item is checked against your backlog and past decisions — with a cited verdict, never a silent guess.',
    },
    {
      icon: MessageSquare,
      title: 'Ask your project anything',
      body: 'Answers about why something was decided, drawn from meetings, tickets, and docs. Every claim is cited.',
    },
    {
      icon: Network,
      title: 'See what a change touches',
      body: 'Trace impact across items, decisions, and areas before you commit to a change.',
    },
  ];

  return (
    <div className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)] flex flex-col lg:flex-row">
      {/* Brand + description */}
      <div className="flex-1 flex flex-col justify-center px-8 py-12 lg:px-16">
        <div className="w-full max-w-xl mx-auto lg:mx-0">
          {/* Wordmark */}
          <div className="flex items-center gap-2.5 mb-10">
            <span className="w-9 h-9 grid place-items-center bg-[var(--accent)] text-white font-mono text-base rounded-[var(--r-md)] font-bold">
              A
            </span>
            <span className="font-sans font-semibold text-xl tracking-tight">Alpha Auctus</span>
          </div>

          <h1 className="text-3xl lg:text-4xl font-semibold tracking-tight leading-tight">
            The memory layer for your team's decisions.
          </h1>
          <p className="mt-4 text-base text-stone-600 dark:text-stone-300 leading-relaxed">
            Alpha Auctus turns a simple board into living memory. It flags duplicates and conflicts with
            past decisions as you work, answers questions about your project with citations, and
            shows what every change touches — so getting context takes minutes, not days.
          </p>

          <div className="mt-10 space-y-5">
            {features.map((f) => {
              const Icon = f.icon;
              return (
                <div key={f.title} className="flex items-start gap-3.5">
                  <span className="mt-0.5 w-8 h-8 shrink-0 grid place-items-center rounded-[var(--r-md)] bg-[var(--accent-bg)] text-[var(--accent)]">
                    <Icon className="w-4 h-4" />
                  </span>
                  <div>
                    <h3 className="text-sm font-semibold">{f.title}</h3>
                    <p className="text-[13px] text-stone-500 dark:text-stone-400 leading-relaxed mt-0.5">
                      {f.body}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Auth card */}
      <div className="lg:w-[460px] shrink-0 flex items-center justify-center px-8 py-12 bg-stone-50/70 dark:bg-stone-900/40 border-t lg:border-t-0 lg:border-l border-stone-200 dark:border-stone-850">
        <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-5">
          <div>
            <h2 className="text-xl font-semibold tracking-tight">
              {mode === 'signin' ? 'Sign in to Alpha Auctus' : 'Create your account'}
            </h2>
            <p className="text-xs text-stone-500 dark:text-stone-400 mt-1">
              {mode === 'signin'
                ? 'Welcome back. Pick up where your team left off.'
                : 'Start turning decisions into memory in minutes.'}
            </p>
          </div>

          <div className="space-y-3">
            <div>
              <label className="text-[11px] font-medium text-stone-500 dark:text-stone-400 block mb-1">
                Work email
              </label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                className="w-full bg-white dark:bg-stone-950 border border-stone-200 dark:border-stone-800 rounded-[var(--r-md)] px-3 py-2 text-sm text-stone-800 dark:text-stone-100 placeholder-stone-400 dark:placeholder-stone-500 focus:outline-none focus:border-[var(--accent)]"
              />
            </div>
            <div>
              <label className="text-[11px] font-medium text-stone-500 dark:text-stone-400 block mb-1">
                Password
              </label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full bg-white dark:bg-stone-950 border border-stone-200 dark:border-stone-800 rounded-[var(--r-md)] px-3 py-2 text-sm text-stone-800 dark:text-stone-100 placeholder-stone-400 dark:placeholder-stone-500 focus:outline-none focus:border-[var(--accent)]"
              />
            </div>
          </div>

          <button
            type="submit"
            className="w-full py-2.5 bg-[var(--accent)] text-white text-sm font-semibold rounded-[var(--r-md)] hover:opacity-95 active:scale-[.99] transition flex items-center justify-center gap-1.5 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]"
          >
            <span>{mode === 'signin' ? 'Sign in' : 'Sign up'}</span>
            <ArrowRight className="w-4 h-4" />
          </button>

          <button
            type="button"
            onClick={handleGuest}
            className="w-full py-2.5 bg-transparent text-sm font-semibold rounded-[var(--r-md)] border border-stone-200 dark:border-stone-800 text-stone-700 dark:text-stone-200 hover:bg-stone-100 dark:hover:bg-stone-900 active:scale-[.99] transition cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]"
          >
            Log in as guest
          </button>
          <p className="text-xs text-center text-stone-500 dark:text-stone-400">
            No email needed — for testing.
          </p>

          <p className="text-xs text-center text-stone-500 dark:text-stone-400">
            {mode === 'signin' ? "Don't have an account? " : 'Already have an account? '}
            <button
              type="button"
              onClick={() => setMode(mode === 'signin' ? 'signup' : 'signin')}
              className="text-[var(--accent)] font-semibold hover:underline cursor-pointer"
            >
              {mode === 'signin' ? 'Sign up' : 'Sign in'}
            </button>
          </p>
        </form>
      </div>
    </div>
  );
};
