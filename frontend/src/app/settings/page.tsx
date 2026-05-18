import { Suspense } from 'react';
import { SettingsDashboard } from '@/components/mvpblocks/settings';

export default function SettingsPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-background" />}>
      <SettingsDashboard />
    </Suspense>
  );
}
