import React from 'react';
import { Check, Circle } from 'lucide-react';
import { useProject } from '../context/ProjectContext.js';
import { workflowSteps } from '../lib/workflow.js';

export const WorkflowStepper: React.FC = () => {
  const { documents, features, setActiveView } = useProject();
  const steps = workflowSteps(documents, features);

  return (
    <div className="px-6 py-2 border-b border-stone-200/50 dark:border-stone-850/50 bg-[var(--bg-app)] shrink-0" aria-label="Project workflow">
      <ol className="flex items-center gap-1 text-[11px] font-medium text-stone-500 dark:text-stone-400">
        {steps.map((step, i) => (
          <li key={step.id} className="flex items-center gap-1 min-w-0">
            {i > 0 && <span className="text-stone-300 dark:text-stone-700 px-1" aria-hidden>→</span>}
            <button
              type="button"
              onClick={() => setActiveView(step.view)}
              className={`inline-flex items-center gap-1 rounded-[var(--r-sm)] px-1.5 py-0.5 cursor-pointer ${
                step.state === 'current'
                  ? 'text-[var(--accent)]'
                  : step.state === 'done'
                    ? 'text-stone-700 dark:text-stone-200'
                    : 'text-stone-400'
              }`}
              aria-current={step.state === 'current' ? 'step' : undefined}
            >
              {step.state === 'done' ? (
                <Check className="w-3 h-3 text-[var(--verdict-new-txt)]" aria-hidden />
              ) : step.state === 'current' ? (
                <Circle className="w-2.5 h-2.5 fill-current" aria-hidden />
              ) : (
                <Circle className="w-2.5 h-2.5" aria-hidden />
              )}
              <span>{step.label}</span>
              <span className="sr-only">
                {step.state === 'done' ? 'complete' : step.state === 'current' ? 'current' : 'not started'}
              </span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
};
