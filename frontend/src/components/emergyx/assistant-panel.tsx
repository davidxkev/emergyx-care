'use client';

import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { Bot, Loader2, MessageSquarePlus, SendHorizonal } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import type { AgentStatus, ChatMessage, ChatThread, Mode, ThreadDetailResponse } from '@/lib/types';
import { formatTimestamp, gemmaStatusLabel } from '@/lib/format';

interface AssistantPanelProps {
  mode: Mode;
  status: AgentStatus | null;
  threads: ChatThread[];
  activeThread: ThreadDetailResponse | null;
  loading: boolean;
  thinkingEnabled: boolean;
  showThreadChips?: boolean;
  onNewThread: () => Promise<void> | void;
  onSelectThread: (threadId: number) => Promise<void> | void;
  onSend: (question: string) => Promise<void> | void;
}

const promptChips = [
  'What happened today?',
  'Why was I alerted?',
  'Was the room dark?',
  'Summarize today for my sister.',
  'Any likely falls this week?',
  'Generate today’s report.',
];

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user';
  const evidence = message.metadata?.evidence ?? [];
  const thinking = message.metadata?.thinking?.trim() ?? '';
  const displayContent =
    message.content.trim() || (!isUser && thinking ? 'Gemma is reasoning…' : '');

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={
          isUser
            ? 'max-w-[92%] rounded-2xl rounded-br-md bg-primary px-3 py-2.5 text-sm text-primary-foreground shadow-sm sm:max-w-[80%] sm:px-4 sm:py-3'
            : 'max-w-[94%] rounded-2xl rounded-bl-md border border-border bg-background px-3 py-2.5 text-sm text-foreground shadow-sm sm:max-w-[85%] sm:px-4 sm:py-3'
        }
      >
        {displayContent ? (
          <div className="whitespace-pre-wrap leading-6">{displayContent}</div>
        ) : null}
        {!isUser && thinking ? (
          <details
            className="mt-3 rounded-xl border border-border/70 bg-muted/40 p-2.5 text-xs text-muted-foreground sm:p-3"
            open={message.id < 0}
          >
            <summary className="cursor-pointer font-medium text-foreground">
              Gemma reasoning
            </summary>
            <div className="mt-3 whitespace-pre-wrap leading-6">{thinking}</div>
          </details>
        ) : null}
        {!isUser && evidence.length > 0 ? (
          <details className="mt-3 rounded-xl border border-border/70 bg-muted/40 p-2.5 text-xs text-muted-foreground sm:p-3">
            <summary className="cursor-pointer font-medium text-foreground">
              Used local context
            </summary>
            <div className="mt-3 space-y-2">
              {evidence.map((item, index) => (
                <div
                  key={`${item.kind}-${item.timestamp ?? 'na'}-${index}`}
                  className="rounded-lg border border-border bg-card px-3 py-2"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                      {item.kind}
                    </span>
                    <span className="text-[11px] text-muted-foreground">
                      {formatTimestamp(item.timestamp)}
                    </span>
                  </div>
                  <p className="mt-1 text-sm font-medium text-foreground">
                    {item.label}
                  </p>
                  <p className="mt-1 leading-5 text-muted-foreground">{item.text}</p>
                </div>
              ))}
            </div>
          </details>
        ) : null}
        <div className="mt-2 text-[11px] text-muted-foreground">
          {formatTimestamp(message.created_at)}
        </div>
      </div>
    </div>
  );
}

