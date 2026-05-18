'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import {
  AlertCircle,
  BarChart3,
  ChevronDown,
  ChevronRight,
  Download,
  FileText,
  Loader2,
  Sparkles,
  TrendingUp,
} from 'lucide-react';

import { AdminSidebar } from '@/components/ui/admin-sidebar';
import { Button } from '@/components/ui/button';
import { DashboardHeader } from '@/components/ui/dashboard-header';
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar';
import {
  analyzeTrends,
  downloadWeeklyReportPdf,
  generateDailyReport,
  generateWeeklyReportPdf,
  getGemmaFindings,
  getReportSchedule,
  getReports,
  getTrendsToday,
  getTrendsWeek,
  getWeeklyReports,
  runDemoScenario,
  runGemmaPatternScan,
  testReportScheduleTelegram,
  updateReportSchedule,
} from '@/lib/api';
import { formatTimestamp } from '@/lib/format';
import { loadNightWindowPreference } from '@/lib/trends';
import type {
  AgentTrendAnalysisResponse,
  DailyReportRead,
  GemmaFindingRead,
  Mode,
  ReportScheduleRead,
  TrendsTodayResponse,
  TrendsWeekResponse,
  WeeklyReportRead,
} from '@/lib/types';

const WEEK_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

function metricValue(trends: TrendsTodayResponse | null, key: string) {
  return trends?.metrics?.[key]?.today ?? 0;
}

