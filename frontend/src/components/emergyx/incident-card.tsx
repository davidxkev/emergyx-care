'use client';

import { AlertTriangle, Sparkles } from 'lucide-react';

import { Button } from '@/components/ui/button';
import type { AgentExplainResponse, IncidentContext } from '@/lib/types';
import { formatTimestamp, incidentTimeline } from '@/lib/format';

interface IncidentCardProps {
  incident: IncidentContext | null;
  explanation: AgentExplainResponse | null;
  loading: boolean;
  onExplain: () => Promise<void> | void;
}

export function IncidentCard({
  incident,
  explanation,
  loading,
  onExplain,
}: IncidentCardProps) {
  const steps = incidentTimeline(incident);

  return (
    <section className="rounded-2xl border border-border bg-card p-6 shadow-sm">
      <div className="flex flex-col gap-4 border-b border-border pb-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-amber-500/10 text-amber-600">
            <AlertTriangle className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-xl font-semibold tracking-tight">
              Incident Reconstruction
            </h2>
            <p className="text-sm text-muted-foreground">
              A calm, local explanation of the latest likely-fall event.
            </p>
          </div>
        </div>
        <Button variant="outline" onClick={() => void onExplain()} disabled={loading}>
          <Sparkles className="mr-2 h-4 w-4" />
          {loading ? 'Explaining…' : 'Explain latest incident'}
        </Button>
      </div>

      {incident ? (
        <div className="mt-6 space-y-4">
          {steps.map((step, index) => (
            <div key={step.label} className="flex gap-4">
              <div className="flex flex-col items-center">
                <div className="mt-1 h-3 w-3 rounded-full bg-primary" />
                {index < steps.length - 1 ? (
                  <div className="mt-2 h-full min-h-10 w-px bg-border" />
                ) : null}
              </div>
              <div className="pb-4">
                <p className="text-sm font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                  {step.label}
                </p>
                <p className="mt-1 text-base leading-7 text-foreground">
                  {step.value}
                </p>
              </div>
            </div>
          ))}

          {explanation ? (
            <div className="rounded-2xl border border-border bg-muted/40 p-4">
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-sm font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                  Gemma caregiver explanation
                </h3>
                <span className="text-xs text-muted-foreground">
                  {formatTimestamp(explanation.incident?.event?.timestamp ?? null)}
                </span>
              </div>
              <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-foreground">
                {explanation.explanation}
              </p>
            </div>
          ) : null}
        </div>
      ) : (
        <div className="mt-6 rounded-2xl border border-dashed border-border bg-muted/30 px-5 py-10 text-center">
          <p className="text-lg font-semibold">No likely-fall incident recorded</p>
          <p className="mt-2 text-sm text-muted-foreground">
            When a likely fall is detected, this timeline will show what happened
            before, during, and after the event.
          </p>
        </div>
      )}
    </section>
  );
}
