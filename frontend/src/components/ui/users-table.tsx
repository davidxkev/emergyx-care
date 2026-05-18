'use client';

import { memo } from 'react';
import { motion } from 'framer-motion';
import {
  Calendar,
  Circle,
  Lightbulb,
  MapPin,
  ShieldAlert,
  UserRound,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { eventLabel, formatTimestamp } from '@/lib/format';
import type { EventRead } from '@/lib/types';

interface UsersTableProps {
  events: EventRead[];
  onOpenResidents: () => void;
}

function EventIcon({ eventType }: { eventType: string }) {
  if (eventType === 'fall_detected') {
    return <ShieldAlert className="h-5 w-5 text-red-500" />;
  }
  if (eventType === 'illuminance') {
    return <Lightbulb className="h-5 w-5 text-amber-500" />;
  }
  return <UserRound className="h-5 w-5 text-blue-500" />;
}

export const UsersTable = memo(({ events, onOpenResidents }: UsersTableProps) => {
  return (
    <div className="border-border bg-card/75 rounded-2xl border p-3 shadow-sm sm:p-6">
      <div className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h3 className="text-lg font-semibold sm:text-xl">Live Sensor Timeline</h3>
          <p className="text-muted-foreground text-sm">
            Real-time records from the local care timeline
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={onOpenResidents}>
          Open residents
        </Button>
      </div>

      <div className="space-y-2">
        {events.length > 0 ? (
          events.slice(0, 8).map((event, index) => (
            <motion.div
              key={event.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.05 }}
              className="group hover:bg-accent/50 flex flex-col items-start gap-4 rounded-lg p-4 transition-colors sm:flex-row sm:items-center"
            >
              <div className="flex w-full items-center gap-4 sm:w-auto">
                <div className="border-border bg-background flex h-10 w-10 items-center justify-center rounded-full border">
                  <EventIcon eventType={event.event_type} />
                </div>

                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h4 className="truncate text-sm font-medium">
                      {eventLabel(event)}
                    </h4>
                    <span className="rounded-full bg-blue-500/10 px-2 py-1 text-xs font-medium text-blue-500">
                      Live sensor
                    </span>
                    <span className="rounded-full bg-slate-500/10 px-2 py-1 text-xs font-medium text-slate-600 dark:text-slate-300">
                      {event.sensor_id}
                    </span>
                  </div>
                  <div className="text-muted-foreground mt-1 flex flex-col gap-2 text-xs sm:flex-row sm:items-center sm:gap-4">
                    <div className="flex items-center gap-1">
                      <MapPin className="h-3 w-3" />
                      <span className="truncate">{event.room}</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <Circle className="h-3 w-3" />
                      <span className="truncate">{event.value}</span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="ml-auto flex items-center gap-3">
                <div className="text-muted-foreground flex items-center gap-1 text-xs">
                  <Calendar className="h-3 w-3" />
                  <span>{formatTimestamp(event.timestamp)}</span>
                </div>
              </div>
            </motion.div>
          ))
        ) : (
          <div className="text-muted-foreground rounded-lg border border-dashed px-4 py-8 text-sm">
            No live sensor rows yet. Make sure ingestion is running and the sensor is
            sending updates.
          </div>
        )}
      </div>
    </div>
  );
});

UsersTable.displayName = 'UsersTable';