function metricDelta(trends: TrendsTodayResponse | null, key: string) {
  const metric = trends?.metrics?.[key];
  if (!metric) {
    return 'No baseline yet';
  }
  const sign = metric.delta > 0 ? '+' : '';
  return `${sign}${metric.delta.toFixed(2)} vs baseline`;
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function dateRangeLabel(report: WeeklyReportRead) {
  return `${report.start_date} to ${report.end_date}`;
}

export function ReportsDashboard() {
  const searchParams = useSearchParams();
  const mode: Mode = searchParams.get('mode') === 'demo' ? 'demo' : 'live';
  const [searchQuery, setSearchQuery] = useState('');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [dailyReports, setDailyReports] = useState<DailyReportRead[]>([]);
  const [weeklyReports, setWeeklyReports] = useState<WeeklyReportRead[]>([]);
  const [gemmaFindings, setGemmaFindings] = useState<GemmaFindingRead[]>([]);
  const [todayTrends, setTodayTrends] = useState<TrendsTodayResponse | null>(null);
  const [weekTrends, setWeekTrends] = useState<TrendsWeekResponse | null>(null);
  const [schedule, setSchedule] = useState<ReportScheduleRead | null>(null);
  const [dailyEnabled, setDailyEnabled] = useState(false);
  const [dailyTime, setDailyTime] = useState('20:00');
  const [dailyTelegram, setDailyTelegram] = useState(false);
  const [weeklyEnabled, setWeeklyEnabled] = useState(false);
  const [weeklyDay, setWeeklyDay] = useState(0);
  const [weeklyTime, setWeeklyTime] = useState('09:00');
  const [weeklyTelegram, setWeeklyTelegram] = useState(false);
  const [patternEnabled, setPatternEnabled] = useState(true);
  const [patternIntervalMinutes, setPatternIntervalMinutes] = useState(60);
  const [patternTelegram, setPatternTelegram] = useState(false);
  const [trendAnalysis, setTrendAnalysis] = useState<AgentTrendAnalysisResponse | null>(null);
  const [expandedDaily, setExpandedDaily] = useState<Record<number, boolean>>({});
  const [generatingDaily, setGeneratingDaily] = useState(false);
  const [generatingWeekly, setGeneratingWeekly] = useState(false);
  const [downloadingWeeklyId, setDownloadingWeeklyId] = useState<number | null>(null);
  const [analyzingTrends, setAnalyzingTrends] = useState(false);
  const [scanningPatterns, setScanningPatterns] = useState(false);
  const [savingSchedule, setSavingSchedule] = useState(false);
  const [testingTelegramReport, setTestingTelegramReport] = useState<'daily' | 'weekly' | null>(null);
  const [runningScenario, setRunningScenario] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  const loadReports = useCallback(async () => {
    const nightWindow = loadNightWindowPreference();
    const [dailyPayload, weeklyPayload, findingPayload, todayPayload, weekPayload, schedulePayload] = await Promise.all([
      getReports(mode, 20),
      getWeeklyReports(mode, 20),
      getGemmaFindings(mode, 20),
      getTrendsToday(mode, {
        nightStartHour: nightWindow.startHour,
        nightEndHour: nightWindow.endHour,
      }),
      getTrendsWeek(mode, {
        nightStartHour: nightWindow.startHour,
        nightEndHour: nightWindow.endHour,
      }),
      getReportSchedule(),
    ]);
    setDailyReports(dailyPayload);
    setWeeklyReports(weeklyPayload);
    setGemmaFindings(findingPayload);
    setTodayTrends(todayPayload);
    setWeekTrends(weekPayload);
    setSchedule(schedulePayload);
    setDailyEnabled(schedulePayload.daily_enabled);
    setDailyTime(schedulePayload.daily_time);
    setDailyTelegram(schedulePayload.daily_send_telegram);
    setWeeklyEnabled(schedulePayload.weekly_enabled);
    setWeeklyDay(schedulePayload.weekly_day);
    setWeeklyTime(schedulePayload.weekly_time);
    setWeeklyTelegram(schedulePayload.weekly_send_telegram);
    setPatternEnabled(schedulePayload.pattern_enabled);
    setPatternIntervalMinutes(schedulePayload.pattern_interval_minutes);
    setPatternTelegram(schedulePayload.pattern_send_telegram);
  }, [mode]);

  useEffect(() => {
    let cancelled = false;
    async function run() {
      try {
        setIsRefreshing(true);
        setError(null);
        await loadReports();
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : 'Unable to load reports.');
        }
      } finally {
        if (!cancelled) {
          setIsRefreshing(false);
        }
      }
    }
    void run();
    return () => {
      cancelled = true;
    };
  }, [loadReports]);

  const filteredDailyReports = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) {
      return dailyReports;
    }
    return dailyReports.filter((report) =>
      `${report.date} ${report.created_at} ${report.report_text}`.toLowerCase().includes(query),
    );
  }, [dailyReports, searchQuery]);

  const filteredWeeklyReports = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) {
      return weeklyReports;
    }
    return weeklyReports.filter((report) =>
      `${report.start_date} ${report.end_date} ${report.created_at} ${report.filename} ${report.model_name}`
        .toLowerCase()
        .includes(query),
    );
  }, [weeklyReports, searchQuery]);

  const refreshReports = async () => {
    try {
      setIsRefreshing(true);
      setError(null);
      await loadReports();
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : 'Unable to refresh reports.');
    } finally {
      setIsRefreshing(false);
    }
  };

  const exportReportIndex = () => {
    const payload = {
      exported_at: new Date().toISOString(),
      daily_reports: dailyReports,
      weekly_reports: weeklyReports,
      gemma_findings: gemmaFindings,
      today_trends: todayTrends,
      week_trends: weekTrends,
      trend_analysis: trendAnalysis,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: 'application/json;charset=utf-8',
    });
    downloadBlob(blob, 'emergyx-reports-index.json');
  };

  const handleGenerateDaily = async () => {
    try {
      setGeneratingDaily(true);
      setError(null);
      const result = await generateDailyReport(mode, { requireGemma: true });
      setFeedback(`Gemma daily report generated for ${result.date} with ${result.model_name}.`);
      await loadReports();
    } catch (dailyError) {
      setError(dailyError instanceof Error ? dailyError.message : 'Unable to generate daily report.');
    } finally {
      setGeneratingDaily(false);
    }
  };

  const handleGenerateWeekly = async () => {
    try {
      setGeneratingWeekly(true);
      setError(null);
      const nightWindow = loadNightWindowPreference();
      const result = await generateWeeklyReportPdf(mode, {
        nightStartHour: nightWindow.startHour,
        nightEndHour: nightWindow.endHour,
      });
      downloadBlob(result.blob, result.filename);
      setFeedback(
        `Gemma weekly PDF generated with ${result.modelName ?? 'Gemma 4 E2B'}, saved, and downloaded.`,
      );
      await loadReports();
    } catch (weeklyError) {
      setError(weeklyError instanceof Error ? weeklyError.message : 'Unable to generate weekly PDF.');
    } finally {
      setGeneratingWeekly(false);
    }
  };

  const handleDownloadWeekly = async (report: WeeklyReportRead) => {
    try {
      setDownloadingWeeklyId(report.id);
      setError(null);
      const result = await downloadWeeklyReportPdf(report.id);
      downloadBlob(result.blob, result.filename);
    } catch (downloadError) {
      setError(downloadError instanceof Error ? downloadError.message : 'Unable to download weekly PDF.');
    } finally {
      setDownloadingWeeklyId(null);
    }
  };

  const handleAnalyzeTrends = async () => {
    try {
      setAnalyzingTrends(true);
      setError(null);
      const nightWindow = loadNightWindowPreference();
      const result = await analyzeTrends(mode, {
        nightStartHour: nightWindow.startHour,
        nightEndHour: nightWindow.endHour,
      });
      setTrendAnalysis(result);
      if (result.trends) {
        setTodayTrends(result.trends);
      }
      setFeedback('Trend analysis updated.');
    } catch (analysisError) {
      setError(analysisError instanceof Error ? analysisError.message : 'Unable to analyze trends.');
    } finally {
      setAnalyzingTrends(false);
    }
  };

  const handleSaveSchedule = async () => {
    try {
      setSavingSchedule(true);
      setError(null);
      const result = await updateReportSchedule({
        daily_enabled: dailyEnabled,
        daily_time: dailyTime,
        daily_send_telegram: dailyTelegram,
      weekly_enabled: weeklyEnabled,
      weekly_day: weeklyDay,
      weekly_time: weeklyTime,
      weekly_send_telegram: weeklyTelegram,
      pattern_enabled: patternEnabled,
      pattern_interval_minutes: patternIntervalMinutes,
      pattern_send_telegram: patternTelegram,
    });
      setSchedule(result);
      setFeedback('Report schedule saved.');
    } catch (scheduleError) {
      setError(scheduleError instanceof Error ? scheduleError.message : 'Unable to save report schedule.');
    } finally {
      setSavingSchedule(false);
    }
  };

  const handleRunPatternScan = async () => {
    try {
      setScanningPatterns(true);
      setError(null);
      const nightWindow = loadNightWindowPreference();
      const result = await runGemmaPatternScan(mode, {
        sendTelegram: patternTelegram,
        nightStartHour: nightWindow.startHour,
        nightEndHour: nightWindow.endHour,
      });
      setFeedback(
        `Gemma pattern scan complete: ${result.findings.length} new finding${result.findings.length === 1 ? '' : 's'}, ${result.alerts_created} alert${result.alerts_created === 1 ? '' : 's'} created.`,
      );
      await loadReports();
    } catch (scanError) {
      setError(scanError instanceof Error ? scanError.message : 'Unable to run Gemma pattern scan.');
    } finally {
      setScanningPatterns(false);
    }
  };

  const handleDemoScenario = async (scenario: 'fall' | 'vitals-change' | 'night-activity' | 'pattern-scan' | 'reset') => {
    try {
      setRunningScenario(scenario);
      setError(null);
      const result = await runDemoScenario(scenario);
      setFeedback(`${result.scenario} scenario complete. ${result.next_step}`);
      await loadReports();
    } catch (scenarioError) {
      setError(scenarioError instanceof Error ? scenarioError.message : 'Unable to run demo scenario.');
    } finally {
      setRunningScenario(null);
    }
  };

  const handleTestTelegramReport = async (reportType: 'daily' | 'weekly') => {
    try {
      setTestingTelegramReport(reportType);
      setError(null);
      const result = await testReportScheduleTelegram(reportType);
      setFeedback(result.message);
      await loadReports();
    } catch (testError) {
      setError(testError instanceof Error ? testError.message : 'Unable to send report to Telegram.');
    } finally {
      setTestingTelegramReport(null);
    }
  };

  const latestWeekly = weeklyReports[0];
  const latestDaily = dailyReports[0];
  const latestFinding = gemmaFindings[0];
  const latestChange = todayTrends?.notable_changes?.[0];

  return (
    <SidebarProvider>
      <AdminSidebar />
      <SidebarInset>
        <DashboardHeader
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          onRefresh={() => void refreshReports()}
          onExport={exportReportIndex}
          isRefreshing={isRefreshing}
          searchPlaceholder="Search reports, dates, or trend analysis..."
        />

        <div className="flex flex-1 flex-col gap-2 bg-[radial-gradient(circle_at_top_left,rgba(37,99,235,0.08),transparent_32rem),linear-gradient(180deg,var(--background),rgba(241,245,249,0.72))] p-2 pt-0 sm:gap-4 sm:p-4 dark:bg-[radial-gradient(circle_at_top_left,rgba(59,130,246,0.18),transparent_30rem),linear-gradient(180deg,var(--background),#09090b)]">
          <div className="min-h-[calc(100vh-4rem)] flex-1 rounded-lg p-3 sm:rounded-xl sm:p-4 md:p-6">
            <div className="mx-auto max-w-7xl space-y-6">
              <section className="overflow-hidden rounded-3xl border border-border bg-card/80 p-6 shadow-sm md:p-8">
                <div className="flex flex-col justify-between gap-6 lg:flex-row lg:items-start">
                  <div>
                    <p className="text-xs font-bold uppercase tracking-[0.22em] text-blue-600 dark:text-blue-300">
                      Reports
                    </p>
                    <h1 className="mt-3 text-3xl font-bold tracking-tight md:text-4xl">
                      Care Intelligence Reports
                    </h1>
                    <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground md:text-base">
                      Generate Gemma caregiver summaries, save weekly safety PDFs
                      using the same Gemma 4 E2B flow as the dashboard, and analyze
                      {mode === 'demo' ? ' seeded judge-demo trends' : ' live-mode trends'} from local data.
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button disabled={generatingDaily} onClick={() => void handleGenerateDaily()} type="button">
                      {generatingDaily ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
                      Gemma daily report
                    </Button>
                    <Button disabled={generatingWeekly} onClick={() => void handleGenerateWeekly()} type="button" variant="outline">
                      {generatingWeekly ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                      Gemma weekly PDF
                    </Button>
                  </div>
                </div>
              </section>

              {error ? (
                <div className="flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>{error}</span>
                </div>
              ) : null}
              {feedback ? (
                <div className="rounded-2xl border border-border bg-card px-4 py-3 text-sm font-medium">
                  {feedback}
                </div>
              ) : null}

              <section className="grid gap-4 md:grid-cols-4">
                <article className="rounded-2xl border border-border bg-card/75 p-5 shadow-sm">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Latest daily</p>
                  <p className="mt-2 text-2xl font-bold">{latestDaily?.date ?? 'None'}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{latestDaily ? formatTimestamp(latestDaily.created_at) : `Generate one from ${mode} data`}</p>
                </article>
                <article className="rounded-2xl border border-border bg-card/75 p-5 shadow-sm">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Latest weekly</p>
                  <p className="mt-2 text-2xl font-bold">{latestWeekly ? dateRangeLabel(latestWeekly) : 'None'}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{latestWeekly ? latestWeekly.model_name : 'Generate a weekly PDF'}</p>
                </article>
                <article className="rounded-2xl border border-border bg-card/75 p-5 shadow-sm">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Likely falls today</p>
                  <p className="mt-2 text-2xl font-bold">{metricValue(todayTrends, 'fall_count')}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{metricDelta(todayTrends, 'fall_count')}</p>
                </article>
                <article className="rounded-2xl border border-border bg-card/75 p-5 shadow-sm">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Night movement</p>
                  <p className="mt-2 text-2xl font-bold">{metricValue(todayTrends, 'nighttime_movement_count')}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{metricDelta(todayTrends, 'nighttime_movement_count')}</p>
                </article>
              </section>

              {mode === 'demo' ? (
                <section className="rounded-3xl border border-border bg-card/75 p-6 shadow-sm">
                  <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
                    <div>
                      <h2 className="text-2xl font-bold">Judge demo controls</h2>
                      <p className="mt-1 text-sm text-muted-foreground">
                        Trigger reproducible demo scenarios without real sensors or Telegram credentials.
                      </p>
                    </div>
                  </div>
                  <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
                    {[
                      ['fall', 'Likely fall'],
                      ['vitals-change', 'Vitals change'],
                      ['night-activity', 'Night activity'],
                      ['pattern-scan', 'Gemma scan'],
                      ['reset', 'Reset demo'],
                    ].map(([scenario, label]) => (
                      <Button
                        disabled={runningScenario !== null}
                        key={scenario}
                        onClick={() => void handleDemoScenario(scenario as 'fall' | 'vitals-change' | 'night-activity' | 'pattern-scan' | 'reset')}
                        type="button"
                        variant={scenario === 'reset' ? 'outline' : 'default'}
                      >
                        {runningScenario === scenario ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                        {label}
                      </Button>
                    ))}
                  </div>
                </section>
              ) : null}

              <section className="rounded-3xl border border-border bg-card/75 p-6 shadow-sm">
                <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
                  <div>
                    <div className="inline-flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-700 dark:text-emerald-300">
                      <Sparkles className="h-3.5 w-3.5" />
                      Gemma Pattern Monitor
                    </div>
                    <h2 className="mt-3 text-2xl font-bold">Autonomous findings</h2>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Gemma scans local sensor trends, vitals, incidents, and resident context. Medium/high findings can create dashboard alerts and optional Telegram notifications.
                    </p>
                    {latestFinding ? (
                      <p className="mt-3 text-sm">
                        Latest finding: <span className="font-semibold">{latestFinding.title}</span>{' '}
                        <span className="text-muted-foreground">({formatTimestamp(latestFinding.created_at)})</span>
                      </p>
                    ) : (
                      <p className="mt-3 text-sm text-muted-foreground">No Gemma findings saved yet.</p>
                    )}
                  </div>
                  <Button disabled={scanningPatterns} onClick={() => void handleRunPatternScan()} type="button">
                    {scanningPatterns ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                    Run pattern scan
                  </Button>
                </div>

                <div className="mt-5 space-y-3">
                  {gemmaFindings.length ? (
                    gemmaFindings.slice(0, 5).map((finding) => (
                      <div className="rounded-2xl border border-border bg-background/70 p-4" key={finding.id}>
                        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
                          <div>
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-semibold">{finding.title}</span>
                              <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                                finding.severity === 'high'
                                  ? 'bg-red-500/10 text-red-700 dark:text-red-300'
                                  : finding.severity === 'medium'
                                    ? 'bg-amber-500/10 text-amber-700 dark:text-amber-300'
                                    : 'bg-blue-500/10 text-blue-700 dark:text-blue-300'
                              }`}>
                                {finding.severity}
                              </span>
                              {finding.alert_id ? (
                                <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-semibold text-primary">
                                  alert #{finding.alert_id}
                                </span>
                              ) : null}
                            </div>
                            <p className="mt-2 text-sm leading-6 text-muted-foreground">{finding.summary}</p>
                            {finding.caregiver_action ? (
                              <p className="mt-2 text-sm">
                                <span className="font-semibold">Recommended action:</span> {finding.caregiver_action}
                              </p>
                            ) : null}
                          </div>
                          <div className="shrink-0 text-xs text-muted-foreground">
                            <p>{finding.pattern_type.replace(/_/g, ' ')}</p>
                            <p>{finding.model_name}</p>
                          </div>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="rounded-2xl border border-dashed border-border bg-background/70 p-8 text-center text-sm text-muted-foreground">
                      Run a Gemma pattern scan to create persistent findings.
                    </div>
                  )}
                </div>
              </section>

              <section className="rounded-3xl border border-border bg-card/75 p-6 shadow-sm">
                <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
                  <div>
                    <h2 className="text-2xl font-bold">Report Schedule</h2>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Cron-style report automation while the local FastAPI server is running.
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={`rounded-full border px-3 py-1 text-xs font-semibold ${
                        schedule?.scheduler_running
                          ? 'border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-300'
                          : 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300'
                      }`}
                    >
                      {schedule?.scheduler_running ? 'Scheduler running' : 'Scheduler not running'}
                    </span>
                    <Button disabled={savingSchedule} onClick={() => void handleSaveSchedule()} type="button">
                      {savingSchedule ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                      Save schedule
                    </Button>
                  </div>
                </div>

                <div className="mt-5 grid gap-4 xl:grid-cols-3">
                  <div className="rounded-2xl border border-border bg-background/70 p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="font-semibold">Daily report</p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          Generates today&apos;s {mode} caregiver report.
                        </p>
                      </div>
                      <label className="flex items-center gap-2 text-sm">
                        <input
                          checked={dailyEnabled}
                          onChange={(event) => setDailyEnabled(event.target.checked)}
                          type="checkbox"
                        />
                        Enabled
                      </label>
                    </div>
                    <div className="mt-4 grid gap-3 sm:grid-cols-2">
                      <label className="space-y-1">
                        <span className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                          Time
                        </span>
                        <input
                          className="h-10 w-full rounded-xl border border-border bg-card px-3 text-sm"
                          onChange={(event) => setDailyTime(event.target.value)}
                          type="time"
                          value={dailyTime}
                        />
                      </label>
                      <label className="mt-6 flex items-center gap-2 text-sm sm:mt-7">
                        <input
                          checked={dailyTelegram}
                          onChange={(event) => setDailyTelegram(event.target.checked)}
                          type="checkbox"
                        />
                        Send in Telegram
                      </label>
                    </div>
                    <p className="mt-3 text-xs text-muted-foreground">
                      Last daily run: {schedule?.last_daily_run_date ?? 'not yet'}
                    </p>
                    <Button
                      className="mt-3"
                      disabled={testingTelegramReport !== null}
                      onClick={() => void handleTestTelegramReport('daily')}
                      size="sm"
                      type="button"
                      variant="outline"
                    >
                      {testingTelegramReport === 'daily' ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                      Test Telegram daily
                    </Button>
                  </div>

                  <div className="rounded-2xl border border-border bg-background/70 p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="font-semibold">Weekly report</p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          Generates and saves the weekly PDF.
                        </p>
                      </div>
                      <label className="flex items-center gap-2 text-sm">
                        <input
                          checked={weeklyEnabled}
                          onChange={(event) => setWeeklyEnabled(event.target.checked)}
                          type="checkbox"
                        />
                        Enabled
                      </label>
                    </div>
                    <div className="mt-4 grid gap-3 sm:grid-cols-3">
                      <label className="space-y-1">
                        <span className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                          Day
                        </span>
                        <select
                          className="h-10 w-full rounded-xl border border-border bg-card px-3 text-sm"
                          onChange={(event) => setWeeklyDay(Number.parseInt(event.target.value, 10))}
                          value={weeklyDay}
                        >
                          {WEEK_DAYS.map((day, index) => (
                            <option key={day} value={index}>
                              {day}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="space-y-1">
                        <span className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                          Time
                        </span>
                        <input
                          className="h-10 w-full rounded-xl border border-border bg-card px-3 text-sm"
                          onChange={(event) => setWeeklyTime(event.target.value)}
                          type="time"
                          value={weeklyTime}
                        />
                      </label>
                      <label className="mt-6 flex items-center gap-2 text-sm sm:mt-7">
                        <input
                          checked={weeklyTelegram}
                          onChange={(event) => setWeeklyTelegram(event.target.checked)}
                          type="checkbox"
                        />
                        Send in Telegram
                      </label>
                    </div>
                    <p className="mt-3 text-xs text-muted-foreground">
                      Last weekly run: {schedule?.last_weekly_run_key ?? 'not yet'}
                    </p>
                    <Button
                      className="mt-3"
                      disabled={testingTelegramReport !== null}
                      onClick={() => void handleTestTelegramReport('weekly')}
                      size="sm"
                      type="button"
                      variant="outline"
                    >
                      {testingTelegramReport === 'weekly' ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                      Test Telegram weekly PDF
                    </Button>
                  </div>

                  <div className="rounded-2xl border border-border bg-background/70 p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="font-semibold">Gemma pattern monitor</p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          Automatically detects trends and creates findings/alerts.
                        </p>
                      </div>
                      <label className="flex items-center gap-2 text-sm">
                        <input
                          checked={patternEnabled}
                          onChange={(event) => setPatternEnabled(event.target.checked)}
                          type="checkbox"
                        />
                        Enabled
                      </label>
                    </div>
                    <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
                      <label className="space-y-1">
                        <span className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                          Interval
                        </span>
                        <select
                          className="h-10 w-full rounded-xl border border-border bg-card px-3 text-sm"
                          onChange={(event) => setPatternIntervalMinutes(Number.parseInt(event.target.value, 10))}
                          value={patternIntervalMinutes}
                        >
                          <option value={15}>Every 15 min</option>
                          <option value={30}>Every 30 min</option>
                          <option value={60}>Every hour</option>
                          <option value={180}>Every 3 hours</option>
                          <option value={360}>Every 6 hours</option>
                          <option value={1440}>Daily</option>
                        </select>
                      </label>
                      <label className="mt-6 flex items-center gap-2 text-sm sm:mt-7 xl:mt-0 2xl:mt-7">
                        <input
                          checked={patternTelegram}
                          onChange={(event) => setPatternTelegram(event.target.checked)}
                          type="checkbox"
                        />
                        Send Gemma alerts in Telegram
                      </label>
                    </div>
                    <p className="mt-3 text-xs text-muted-foreground">
                      Last scan: {schedule?.last_pattern_run_at ? formatTimestamp(schedule.last_pattern_run_at) : 'not yet'}
                    </p>
                    {schedule?.last_pattern_summary ? (
                      <p className="mt-2 text-xs text-muted-foreground">{schedule.last_pattern_summary}</p>
                    ) : null}
                    <Button
                      className="mt-3"
                      disabled={scanningPatterns}
                      onClick={() => void handleRunPatternScan()}
                      size="sm"
                      type="button"
                      variant="outline"
                    >
                      {scanningPatterns ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                      Run now
                    </Button>
                  </div>
                </div>

                {schedule?.last_error ? (
                  <p className="mt-4 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-800 dark:text-amber-200">
                    Last scheduler error: {schedule.last_error}
                  </p>
                ) : null}
              </section>

              <section className="grid gap-6 xl:grid-cols-2">
                <article className="rounded-3xl border border-border bg-card/75 p-6 shadow-sm">
                  <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
                    <div>
                      <h2 className="text-2xl font-bold">Daily Reports</h2>
                      <p className="mt-1 text-sm text-muted-foreground">
                        Recent Gemma-generated caregiver handoff summaries.
                      </p>
                    </div>
                    <Button disabled={generatingDaily} onClick={() => void handleGenerateDaily()} type="button" variant="outline">
                      {generatingDaily ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
                      Generate with Gemma
                    </Button>
                  </div>
                  <div className="mt-5 space-y-3">
                    {filteredDailyReports.length ? (
                      filteredDailyReports.map((report) => {
                        const expanded = Boolean(expandedDaily[report.id]);
                        return (
                          <div className="rounded-2xl border border-border bg-background/70 p-4" key={report.id}>
                            <button
                              className="flex w-full items-center justify-between gap-3 text-left"
                              onClick={() =>
                                setExpandedDaily((current) => ({
                                  ...current,
                                  [report.id]: !current[report.id],
                                }))
                              }
                              type="button"
                            >
                              <span>
                                <span className="block font-semibold">{report.date}</span>
                                <span className="text-xs text-muted-foreground">Generated {formatTimestamp(report.created_at)}</span>
                              </span>
                              {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                            </button>
                            {expanded ? (
                              <p className="mt-4 whitespace-pre-wrap text-sm leading-7 text-muted-foreground">
                                {report.report_text}
                              </p>
                            ) : null}
                          </div>
                        );
                      })
                    ) : (
                      <div className="rounded-2xl border border-dashed border-border bg-background/70 p-8 text-center text-sm text-muted-foreground">
                        No daily reports yet.
                      </div>
                    )}
                  </div>
                </article>

                <article className="rounded-3xl border border-border bg-card/75 p-6 shadow-sm">
                  <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
                    <div>
                      <h2 className="text-2xl font-bold">Weekly PDF Reports</h2>
                      <p className="mt-1 text-sm text-muted-foreground">
                        Saved safety and wellness PDFs from the dashboard weekly report generator.
                      </p>
                    </div>
                    <Button disabled={generatingWeekly} onClick={() => void handleGenerateWeekly()} type="button" variant="outline">
                      {generatingWeekly ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                      Generate with Gemma
                    </Button>
                  </div>
                  <div className="mt-5 space-y-3">
                    {filteredWeeklyReports.length ? (
                      filteredWeeklyReports.map((report) => (
                        <div className="rounded-2xl border border-border bg-background/70 p-4" key={report.id}>
                          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
                            <div>
                              <p className="font-semibold">{dateRangeLabel(report)}</p>
                              <p className="mt-1 text-xs text-muted-foreground">
                                Generated {formatTimestamp(report.created_at)} · {report.model_name}
                              </p>
                            </div>
                            <Button
                              disabled={downloadingWeeklyId === report.id}
                              onClick={() => void handleDownloadWeekly(report)}
                              size="sm"
                              type="button"
                              variant="outline"
                            >
                              {downloadingWeeklyId === report.id ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              ) : (
                                <Download className="h-4 w-4" />
                              )}
                              Download
                            </Button>
                          </div>
                        </div>
                      ))
                    ) : (
                      <div className="rounded-2xl border border-dashed border-border bg-background/70 p-8 text-center text-sm text-muted-foreground">
                        No weekly PDFs saved yet.
                      </div>
                    )}
                  </div>
                </article>
              </section>

              <section className="rounded-3xl border border-border bg-card/75 p-6 shadow-sm">
                <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
                  <div>
                    <div className="inline-flex items-center gap-2 rounded-full border border-blue-500/30 bg-blue-500/10 px-3 py-1 text-xs font-semibold text-blue-700 dark:text-blue-300">
                      <TrendingUp className="h-3.5 w-3.5" />
                      Trends & Patterns
                    </div>
                    <h2 className="mt-3 text-2xl font-bold">{mode === 'demo' ? 'Demo trend analysis' : 'Live trend analysis'}</h2>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Today and week-level local SQLite trend signals. Not a medical diagnosis.
                    </p>
                  </div>
                  <Button disabled={analyzingTrends} onClick={() => void handleAnalyzeTrends()} type="button">
                    {analyzingTrends ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                    Analyze with Gemma
                  </Button>
                </div>

                <div className="mt-5 grid gap-3 md:grid-cols-4">
                  <div className="rounded-2xl border border-border bg-background/70 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Events today</p>
                    <p className="mt-2 text-2xl font-bold">{metricValue(todayTrends, 'event_count')}</p>
                    <p className="text-xs text-muted-foreground">{metricDelta(todayTrends, 'event_count')}</p>
                  </div>
                  <div className="rounded-2xl border border-border bg-background/70 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Alerts sent</p>
                    <p className="mt-2 text-2xl font-bold">{metricValue(todayTrends, 'alerts_sent')}</p>
                    <p className="text-xs text-muted-foreground">{metricDelta(todayTrends, 'alerts_sent')}</p>
                  </div>
                  <div className="rounded-2xl border border-border bg-background/70 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Last activity</p>
                    <p className="mt-2 text-xl font-bold">{todayTrends?.activity?.last_activity_age_human ?? 'No data'}</p>
                    <p className="text-xs text-muted-foreground">{todayTrends?.activity?.last_activity_staleness ?? 'unknown'}</p>
                  </div>
                  <div className="rounded-2xl border border-border bg-background/70 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Pattern status</p>
                    <p className="mt-2 text-xl font-bold">{todayTrends?.unusual_detected ? 'Review' : 'Stable'}</p>
                    <p className="text-xs text-muted-foreground">{latestChange?.title ?? 'No unusual pattern detected'}</p>
                  </div>
                </div>

                <div className="mt-5 overflow-hidden rounded-2xl border border-border">
                  <div className="grid grid-cols-5 bg-background/80 px-4 py-3 text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                    <span>Day</span>
                    <span>Events</span>
                    <span>Falls</span>
                    <span>Alerts</span>
                    <span>Night</span>
                  </div>
                  {(weekTrends?.days ?? []).map((day) => (
                    <div className="grid grid-cols-5 border-t border-border px-4 py-3 text-sm" key={day.date}>
                      <span className="font-medium">{day.label}</span>
                      <span>{day.event_count}</span>
                      <span>{day.fall_count}</span>
                      <span>{day.alerts_sent}</span>
                      <span>{day.nighttime_movement_count}</span>
                    </div>
                  ))}
                </div>

                {trendAnalysis ? (
                  <div className="mt-5 rounded-2xl border border-border bg-background/70 p-4">
                    <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                      <BarChart3 className="h-4 w-4" />
                      {trendAnalysis.used_mock ? 'Deterministic fallback' : `Gemma via ${trendAnalysis.model_name}`}
                    </div>
                    <p className="mt-3 whitespace-pre-wrap text-sm leading-7">{trendAnalysis.analysis}</p>
                  </div>
                ) : null}
              </section>
            </div>
          </div>
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}

export default ReportsDashboard;
