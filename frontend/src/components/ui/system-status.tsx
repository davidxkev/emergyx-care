'use client';

import { memo, useMemo } from 'react';
import { motion } from 'framer-motion';
import { Activity, Database, Shield, Zap } from 'lucide-react';

import { gemmaStatusLabel } from '@/lib/format';
import type { AgentStatus, ModeSnapshot } from '@/lib/types';

interface SystemStatusProps {
  status: AgentStatus | null;
  snapshot: ModeSnapshot | null;
}

function freshnessPercent(ageSeconds?: number | null) {
  if (ageSeconds == null) {
    return 0;
  }
  if (ageSeconds <= 15) {
    return 100;
  }
  if (ageSeconds <= 60) {
    return 85;
  }
  if (ageSeconds <= 300) {
    return 60;
  }
  return 30;
}

export const SystemStatus = memo(({ status, snapshot }: SystemStatusProps) => {
  const statusItems = useMemo(
    () => [
      {
        label: 'Live sensor stream',
        status: snapshot?.last_event_age_human ?? 'No data',
        color: snapshot?.last_event_timestamp ? 'text-green-500' : 'text-red-500',
        icon: Shield,
        percentage: freshnessPercent(snapshot?.last_event_age_seconds),
      },
      {
        label: 'SQLite timeline',
        status: snapshot?.last_event_timestamp ? 'Receiving live rows' : 'Waiting',
        color: snapshot?.last_event_timestamp ? 'text-green-500' : 'text-yellow-500',
        icon: Database,
        percentage: snapshot?.last_event_timestamp ? 95 : 35,
      },
      {
        label: 'Gemma via Ollama',
        status: gemmaStatusLabel(status),
        color: status?.status === 'online' ? 'text-green-500' : 'text-yellow-500',
        icon: Zap,
        percentage: status?.status === 'online' ? 98 : 45,
      },
      {
        label: 'Light context',
        status: snapshot?.light?.category ?? 'No live light',
        color: snapshot?.light ? 'text-amber-500' : 'text-yellow-500',
        icon: Activity,
        percentage: snapshot?.light ? 88 : 25,
      },
    ],
    [snapshot, status],
  );

  return (
    <div className="border-border bg-card/75 rounded-2xl border p-6 shadow-sm">
      <h3 className="mb-4 text-xl font-semibold">System Status</h3>
      <div className="space-y-4">
        {statusItems.map((item, index) => {
          const Icon = item.icon;
          const barClass =
            item.color === 'text-green-500'
              ? 'bg-green-500'
              : item.color === 'text-amber-500' || item.color === 'text-yellow-500'
                ? 'bg-amber-500'
                : 'bg-red-500';
          return (
            <motion.div
              key={item.label}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.1 }}
              className="hover:bg-accent/50 flex cursor-pointer items-center justify-between rounded-lg p-3 transition-colors"
            >
              <div className="flex items-center gap-3">
                <Icon className={`h-4 w-4 ${item.color}`} />
                <span className="text-sm font-medium">{item.label}</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="bg-muted h-2 w-16 overflow-hidden rounded-full">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${item.percentage}%` }}
                    transition={{ duration: 1, delay: index * 0.1 }}
                    className={`h-full rounded-full ${barClass}`}
                  />
                </div>
                <span
                  className={`min-w-[90px] text-right text-sm font-medium ${item.color}`}
                >
                  {item.status}
                </span>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
});

SystemStatus.displayName = 'SystemStatus';
