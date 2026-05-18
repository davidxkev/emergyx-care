'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Bot, CircleAlert, Trash2 } from 'lucide-react';

import { AssistantPanel } from '@/components/emergyx/assistant-panel';
import { AdminSidebar } from '@/components/ui/admin-sidebar';
import { DashboardHeader } from '@/components/ui/dashboard-header';
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar';
import { confirmDestructiveAction } from '@/lib/confirm';
import {
  createThread,
  deleteThread,
  getAgentStatus,
  getModeSnapshot,
  getThread,
  getThreads,
  streamThreadMessage,
} from '@/lib/api';
import {
  formatTimestamp,
  gemmaStatusLabel,
  modeBadge,
  snapshotState,
} from '@/lib/format';
import type {
  AgentStatus,
  ChatMessage,
  ChatThread,
  Mode,
  ModeSnapshot,
  ThreadDetailResponse,
} from '@/lib/types';

export function ChatDashboard() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const mode: Mode = searchParams.get('mode') === 'demo' ? 'demo' : 'live';
  const modeMeta = modeBadge(mode);

  const [searchQuery, setSearchQuery] = useState('');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [snapshot, setSnapshot] = useState<ModeSnapshot | null>(null);
  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [activeThread, setActiveThread] = useState<ThreadDetailResponse | null>(null);
  const [selectedThreadId, setSelectedThreadId] = useState<number | null>(null);
  const [deletingThreadId, setDeletingThreadId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [thinkingEnabled, setThinkingEnabled] = useState(() => {
    if (typeof window === 'undefined') {
      return true;
    }
    return window.localStorage.getItem('emergyx-chat-thinking') !== 'false';
  });

  useEffect(() => {
    window.localStorage.setItem(
      'emergyx-chat-thinking',
      thinkingEnabled ? 'true' : 'false',
    );
  }, [thinkingEnabled]);

  const filteredThreads = threads.filter((thread) =>
    thread.title.toLowerCase().includes(searchQuery.trim().toLowerCase()),
  );

  const loadThread = useCallback(async (modeValue: Mode, threadId: number) => {
    const detail = await getThread(modeValue, threadId);
    setSelectedThreadId(threadId);
    setActiveThread(detail);
  }, []);

  const loadPage = useCallback(
    async (modeValue: Mode) => {
      setError(null);
      const [agentStatus, modeSnapshot, threadList] = await Promise.all([
        getAgentStatus(),
        getModeSnapshot(modeValue),
        getThreads(modeValue),
      ]);

      setStatus(agentStatus);
      setSnapshot(modeSnapshot);
      setThreads(threadList.threads);

      if (threadList.threads.length > 0) {
        const preferredThreadId =
          selectedThreadId &&
          threadList.threads.some((thread) => thread.id === selectedThreadId)
            ? selectedThreadId
            : threadList.threads[0].id;
        await loadThread(modeValue, preferredThreadId);
      } else {
        setSelectedThreadId(null);
        setActiveThread(null);
      }
    },
    [loadThread, selectedThreadId],
  );

  useEffect(() => {
    let cancelled = false;

    async function run() {
      try {
        setIsRefreshing(true);
        await loadPage(mode);
      } catch (loadError) {
        if (!cancelled) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : 'Unable to load the Gemma chat workspace.',
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
  }, [loadPage, mode]);

  const handleRefresh = async () => {
    try {
      setIsRefreshing(true);
      await loadPage(mode);
    } catch (refreshError) {
      setError(
        refreshError instanceof Error
          ? refreshError.message
          : 'Unable to refresh the chat workspace.',
      );
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleExport = () => {
    if (!activeThread) {
      return;
    }

    const transcript = activeThread.messages
      .map((message) => {
        const role = message.role === 'user' ? 'Caregiver' : 'Gemma';
        return `[${role}] ${message.content}`;
      })
      .join('\n\n');

    const blob = new Blob([transcript], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${activeThread.thread.title.replace(/\s+/g, '-').toLowerCase() || 'emergyx-chat'}.txt`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const handleModeChange = (nextMode: Mode) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set('mode', nextMode);
    router.replace(`/chat?${params.toString()}`);
  };

  const handleNewThread = async () => {
    try {
      setLoading(true);
      const created = await createThread(mode);
      setThreads((current) => [created.thread, ...current]);
      setSelectedThreadId(created.thread.id);
      setActiveThread({
        thread: created.thread,
        messages: [],
      });
    } catch (createError) {
      setError(
        createError instanceof Error
          ? createError.message
          : 'Unable to create a new chat thread.',
      );
    } finally {
      setLoading(false);
    }
  };

  const handleSelectThread = async (threadId: number) => {
    try {
      setLoading(true);
      await loadThread(mode, threadId);
    } catch (selectError) {
      setError(
        selectError instanceof Error
          ? selectError.message
          : 'Unable to open this chat thread.',
      );
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteThread = async (thread: ChatThread) => {
    const confirmed = confirmDestructiveAction(
      `Delete "${thread.title}" and all messages in this chat?`,
    );
    if (!confirmed) {
      return;
    }

    try {
      setDeletingThreadId(thread.id);
      setError(null);
      await deleteThread(mode, thread.id);

      const refreshedThreads = await getThreads(mode);
      setThreads(refreshedThreads.threads);

      if (activeThread?.thread.id !== thread.id) {
        return;
      }

      const nextThread = refreshedThreads.threads[0] ?? null;
      if (nextThread) {
        await loadThread(mode, nextThread.id);
      } else {
        setSelectedThreadId(null);
        setActiveThread(null);
      }
    } catch (deleteError) {
      setError(
        deleteError instanceof Error
          ? deleteError.message
          : 'Unable to delete this chat thread.',
      );
    } finally {
      setDeletingThreadId(null);
    }
  };

  const handleSend = async (question: string) => {
    const pendingAssistantId = -Date.now() - 1;
    try {
      setLoading(true);
      setError(null);

      let thread = activeThread?.thread ?? null;
      if (!thread) {
        const created = await createThread(mode, question.slice(0, 60));
        thread = created.thread;
        setThreads((current) => [created.thread, ...current]);
        setSelectedThreadId(created.thread.id);
        setActiveThread({
          thread: created.thread,
          messages: [],
        });
      }

      const optimisticUserMessage: ChatMessage = {
        id: -Date.now(),
        thread_id: thread.id,
        role: 'user',
        content: question,
        created_at: new Date().toISOString(),
        metadata: null,
      };

      const optimisticAssistantMessage: ChatMessage = {
        id: pendingAssistantId,
        thread_id: thread.id,
        role: 'assistant',
        content: '',
        created_at: new Date().toISOString(),
        metadata: {
          thinking: '',
        },
      };

      setActiveThread((current) => {
        if (!thread) {
          return current;
        }
        return {
          thread,
          messages: [
            ...(current?.messages ?? []),
            optimisticUserMessage,
            optimisticAssistantMessage,
          ],
        };
      });

      const detail = await streamThreadMessage(mode, thread.id, question, thinkingEnabled, {
        onThinking: (delta) => {
          setActiveThread((current) => {
            if (!current) {
              return current;
            }
            return {
              ...current,
              messages: current.messages.map((message) =>
                message.id === pendingAssistantId
                  ? {
                      ...message,
                      metadata: {
                        ...(message.metadata ?? {}),
                        thinking: `${message.metadata?.thinking ?? ''}${delta}`,
                      },
                    }
                  : message,
              ),
            };
          });
        },
        onChunk: (delta) => {
          setActiveThread((current) => {
            if (!current) {
              return current;
            }
            return {
              ...current,
              messages: current.messages.map((message) =>
                message.id === pendingAssistantId
                  ? { ...message, content: `${message.content}${delta}` }
                  : message,
              ),
            };
          });
        },
      });
      setSelectedThreadId(thread.id);
      setActiveThread(detail);

      const refreshedThreads = await getThreads(mode);
      setThreads(refreshedThreads.threads);
    } catch (sendError) {
      setError(
        sendError instanceof Error
          ? sendError.message
          : 'Unable to send this message to Gemma.',
      );
      setActiveThread((current) => {
        if (!current) {
          return current;
        }
        return {
          ...current,
          messages: current.messages.filter((message) => message.id !== pendingAssistantId),
        };
      });
    } finally {
      setLoading(false);
    }
  };

  const stateSummary = snapshot ? snapshotState(snapshot) : null;

  return (
    <SidebarProvider>
      <AdminSidebar />
      <SidebarInset>
        <DashboardHeader
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          onRefresh={() => void handleRefresh()}
          onExport={handleExport}
          isRefreshing={isRefreshing}
          searchPlaceholder="Search saved chats..."
        />

        <div className="flex flex-1 flex-col gap-2 p-2 pt-0 sm:gap-4 sm:p-4">
          <div className="min-h-[calc(100vh-4rem)] flex-1 rounded-lg p-3 sm:rounded-xl sm:p-4 md:p-6">
            <div className="mx-auto max-w-6xl space-y-6">
              <section className="border-border bg-card/40 rounded-xl border p-6">
                <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
                  <div className="space-y-3">
                    <div className="flex items-center gap-3">
                      <div className="bg-primary/10 text-primary flex h-11 w-11 items-center justify-center rounded-xl">
                        <Bot className="h-5 w-5" />
                      </div>
                      <div>
                        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">
                          Gemma Chat
                        </h1>
                        <p className="text-muted-foreground text-sm sm:text-base">
                          Ask about incidents, alerts, reports, and the local care
                          timeline.
                        </p>
                      </div>
                    </div>
                    <p className="text-muted-foreground max-w-3xl text-sm leading-6">
                      Gemma answers from local care data, generates reports, and can
                      support alert decisions when Gemma-first notifications or the
                      pattern monitor are enabled.
                    </p>
                  </div>

                  <div className="flex flex-wrap items-center gap-3">
                    <div className="bg-muted inline-flex rounded-full p-1">
                      {(['live', 'demo'] as const).map((value) => (
                        <button
                          key={value}
                          type="button"
                          onClick={() => handleModeChange(value)}
                          className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                            mode === value
                              ? 'bg-background text-foreground shadow-sm'
                              : 'text-muted-foreground hover:text-foreground'
                          }`}
                        >
                          {value === 'live' ? 'LIVE' : 'DEMO'}
                        </button>
                      ))}
                    </div>
                    <span className="rounded-full border border-border bg-background px-3 py-2 text-sm font-medium">
                      {gemmaStatusLabel(status)}
                    </span>
                    <span className="rounded-full border border-border bg-background px-3 py-2 text-sm font-medium">
                      {modeMeta.label} · {modeMeta.detail}
                    </span>
                    <button
                      type="button"
                      onClick={() => setThinkingEnabled((current) => !current)}
                      className={`inline-flex items-center gap-2 rounded-full border px-3 py-2 text-sm font-medium transition ${
                        thinkingEnabled
                          ? 'border-primary/30 bg-primary/5 text-foreground'
                          : 'border-border bg-background text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      <span
                        className={`h-2.5 w-2.5 rounded-full ${
                          thinkingEnabled ? 'bg-primary' : 'bg-muted-foreground/50'
                        }`}
                      />
                      Thinking {thinkingEnabled ? 'on' : 'off'}
                    </button>
                  </div>
                </div>

                <div className="mt-5 grid grid-cols-1 gap-3 md:grid-cols-3">
                  <div className="rounded-xl bg-muted/50 px-4 py-3">
                    <p className="text-muted-foreground text-xs uppercase tracking-[0.16em]">
                      Safety state
                    </p>
                    <p className="mt-2 text-sm font-semibold">
                      {stateSummary?.safety ?? 'No data'}
                    </p>
                  </div>
                  <div className="rounded-xl bg-muted/50 px-4 py-3">
                    <p className="text-muted-foreground text-xs uppercase tracking-[0.16em]">
                      Latest incident
                    </p>
                    <p className="mt-2 text-sm font-semibold">
                      {stateSummary?.incident ?? 'No urgent incident'}
                    </p>
                  </div>
                  <div className="rounded-xl bg-muted/50 px-4 py-3">
                    <p className="text-muted-foreground text-xs uppercase tracking-[0.16em]">
                      Latest local update
                    </p>
                    <p className="mt-2 text-sm font-semibold">
                      {formatTimestamp(snapshot?.last_event_timestamp)}
                    </p>
                  </div>
                </div>

                {error ? (
                  <div className="mt-5 flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200">
                    <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>{error}</span>
                  </div>
                ) : null}
              </section>

              <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
                <AssistantPanel
                  mode={mode}
                  status={status}
                  threads={threads}
                  activeThread={activeThread}
                  loading={loading}
                  thinkingEnabled={thinkingEnabled}
                  showThreadChips={false}
                  onNewThread={handleNewThread}
                  onSelectThread={handleSelectThread}
                  onSend={handleSend}
                />

                <aside className="border-border bg-card/40 rounded-xl border p-5">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <h2 className="text-lg font-semibold tracking-tight">
                        Chat history
                      </h2>
                      <p className="text-muted-foreground mt-1 text-sm">
                        Saved caregiver conversations
                      </p>
                    </div>
                    <span className="rounded-full bg-muted px-3 py-1 text-xs font-medium text-muted-foreground">
                      {filteredThreads.length}
                    </span>
                  </div>

                  <div className="mt-4 max-h-[560px] space-y-2 overflow-y-auto pr-1">
                    {filteredThreads.length > 0 ? (
                      filteredThreads.map((thread) => (
                        <div
                          key={thread.id}
                          className={`group flex w-full items-center gap-2 rounded-xl border px-3 py-3 transition ${
                            activeThread?.thread.id === thread.id
                              ? 'border-primary/30 bg-primary/5'
                              : 'border-border bg-background hover:bg-accent'
                          }`}
                        >
                          <button
                            type="button"
                            onClick={() => void handleSelectThread(thread.id)}
                            className="min-w-0 flex-1 text-left"
                          >
                            <div className="line-clamp-1 text-sm font-medium">
                              {thread.title}
                            </div>
                            <div className="mt-1 text-xs text-muted-foreground">
                              {formatTimestamp(thread.updated_at)}
                            </div>
                          </button>
                          <button
                            type="button"
                            aria-label={`Delete chat ${thread.title}`}
                            disabled={deletingThreadId === thread.id}
                            onClick={() => void handleDeleteThread(thread)}
                            className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-muted-foreground opacity-100 transition hover:bg-destructive/10 hover:text-destructive disabled:pointer-events-none disabled:opacity-50 sm:opacity-0 sm:group-hover:opacity-100 sm:focus:opacity-100"
                            title="Delete chat"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      ))
                    ) : (
                      <div className="rounded-xl border border-dashed border-border px-4 py-6 text-sm text-muted-foreground">
                        No saved chats match your search.
                      </div>
                    )}
                  </div>
                </aside>
              </div>
            </div>
          </div>
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}
