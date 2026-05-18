export function PrivacyCard() {
  const items = [
    ['Camera', 'None'],
    ['Raw timeline', 'Local only'],
    ['Dashboard', 'Home network only'],
    ['Urgent alerts', 'Rule-based and immediate'],
    ['If Gemma offline', 'Alerts still work'],
  ];

  return (
    <section className="rounded-2xl border border-border bg-card p-6 shadow-sm">
      <div>
        <h3 className="text-lg font-semibold tracking-tight">Privacy & Failsafe</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Emergyx Care keeps urgent detection rule-based and local-first.
        </p>
      </div>
      <div className="mt-5 space-y-3">
        {items.map(([label, value]) => (
          <div
            key={label}
            className="flex items-start justify-between gap-4 rounded-xl bg-muted/30 px-4 py-3"
          >
            <span className="text-sm font-medium text-foreground">{label}</span>
            <span className="text-right text-sm text-muted-foreground">{value}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
