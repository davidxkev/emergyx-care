import { Suspense } from 'react';
import { ResidentsDashboard } from '@/components/mvpblocks/residents';

export default function ResidentsPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-background" />}>
      <ResidentsDashboard />
    </Suspense>
  );
}
