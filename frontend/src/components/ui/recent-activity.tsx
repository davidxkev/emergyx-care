'use client';

import { memo, useMemo } from 'react';
import { motion } from 'framer-motion';
import { BellRing, Home, Lightbulb, ShieldAlert } from 'lucide-react';

import { eventLabel, formatTimestamp } from '@/lib/format';
import type { AlertRead, EventRead } from '@/lib/types';

interface RecentActivityProps {
  events: EventRead[];
  alerts: AlertRead[];
}

type ActivityRow = {
  key: string;
  action: string;
  actor: string;
  time: string;
  icon: typeof Home;
  color: string;
};

export const RecentActivity = memo(({ events, alerts }: RecentActivityProps) => {
  const items = useMemo<ActivityRow[]>(() => {
    const eventRows = events.slice(0, 4).map((event) => ({
      key: `event-${event.id}`,
      action: eventLabel(event),
      actor: `${event.room} · ${event.sensor_id}`,
      time: formatTimestamp(event.timestamp),
      icon:
        event.event_type === 'illuminance'
          ? Lightbulb
          : event.event_type === 'fall_detected'
            ? ShieldAlert
            : Home,
      color:
        event.event_type === 'fall_detected'
          ? 'text-red-500'
          : event.event_type === 'illuminance'
            ? 'text-amber-500'
            : 'text-blue-500',
    }));

    const alertRows = alerts.slice(0, 2).map((alert) => ({
      key: `alert-${alert.id}`,
      action: alert.sent_success ? 'Rule-based alert sent' : 'Alert delivery pending',
      actor: `${alert.sent_channel} · ${alert.alert_type.replace(/_/g, ' ')}`,
      time: formatTimestamp(alert.timestamp),
      icon: BellRing,
      color: alert.sent_success ? 'text-green-500' : 'text-red-500',
    }));

    return [...alertRows, ...eventRows].slice(0, 6);
  }, [alerts, events]);

  return (
    <div className="border-border bg-card/75 rounded-2xl border p-6 shadow-sm">
      <h3 className="mb-4 text-xl font-semibold">Recent Live Activity</h3>
      <div className="space-y-3">
        {items.length > 0 ? (
          items.map((activity, index) => {
            const Icon = activity.icon;
            return (
              <motion.div
                key={activity.key}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.08 }}
                className="hover:bg-accent/50 flex items-center gap-3 rounded-lg p-2 transition-colors"
              >
                <div className="bg-accent/50 rounded-lg p-2">
                  <Icon className={`h-4 w-4 ${activity.color}`} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium">{activity.action}</div>
                  <div className="text-muted-foreground truncate text-xs">
                    {activity.actor}
                  </div>
                </div>
                <div className="text-muted-foreground text-xs">
                  {activity.time}
                </div>
              </motion.div>
            );
          })
        ) : (
          <div className="text-muted-foreground rounded-lg border border-dashed px-4 py-6 text-sm">
            No live sensor activity has been recorded yet.
          </div>
        )}
      </div>
    </div>
  );
});

RecentActivity.displayName = 'RecentActivity';
