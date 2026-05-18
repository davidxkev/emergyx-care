import { Suspense } from 'react';
import { ChatDashboard } from '@/components/mvpblocks/chat';

export default function ChatPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-background" />}>
      <ChatDashboard />
    </Suspense>
  );
}
