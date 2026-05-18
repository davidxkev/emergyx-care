'use client';

import { memo } from 'react';
import { Activity, AlertTriangle, Moon, TrendingUp } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { formatTimestamp } from '@/lib/format';
import type { AgentTrendAnalysisResponse, TrendMetric, TrendsTodayResponse } from '@/lib/types';

function metricDelta(metric?: TrendMetric | null) {
  if (!metric) {
    return 'No baseline';
  }
  const sign = metric.delta > 0 ? '+' : '';
  return `${sign}${metric.delta.toFixed(2)} vs avg`;
}

function metricClass(metric?: TrendMetric | null) {
  if (!metric) {
    return 'text-muted-foreground';
  }
  if (metric.direction === 'up') {
    return 'text-amber-600 dark:text-amber-300';
  }
  if (metric.direction === 'down') {
    return 'text-teal-600 dark:text-teal-300';
  }
  return 'text-muted-foreground';
}

interface CareTrendsCardProps {
  trends: TrendsTodayResponse | null;
  analysis: AgentTrendAnalysisResponse | null;
  analyzing: boolean;
  error?: string | null;
  onAnalyze: () => void;
}

export const CareTrendsCard = memo(
  ({ trends, analysis, analyzing, error, onAnalyze }: CareTrendsCardProps) => {
    const fallMetric = trends?.metrics?.fall_count;
    const alertMetric = trends?.metrics?.alerts_sent;
    const nightMetric = trends?.metrics?.nighttime_movement_count;
    const newestChange = trends?.notable_changes?.[0];
    const analysisLabel = analysis
      ? analysis.used_mock
        ? 'Deterministic fallback'
        : `Gemma via ${analysis.model_name}`
      : null;

    return (
      <section className="rounded-2xl border border-border bg-card/75 p-5 shadow-sm sm:p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-blue-500/30 bg-blue-500/10 px-3 py-1 text-xs font-semibold text-blue-700 dark:text-blue-300">
              <TrendingUp className="h-3.5 w-3.5" />
              Care Trends
            </div>
            <h2 className="mt-3 text-xl font-bold sm:text-2xl">
              Today vs previous 7 days
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Local SQLite trend snapshot. Advisory context only.
            </p>
          </div>

          <Button
            onClick={onAnalyze}
            disabled={analyzing}
            type="button"
            className="self-start"
          >
            {analyzing ? 'Analyzing…' : 'Analyze trends with Gemma'}
          </Button>
        </div>

        <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="rounded-xl border border-border bg-background/70 p-3">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              Likely falls
            </p>
            <p className="mt-2 text-2xl font-bold">{fallMetric?.today ?? 0}</p>
            <p className={`text-xs ${metricClass(fallMetric)}`}>{metricDelta(fallMetric)}</p>
          </div>
          <div className="rounded-xl border border-border bg-background/70 p-3">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              Alerts sent
            </p>
            <p className="mt-2 text-2xl font-bold">{alertMetric?.today ?? 0}</p>
            <p className={`text-xs ${metricClass(alertMetric)}`}>{metricDelta(alertMetric)}</p>
          </div>
          <div className="rounded-xl border border-border bg-background/70 p-3">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              Night movement
            </p>
            <p className="mt-2 text-2xl font-bold">{nightMetric?.today ?? 0}</p>
            <p className={`text-xs ${metricClass(nightMetric)}`}>{metricDelta(nightMetric)}</p>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="rounded-xl border border-border bg-background/70 p-3 text-sm">
            <div className="flex items-center gap-2 font-semibold">
              <Moon className="h-4 w-4 text-amber-500" />
              Night window
            </div>
            <p className="mt-2 text-muted-foreground">
              {trends
                ? `${String(trends.night_window.start_hour).padStart(2, '0')}:00 to ${String(
                    trends.night_window.end_hour,
                  ).padStart(2, '0')}:00`
                : '22:00 to 06:00'}
            </p>
          </div>
          <div className="rounded-xl border border-border bg-background/70 p-3 text-sm">
            <div className="flex items-center gap-2 font-semibold">
              <Activity className="h-4 w-4 text-teal-500" />
              Last activity
            </div>
            <p className="mt-2 text-muted-foreground">
              {trends?.activity?.last_activity_age_human ?? 'No data'}
            </p>
            {trends?.activity?.last_activity_timestamp ? (
              <p className="text-xs text-muted-foreground">
                {formatTimestamp(trends.activity.last_activity_timestamp)}
              </p>
            ) : null}
          </div>
        </div>

        <div
          className={`mt-4 rounded-xl border px-3 py-2 text-sm ${
            trends?.unusual_detected
              ? 'border-amber-500/30 bg-amber-500/10'
              : 'border-border bg-background/70'
          }`}
        >
          <div className="flex items-start gap-2">
            <AlertTriangle
              className={`mt-0.5 h-4 w-4 ${
                trends?.unusual_detected ? 'text-amber-600 dark:text-amber-300' : 'text-muted-foreground'
              }`}
            />
            <div>
              <p className="font-semibold">
                {newestChange?.title ?? 'No unusual pattern detected'}
              </p>
              <p className="text-muted-foreground">{newestChange?.detail ?? 'Trend values are within normal variation.'}</p>
            </div>
          </div>
        </div>

        {analysis ? (
          <div className="mt-4 rounded-xl border border-border bg-background/70 p-3">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              {analysisLabel}
            </p>
            <p className="mt-2 text-sm leading-6">{analysis.analysis}</p>
          </div>
        ) : null}

        {error ? (
          <p className="mt-3 text-sm text-red-600 dark:text-red-300">{error}</p>
        ) : null}
      </section>
    );
  },
);

CareTrendsCard.displayName = 'CareTrendsCard';

