import { Suspense } from 'react';
import AdminDashboard from '@/components/mvpblocks';

export default function DashboardPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-background" />}>
      <AdminDashboard />
    </Suspense>
  );
}
