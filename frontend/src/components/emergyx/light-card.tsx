import type { LightContext, ModeSnapshot } from '@/lib/types';
import { formatTimestamp } from '@/lib/format';

export function LightCard({
  light,
  snapshot,
}: {
  light: LightContext | null | undefined;
  snapshot: ModeSnapshot | null;
}) {
  return (
    <section className="rounded-2xl border border-border bg-card p-6 shadow-sm">
      <div>
        <h3 className="text-lg font-semibold tracking-tight">Light Context</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Light is context only, not a cause.
        </p>
      </div>

      <div className="mt-5 space-y-3">
        <div className="rounded-xl bg-muted/30 px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            Latest reading
          </p>
          <p className="mt-2 text-2xl font-semibold">
            {light && typeof light.lux === 'number'
              ? `${light.lux.toFixed(1)} lux`
              : 'No reading'}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {light?.category ? light.category.replace(/_/g, ' ') : 'No light context available'}
          </p>
        </div>
        <div className="rounded-xl bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
          Latest update: {formatTimestamp(light?.timestamp ?? snapshot?.last_event_timestamp ?? null)}
        </div>
      </div>
    </section>
  );
}