export function AssistantPanel({
  mode,
  status,
  threads,
  activeThread,
  loading,
  thinkingEnabled,
  showThreadChips = true,
  onNewThread,
  onSelectThread,
  onSend,
}: AssistantPanelProps) {
  const [draft, setDraft] = useState('');
  const messages = activeThread?.messages ?? [];
  const scrollViewportRef = useRef<HTMLDivElement | null>(null);
  const lastMessage = messages[messages.length - 1];
  const hasStreamingAssistantThinking =
    lastMessage?.role === 'assistant' &&
    Boolean(lastMessage.metadata?.thinking?.trim());
  const hasStreamingAssistantContent =
    lastMessage?.role === 'assistant' && Boolean(lastMessage.content.trim());

  const hasMessages = messages.length > 0;
  const threadChips = useMemo(() => threads.slice(0, 5), [threads]);

  useEffect(() => {
    const viewport = scrollViewportRef.current;
    if (!viewport) {
      return;
    }

    viewport.scrollTo({
      top: viewport.scrollHeight,
      behavior: 'smooth',
    });
  }, [
    hasStreamingAssistantContent,
    hasStreamingAssistantThinking,
    loading,
    messages.length,
    lastMessage?.content,
    lastMessage?.metadata?.thinking,
  ]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const question = draft.trim();
    if (!question) {
      return;
    }
    setDraft('');
    await onSend(question);
  }

  return (
    <section className="rounded-xl border border-border bg-card p-3 shadow-sm sm:rounded-2xl sm:p-6">
      <div className="flex flex-col gap-4 border-b border-border pb-5 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-2">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary sm:h-11 sm:w-11 sm:rounded-2xl">
              <Bot className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold tracking-tight sm:text-xl">
                Gemma Caregiver Assistant
              </h2>
              <p className="text-sm text-muted-foreground">
                Ask about today’s events, alerts, or safety patterns.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
            <span className="rounded-full bg-muted px-3 py-1">
              {gemmaStatusLabel(status)}
            </span>
            <span className="rounded-full bg-muted px-3 py-1">
              {mode === 'live' ? 'LIVE mode' : 'DEMO mode'}
            </span>
            <span className="rounded-full bg-muted px-3 py-1">
              Thinking {thinkingEnabled ? 'enabled' : 'disabled'}
            </span>
            <span className="rounded-full bg-muted px-3 py-1">
              Uses local evidence only
            </span>
            <span className="rounded-full bg-muted px-3 py-1">
              Alert decisions depend on Settings
            </span>
          </div>
        </div>
        <Button className="w-full sm:w-auto" variant="outline" onClick={() => void onNewThread()}>
          <MessageSquarePlus className="mr-2 h-4 w-4" />
          New chat
        </Button>
      </div>

      {showThreadChips && threadChips.length > 0 ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {threadChips.map((thread) => (
            <button
              key={thread.id}
              type="button"
              onClick={() => void onSelectThread(thread.id)}
              className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                activeThread?.thread.id === thread.id
                  ? 'border-primary/50 bg-primary/10 text-primary'
                  : 'border-border bg-background text-muted-foreground hover:bg-accent'
              }`}
            >
              {thread.title}
            </button>
          ))}
        </div>
      ) : null}

      <div
        ref={scrollViewportRef}
        className="mt-4 h-[58vh] min-h-[360px] overflow-y-auto rounded-xl bg-muted/30 p-2.5 sm:mt-5 sm:h-[420px] sm:rounded-2xl sm:p-4"
      >
        {hasMessages ? (
          <div className="space-y-4">
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}
            {loading && !hasStreamingAssistantContent && !hasStreamingAssistantThinking ? (
              <div className="flex justify-start">
                <div className="rounded-2xl rounded-bl-md border border-border bg-background px-4 py-3 text-sm text-muted-foreground shadow-sm">
                  <span className="inline-flex items-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Gemma is preparing a caregiver explanation…
                  </span>
                </div>
              </div>
            ) : null}
          </div>
        ) : (
          <div className="flex h-full flex-col justify-between gap-6">
            <div className="rounded-xl border border-dashed border-border bg-background px-4 py-4 sm:rounded-2xl sm:px-5 sm:py-6">
              <p className="text-sm leading-6 text-muted-foreground">
                Gemma uses local evidence only. Alert decisions depend on the
                configured notification mode and pattern monitor. Emergyx Care is
                not a medical device.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {promptChips.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => setDraft(prompt)}
                  className="rounded-full border border-border bg-background px-3 py-2 text-sm text-foreground transition hover:bg-accent"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {!hasMessages ? null : (
        <div className="mt-4 flex flex-wrap gap-2">
          {promptChips.slice(0, 4).map((prompt) => (
            <button
              key={prompt}
              type="button"
              onClick={() => setDraft(prompt)}
              className="rounded-full border border-border bg-background px-3 py-1.5 text-xs text-muted-foreground transition hover:bg-accent"
            >
              {prompt}
            </button>
          ))}
        </div>
      )}

      <form onSubmit={handleSubmit} className="mt-4 flex gap-2 sm:gap-3">
        <Input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Ask Gemma..."
          className="h-12 min-w-0 rounded-xl bg-background"
        />
        <Button type="submit" className="h-12 shrink-0 rounded-xl px-4 sm:px-5" disabled={loading}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <SendHorizonal className="h-4 w-4" />}
        </Button>
      </form>
    </section>
  );
}
