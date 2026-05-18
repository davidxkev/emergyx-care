'use client';

import { FileText } from 'lucide-react';

import { Button } from '@/components/ui/button';
import type { DailyReportRead } from '@/lib/types';
import { formatTimestamp } from '@/lib/format';

interface ReportCardProps {
  report: DailyReportRead | null;
  loading: boolean;
  onGenerate: () => Promise<void> | void;
}

export function ReportCard({ report, loading, onGenerate }: ReportCardProps) {
  return (
    <section className="rounded-2xl border border-border bg-card p-6 shadow-sm">
      <div className="flex flex-col gap-4 border-b border-border pb-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-emerald-500/10 text-emerald-600">
            <FileText className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-xl font-semibold tracking-tight">
              Daily Caregiver Report
            </h2>
            <p className="text-sm text-muted-foreground">
              Generate a calm handoff summary from the local care timeline.
            </p>
          </div>
        </div>
        <Button onClick={() => void onGenerate()} disabled={loading}>
          {loading ? 'Generating…' : 'Generate daily report'}
        </Button>
      </div>

      {report ? (
        <div className="mt-6 rounded-2xl bg-muted/30 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                Latest report
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                Generated {formatTimestamp(report.created_at)}
              </p>
            </div>
            <span className="rounded-full bg-background px-3 py-1 text-xs text-muted-foreground shadow-sm">
              {report.date}
            </span>
          </div>
          <p className="mt-4 whitespace-pre-wrap text-sm leading-7 text-foreground">
            {report.report_text}
          </p>
        </div>
      ) : (
        <div className="mt-6 rounded-2xl border border-dashed border-border bg-muted/30 px-5 py-10 text-center">
          <p className="text-lg font-semibold">No report generated yet</p>
          <p className="mt-2 text-sm text-muted-foreground">
            Generate today’s caregiver report from the local care timeline.
          </p>
        </div>
      )}
    </section>
  );
}
