'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  AlertCircle,
  BellRing,
  CheckCircle2,
  Copy,
  Loader2,
  Moon,
  Radio,
  Terminal,
  Zap,
} from 'lucide-react';

import { AdminSidebar } from '@/components/ui/admin-sidebar';
import { Button } from '@/components/ui/button';
import { DashboardHeader } from '@/components/ui/dashboard-header';
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar';
import {
  getAgentStatus,
  getGemmaSettings,
  getHealth,
  getModeSnapshot,
  getTelegramSettings,
  pullGemmaModel,
  updateGemmaSettings,
  updateTelegramSettings,
} from '@/lib/api';
import { confirmDestructiveAction } from '@/lib/confirm';
import { gemmaStatusLabel } from '@/lib/format';
import {
  DEFAULT_NIGHT_END_HOUR,
  DEFAULT_NIGHT_START_HOUR,
  loadNightWindowPreference,
  saveNightWindowPreference,
} from '@/lib/trends';
import type {
  AgentStatus,
  GemmaSettingsRead,
  HealthResponse,
  ModeSnapshot,
  TelegramSettingsRead,
} from '@/lib/types';

function statusText(online: boolean) {
  return online ? 'Online' : 'Offline';
}

function StatusBadge({ online }: { online: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold ${
        online
          ? 'border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-300'
          : 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300'
      }`}
    >
      <span className={`h-2 w-2 rounded-full ${online ? 'bg-green-500' : 'bg-red-500'}`} />
      {statusText(online)}
    </span>
  );
}

function SettingsCard({
  title,
  detail,
  icon: Icon,
  online,
}: {
  title: string;
  detail: string;
  icon: typeof Radio;
  online: boolean;
}) {
  return (
    <article className="rounded-2xl border border-border bg-card/75 p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div className="rounded-xl bg-primary/10 p-3 text-primary">
          <Icon className="h-5 w-5" />
        </div>
        <StatusBadge online={online} />
      </div>
      <h3 className="mt-5 text-lg font-bold">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">{detail}</p>
    </article>
  );
}

function CodeRow({ label, command }: { label: string; command: string }) {
  const copy = async () => {
    await navigator.clipboard.writeText(command);
  };

  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-border bg-background/70 p-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <p className="text-sm font-semibold">{label}</p>
        <code className="mt-1 block truncate text-xs text-muted-foreground">
          {command}
        </code>
      </div>
      <Button variant="outline" size="sm" onClick={() => void copy()}>
        <Copy className="h-4 w-4" />
        Copy
      </Button>
    </div>
  );
}
const telegramCommands = [
  '/status',
  '/latest',
  '/explain',
  '/trends',
  '/changes',
  '/report',
  '/ask what happened today?',
  '/dashboard',
  '/help',
];

export function SettingsDashboard() {
  const [searchQuery, setSearchQuery] = useState('');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
  const [snapshot, setSnapshot] = useState<ModeSnapshot | null>(null);
  const [gemmaSettings, setGemmaSettings] = useState<GemmaSettingsRead | null>(null);
  const [gemmaEnabled, setGemmaEnabled] = useState(true);
  const [gemmaModel, setGemmaModel] = useState('gemma4:e2b');
  const [ollamaBaseUrl, setOllamaBaseUrl] = useState('http://localhost:11434');
  const [gemmaFirstNotifications, setGemmaFirstNotifications] = useState(false);
  const [gemmaSaving, setGemmaSaving] = useState(false);
  const [gemmaPulling, setGemmaPulling] = useState(false);
  const [gemmaFeedback, setGemmaFeedback] = useState<string | null>(null);
  const [telegramSettings, setTelegramSettings] = useState<TelegramSettingsRead | null>(null);
  const [telegramToken, setTelegramToken] = useState('');
  const [telegramChatId, setTelegramChatId] = useState('');
  const [telegramGemma, setTelegramGemma] = useState(false);
  const [telegramPollTimeout, setTelegramPollTimeout] = useState(25);
  const [telegramPollInterval, setTelegramPollInterval] = useState(2);
  const [clearTelegramToken, setClearTelegramToken] = useState(false);
  const [clearTelegramChatId, setClearTelegramChatId] = useState(false);
  const [telegramSaving, setTelegramSaving] = useState(false);
  const [telegramFeedback, setTelegramFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nightStartHour, setNightStartHour] = useState<number>(
    () => loadNightWindowPreference().startHour ?? DEFAULT_NIGHT_START_HOUR,
  );
  const [nightEndHour, setNightEndHour] = useState<number>(
    () => loadNightWindowPreference().endHour ?? DEFAULT_NIGHT_END_HOUR,
  );
  const [nightFeedback, setNightFeedback] = useState<string | null>(null);

  const loadSettings = useCallback(async () => {
    setError(null);
    const [healthPayload, agentPayload, liveSnapshot, telegramPayload, gemmaPayload] = await Promise.all([
      getHealth(),
      getAgentStatus(),
      getModeSnapshot('live'),
      getTelegramSettings(),
      getGemmaSettings(),
    ]);
    setHealth(healthPayload);
    setAgentStatus(agentPayload);
    setSnapshot(liveSnapshot);
    setTelegramSettings(telegramPayload);
    setTelegramChatId(telegramPayload.chat_id ?? '');
    setTelegramGemma(telegramPayload.send_gemma_explanations);
    setTelegramPollTimeout(telegramPayload.poll_timeout_seconds);
    setTelegramPollInterval(telegramPayload.poll_interval_seconds);
    setGemmaSettings(gemmaPayload);
    setGemmaEnabled(gemmaPayload.enabled);
    setGemmaModel(gemmaPayload.model);
    setOllamaBaseUrl(gemmaPayload.ollama_base_url);
    setGemmaFirstNotifications(gemmaPayload.gemma_first_notifications);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function run() {
      try {
        setIsRefreshing(true);
        await loadSettings();
      } catch (loadError) {
        if (!cancelled) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : 'Unable to load settings.',
          );
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
  }, [loadSettings]);

  const liveOnline = (snapshot?.last_event_age_seconds ?? Number.POSITIVE_INFINITY) <= 15;
  const gemmaOnline = agentStatus?.status === 'online';
  const telegramOnline = Boolean(health?.telegram_configured);

  const saveTelegram = async (sendTestMessage: boolean) => {
    if (
      (clearTelegramToken || clearTelegramChatId) &&
      !confirmDestructiveAction(
        `Clear saved Telegram ${clearTelegramToken && clearTelegramChatId ? 'bot token and chat ID' : clearTelegramToken ? 'bot token' : 'chat ID'}?`,
      )
    ) {
      return;
    }

    try {
      setTelegramSaving(true);
      setTelegramFeedback(null);
      const response = await updateTelegramSettings({
        bot_token: telegramToken.trim() || null,
        chat_id: telegramChatId.trim() || null,
        send_gemma_explanations: telegramGemma,
        poll_timeout_seconds: telegramPollTimeout,
        poll_interval_seconds: telegramPollInterval,
        clear_bot_token: clearTelegramToken,
        clear_chat_id: clearTelegramChatId,
        send_test_message: sendTestMessage,
      });
      setTelegramSettings(response.settings);
      setTelegramToken('');
      setClearTelegramToken(false);
      setClearTelegramChatId(false);
      setTelegramFeedback(response.message);
      await loadSettings();
    } catch (saveError) {
      setTelegramFeedback(
        saveError instanceof Error
          ? saveError.message
          : 'Unable to save Telegram settings.',
      );
    } finally {
      setTelegramSaving(false);
    }
  };

  const saveGemma = async () => {
    try {
      setGemmaSaving(true);
      setGemmaFeedback(null);
      const response = await updateGemmaSettings({
        enabled: gemmaEnabled,
        model: gemmaModel.trim(),
        ollama_base_url: ollamaBaseUrl.trim(),
        gemma_first_notifications: gemmaFirstNotifications,
      });
      setGemmaSettings(response.settings);
      setAgentStatus({
        gemma_enabled: response.settings.enabled,
        model: response.settings.model,
        ollama_base_url: response.settings.ollama_base_url,
        checked_at: new Date().toISOString(),
        status: response.settings.status,
        reachable: response.settings.reachable,
        installed_models: response.settings.installed_models,
        error: response.settings.error ?? undefined,
      });
      setGemmaFeedback(response.message);
      await loadSettings();
    } catch (saveError) {
      setGemmaFeedback(
        saveError instanceof Error
          ? saveError.message
          : 'Unable to save Gemma/Ollama settings.',
      );
    } finally {
      setGemmaSaving(false);
    }
  };

  const downloadGemmaModel = async () => {
    try {
      setGemmaPulling(true);
      setGemmaFeedback(`Downloading ${gemmaModel.trim()} with Ollama. This can take a while.`);
      const response = await pullGemmaModel({
        model: gemmaModel.trim(),
        save_as_current: true,
      });
      setGemmaSettings(response.settings);
      setGemmaEnabled(response.settings.enabled);
      setGemmaModel(response.settings.model);
      setOllamaBaseUrl(response.settings.ollama_base_url);
      setGemmaFeedback(response.message);
      await loadSettings();
    } catch (pullError) {
      setGemmaFeedback(
        pullError instanceof Error
          ? pullError.message
          : 'Unable to download the model from Ollama.',
      );
    } finally {
      setGemmaPulling(false);
    }
  };

  const refreshSettings = async () => {
    try {
      setIsRefreshing(true);
      await loadSettings();
    } catch (refreshError) {
      setError(
        refreshError instanceof Error
          ? refreshError.message
          : 'Unable to refresh settings.',
      );
    } finally {
      setIsRefreshing(false);
    }
  };

  const saveNightWindow = () => {
    const next = saveNightWindowPreference({
      startHour: nightStartHour,
      endHour: nightEndHour,
    });
    setNightStartHour(next.startHour);
    setNightEndHour(next.endHour);
    setNightFeedback(
      `Nighttime trends window saved: ${String(next.startHour).padStart(2, '0')}:00-${String(next.endHour).padStart(2, '0')}:00.`,
    );
  };

  const resetNightWindow = () => {
    const next = saveNightWindowPreference({
      startHour: DEFAULT_NIGHT_START_HOUR,
      endHour: DEFAULT_NIGHT_END_HOUR,
    });
    setNightStartHour(next.startHour);
    setNightEndHour(next.endHour);
    setNightFeedback('Nighttime trends window reset to 22:00-06:00.');
  };

  const exportSettingsSnapshot = () => {
    const payload = {
      exported_at: new Date().toISOString(),
      health,
      agentStatus,
      snapshot,
      night_window: {
        start_hour: nightStartHour,
        end_hour: nightEndHour,
      },
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: 'application/json;charset=utf-8',
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'emergyx-settings-snapshot.json';
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <SidebarProvider>
      <AdminSidebar />
      <SidebarInset>
        <DashboardHeader
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          onRefresh={() => void refreshSettings()}
          onExport={exportSettingsSnapshot}
          isRefreshing={isRefreshing}
          searchPlaceholder="Search runtime settings..."
        />

        <div className="flex flex-1 flex-col gap-2 bg-[radial-gradient(circle_at_top_left,rgba(37,99,235,0.08),transparent_32rem),linear-gradient(180deg,var(--background),rgba(241,245,249,0.72))] p-2 pt-0 sm:gap-4 sm:p-4 dark:bg-[radial-gradient(circle_at_top_left,rgba(59,130,246,0.18),transparent_30rem),linear-gradient(180deg,var(--background),#09090b)]">
          <div className="min-h-[calc(100vh-4rem)] flex-1 rounded-lg p-3 sm:rounded-xl sm:p-4 md:p-6">
            <div className="mx-auto max-w-6xl space-y-6">
            <section className="overflow-hidden rounded-3xl border border-border bg-card/80 p-6 shadow-sm md:p-8">
              <div className="flex flex-col justify-between gap-6 lg:flex-row lg:items-start">
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.22em] text-blue-600 dark:text-blue-300">
                    Runtime settings
                  </p>
                  <h1 className="mt-3 text-3xl font-bold tracking-tight md:text-4xl">
                    Emergyx Control Room
                  </h1>
                  <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground md:text-base">
                    A local-only view of the pieces judges care about: live sensors,
                    Gemma4, Telegram caregiver alerts, data storage, and the exact
                    workers that keep the demo running.
                  </p>
                </div>
                <div className="grid gap-2 rounded-2xl border border-border bg-background/70 p-4 text-sm">
                  <div className="flex items-center justify-between gap-8">
                    <span className="text-muted-foreground">App</span>
                    <strong>{health?.app ?? 'Emergyx Care'}</strong>
                  </div>
                  <div className="flex items-center justify-between gap-8">
                    <span className="text-muted-foreground">Version</span>
                    <strong>{health?.version ?? 'unknown'}</strong>
                  </div>
                  <div className="flex items-center justify-between gap-8">
                    <span className="text-muted-foreground">Environment</span>
                    <strong>{health?.environment ?? 'local'}</strong>
                  </div>
                </div>
              </div>
            </section>

            {error ? (
              <div className="flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{error}</span>
              </div>
            ) : null}

            <section className="grid gap-4 md:grid-cols-3">
              <SettingsCard
                title="Live Sensors"
                detail={
                  liveOnline
                    ? `Latest live row ${snapshot?.last_event_age_human ?? 'just now'}.`
                    : 'No fresh live row within the dashboard freshness window.'
                }
                icon={Radio}
                online={liveOnline}
              />
              <SettingsCard
                title="Gemma4"
                detail={`${gemmaStatusLabel(agentStatus)} · ${agentStatus?.model ?? 'gemma4:e2b'}`}
                icon={Zap}
                online={gemmaOnline}
              />
              <SettingsCard
                title="Telegram"
                detail={
                  telegramOnline
                    ? `Commands enabled. Gemma follow-up alerts are ${health?.telegram_gemma_explanations ? 'on' : 'off'}.`
                    : 'Telegram token/chat ID are not configured.'
                }
                icon={BellRing}
                online={telegramOnline}
              />
            </section>

            <section className="grid gap-6 lg:grid-cols-5">
              <article className="rounded-3xl border border-border bg-card/75 p-6 shadow-sm lg:col-span-3">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-xs font-bold uppercase tracking-[0.2em] text-muted-foreground">
                      Telegram setup
                    </p>
                    <h2 className="mt-2 text-2xl font-bold">Caregiver alert channel</h2>
                  </div>
                  <StatusBadge online={telegramOnline} />
                </div>

                <div className="mt-6 grid gap-3">
                  <div className="rounded-2xl border border-border bg-background/70 p-4">
                    <div className="flex items-start gap-3">
                      <BellRing className="mt-0.5 h-5 w-5 text-blue-500" />
                      <div>
                        <p className="text-sm font-bold">Connection status</p>
                        <p className="mt-1 text-sm leading-6 text-muted-foreground">
                          {telegramSettings?.configured
                            ? `Telegram is configured. Gemma follow-up explanations are ${telegramSettings.send_gemma_explanations ? 'enabled' : 'disabled'}.`
                            : 'Paste a bot token and caregiver chat ID below, then save. Start or restart the Telegram worker for command polling.'}
                        </p>
                        {telegramSettings?.bot_token_masked ? (
                          <p className="mt-2 text-xs text-muted-foreground">
                            Current token: {telegramSettings.bot_token_masked}
                          </p>
                        ) : null}
                      </div>
                    </div>
                  </div>

                  <div className="grid gap-4 rounded-2xl border border-border bg-background/70 p-4">
                    <label className="space-y-1">
                      <span className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                        Bot token
                      </span>
                      <input
                        className="h-10 w-full rounded-xl border border-border bg-card px-3 text-sm"
                        disabled={clearTelegramToken || telegramSaving}
                        onChange={(event) => setTelegramToken(event.target.value)}
                        placeholder={
                          telegramSettings?.bot_token_set
                            ? 'Leave blank to keep existing token'
                            : '123456:your-bot-token'
                        }
                        type="password"
                        value={telegramToken}
                      />
                    </label>

                    <label className="space-y-1">
                      <span className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                        Caregiver chat ID
                      </span>
                      <input
                        className="h-10 w-full rounded-xl border border-border bg-card px-3 text-sm"
                        disabled={clearTelegramChatId || telegramSaving}
                        onChange={(event) => setTelegramChatId(event.target.value)}
                        placeholder="123456789"
                        type="text"
                        value={telegramChatId}
                      />
                    </label>

                    <div className="grid gap-3 sm:grid-cols-2">
                      <label className="space-y-1">
                        <span className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                          Poll timeout seconds
                        </span>
                        <input
                          className="h-10 w-full rounded-xl border border-border bg-card px-3 text-sm"
                          max={120}
                          min={5}
                          onChange={(event) =>
                            setTelegramPollTimeout(
                              Math.max(5, Math.min(120, Number.parseInt(event.target.value || '25', 10))),
                            )
                          }
                          type="number"
                          value={telegramPollTimeout}
                        />
                      </label>
                      <label className="space-y-1">
                        <span className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                          Poll interval seconds
                        </span>
                        <input
                          className="h-10 w-full rounded-xl border border-border bg-card px-3 text-sm"
                          max={30}
                          min={1}
                          onChange={(event) =>
                            setTelegramPollInterval(
                              Math.max(1, Math.min(30, Number.parseInt(event.target.value || '2', 10))),
                            )
                          }
                          type="number"
                          value={telegramPollInterval}
                        />
                      </label>
                    </div>

                    <div className="grid gap-2 text-sm">
                      <label className="flex items-center gap-2">
                        <input
                          checked={telegramGemma}
                          onChange={(event) => setTelegramGemma(event.target.checked)}
                          type="checkbox"
                        />
                        Send Gemma follow-up explanations after alerts
                      </label>
                      <label className="flex items-center gap-2">
                        <input
                          checked={clearTelegramToken}
                          onChange={(event) => setClearTelegramToken(event.target.checked)}
                          type="checkbox"
                        />
                        Clear saved bot token
                      </label>
                      <label className="flex items-center gap-2">
                        <input
                          checked={clearTelegramChatId}
                          onChange={(event) => setClearTelegramChatId(event.target.checked)}
                          type="checkbox"
                        />
                        Clear saved chat ID
                      </label>
                    </div>

                    <div className="flex flex-wrap gap-2">
                      <Button
                        disabled={telegramSaving}
                        onClick={() => void saveTelegram(false)}
                        type="button"
                      >
                        Save Telegram setup
                      </Button>
                      <Button
                        disabled={telegramSaving}
                        onClick={() => void saveTelegram(true)}
                        type="button"
                        variant="outline"
                      >
                        Send test message
                      </Button>
                    </div>
                    {telegramFeedback ? (
                      <p className="rounded-xl border border-border bg-card px-3 py-2 text-xs font-medium">
                        {telegramFeedback}
                      </p>
                    ) : null}
                  </div>

                  <div className="rounded-2xl border border-border bg-background/70 p-4">
                    <p className="text-sm font-bold">Caregiver commands</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {telegramCommands.map((command) => (
                        <span
                          key={command}
                          className="rounded-full border border-border bg-card px-3 py-1 text-xs font-semibold"
                        >
                          {command}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div className="rounded-2xl border border-border bg-background/70 p-4">
                    <div className="flex items-start gap-3">
                      <CheckCircle2 className="mt-0.5 h-5 w-5 text-green-500" />
                      <p className="text-sm leading-6 text-muted-foreground">
                        Fall alerts can include inline buttons for Explain, Live status,
                        Latest event, and Daily report. Telegram is optional for the demo;
                        the web dashboard still works without it.
                      </p>
                    </div>
                  </div>
                </div>
              </article>

              <article className="rounded-3xl border border-border bg-card/75 p-6 shadow-sm lg:col-span-2">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-xs font-bold uppercase tracking-[0.2em] text-muted-foreground">
                      Ollama model
                    </p>
                    <h2 className="mt-2 text-2xl font-bold">Gemma setup</h2>
                  </div>
                  <StatusBadge online={Boolean(gemmaSettings?.reachable)} />
                </div>

                <div className="mt-6 space-y-4">
                  <div className="rounded-2xl border border-border bg-background/70 p-4">
                    <p className="text-sm font-semibold">
                      {gemmaSettings?.status === 'online'
                        ? 'Ollama is reachable'
                        : gemmaSettings?.status === 'disabled'
                          ? 'Gemma is disabled'
                          : 'Ollama is not reachable'}
                    </p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      Current model: {gemmaSettings?.model ?? agentStatus?.model ?? gemmaModel}.
                      {gemmaSettings?.error ? ` ${gemmaSettings.error}` : ''}
                    </p>
                  </div>

                  <label className="space-y-1">
                    <span className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                      Ollama URL
                    </span>
                    <input
                      className="h-10 w-full rounded-xl border border-border bg-card px-3 text-sm"
                      onChange={(event) => setOllamaBaseUrl(event.target.value)}
                      placeholder="http://localhost:11434"
                      type="url"
                      value={ollamaBaseUrl}
                    />
                  </label>

                  <label className="space-y-1">
                    <span className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                      Model name
                    </span>
                    <input
                      className="h-10 w-full rounded-xl border border-border bg-card px-3 text-sm"
                      list="installed-ollama-models"
                      onChange={(event) => setGemmaModel(event.target.value)}
                      placeholder="gemma4:e2b"
                      type="text"
                      value={gemmaModel}
                    />
                    <datalist id="installed-ollama-models">
                      {(gemmaSettings?.installed_models ?? agentStatus?.installed_models ?? []).map((model) => (
                        <option key={model} value={model} />
                      ))}
                    </datalist>
                  </label>

                  <label className="flex items-center gap-2 text-sm">
                    <input
                      checked={gemmaEnabled}
                      onChange={(event) => setGemmaEnabled(event.target.checked)}
                      type="checkbox"
                    />
                    Enable Gemma for chat, reports, and explanations
                  </label>

                  <label className="flex items-start gap-3 rounded-2xl border border-border bg-background/70 p-4 text-sm">
                    <input
                      checked={gemmaFirstNotifications}
                      className="mt-1"
                      onChange={(event) => setGemmaFirstNotifications(event.target.checked)}
                      type="checkbox"
                    />
                    <span>
                      <span className="block font-semibold">Gemma-first notifications</span>
                      <span className="mt-1 block text-xs leading-5 text-muted-foreground">
                        When enabled, Gemma reviews likely falls and major heart-rate or breathing-rate changes,
                        decides whether to notify caregivers, and writes the Telegram and dashboard alert text.
                        When disabled, Emergyx uses the normal rule-based fall alert flow.
                      </span>
                    </span>
                  </label>

                  <div className="flex flex-wrap gap-2">
                    <Button
                      disabled={gemmaSaving || gemmaPulling}
                      onClick={() => void saveGemma()}
                      type="button"
                    >
                      {gemmaSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                      Save model
                    </Button>
                    <Button
                      disabled={gemmaSaving || gemmaPulling || !gemmaModel.trim()}
                      onClick={() => void downloadGemmaModel()}
                      type="button"
                      variant="outline"
                    >
                      {gemmaPulling ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                      Download with Ollama
                    </Button>
                  </div>

                  {gemmaSettings?.installed_models?.length ? (
                    <div className="flex flex-wrap gap-2">
                      {gemmaSettings.installed_models.map((model) => (
                        <button
                          className="rounded-full border border-border bg-background px-3 py-1 text-xs font-semibold"
                          key={model}
                          onClick={() => setGemmaModel(model)}
                          type="button"
                        >
                          {model}
                        </button>
                      ))}
                    </div>
                  ) : null}

                  {gemmaFeedback ? (
                    <p className="rounded-xl border border-border bg-background px-3 py-2 text-xs font-medium">
                      {gemmaFeedback}
                    </p>
                  ) : null}
                </div>
              </article>
            </section>

            <section className="grid gap-6 lg:grid-cols-2">
              <article className="rounded-3xl border border-border bg-card/75 p-6 shadow-sm">
                <div className="flex items-center gap-3">
                  <div className="rounded-xl bg-blue-500/10 p-3 text-blue-600 dark:text-blue-300">
                    <Terminal className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="text-xs font-bold uppercase tracking-[0.2em] text-muted-foreground">
                      Workers
                    </p>
                    <h2 className="text-2xl font-bold">Run commands</h2>
                  </div>
                </div>
                <div className="mt-6 space-y-3">
                  <CodeRow label="Backend API" command="./.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000" />
                  <CodeRow label="Next dashboard" command="cd frontend && npm run dev -- --hostname 127.0.0.1 --port 3000" />
                  <CodeRow label="Sensor ingestion" command="./.venv/bin/python scripts/run_sensor_ingestion.py" />
                  <CodeRow label="Telegram command bot" command="./.venv/bin/python scripts/run_telegram_bot.py" />
                </div>
              </article>

              <article className="rounded-3xl border border-border bg-card/75 p-6 shadow-sm">
                <div className="flex items-center gap-3">
                  <div className="rounded-xl bg-violet-500/10 p-3 text-violet-600 dark:text-violet-300">
                    <Moon className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="text-xs font-bold uppercase tracking-[0.2em] text-muted-foreground">
                      Nighttime trends
                    </p>
                    <h2 className="text-2xl font-bold">Trend window setup</h2>
                  </div>
                </div>
                <div className="mt-6 grid gap-4">
                  <div className="grid gap-4 sm:grid-cols-2">
                    <label className="space-y-1">
                      <span className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                        Night starts
                      </span>
                      <select
                        className="h-10 w-full rounded-xl border border-border bg-card px-3 text-sm"
                        onChange={(event) => setNightStartHour(Number.parseInt(event.target.value, 10))}
                        value={nightStartHour}
                      >
                        {Array.from({ length: 24 }, (_, hour) => (
                          <option key={hour} value={hour}>
                            {String(hour).padStart(2, '0')}:00
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="space-y-1">
                      <span className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                        Night ends
                      </span>
                      <select
                        className="h-10 w-full rounded-xl border border-border bg-card px-3 text-sm"
                        onChange={(event) => setNightEndHour(Number.parseInt(event.target.value, 10))}
                        value={nightEndHour}
                      >
                        {Array.from({ length: 24 }, (_, hour) => (
                          <option key={hour} value={hour}>
                            {String(hour).padStart(2, '0')}:00
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    <Button onClick={saveNightWindow} type="button">
                      Save trend window
                    </Button>
                    <Button onClick={resetNightWindow} type="button" variant="outline">
                      Reset default
                    </Button>
                  </div>

                  {nightFeedback ? (
                    <p className="rounded-xl border border-border bg-background px-3 py-2 text-xs font-medium">
                      {nightFeedback}
                    </p>
                  ) : null}
                </div>
                <div className="mt-6 rounded-2xl border border-border bg-background/70 p-4">
                  <div className="flex items-start gap-3">
                    <CheckCircle2 className="mt-0.5 h-5 w-5 text-green-500" />
                    <p className="text-sm leading-6 text-muted-foreground">
                      This window controls how nighttime readings are grouped in the
                      dashboard trend views and exported settings snapshot. It is stored
                      locally in this browser for the demo operator.
                    </p>
                  </div>
                </div>
              </article>
            </section>

            </div>
          </div>
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}

export default SettingsDashboard;
