import { Suspense } from 'react';
import { SensorsDashboard } from '@/components/mvpblocks/sensors';

export default function SensorsPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-background" />}>
      <SensorsDashboard />
    </Suspense>
  );
}
