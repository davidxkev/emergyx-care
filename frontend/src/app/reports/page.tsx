import { Suspense } from 'react';
import { ReportsDashboard } from '@/components/mvpblocks/reports';

export default function ReportsPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-background" />}>
      <ReportsDashboard />
    </Suspense>
  );
}
