'use client';

import { memo } from 'react';
import { motion } from 'framer-motion';
import {
  ArrowRight,
  Download,
  FileText,
  MessageSquare,
  PlayCircle,
  RefreshCw,
} from 'lucide-react';

import { Button } from '@/components/ui/button';

interface QuickActionsProps {
  onRefresh: () => void;
  onExport: () => void;
  onGenerateWeeklyPdf: () => void;
  onOpenResidents: () => void;
  onOpenChat: () => void;
  onRunDemoFall?: () => void;
  onRunDemoScan?: () => void;
  weeklyPdfLoading?: boolean;
  demoMode?: boolean;
  demoActionLoading?: boolean;
}

const actions = [
  {
    icon: RefreshCw,
    label: 'Refresh live data',
    hint: 'Sensor',
    tone: 'green',
    action: 'refresh',
  },
  {
    icon: MessageSquare,
    label: 'Open Gemma chat',
    hint: 'Live mode',
    tone: 'blue',
    action: 'chat',
  },
  {
    icon: ArrowRight,
    label: 'Open residents',
    hint: 'Care context',
    tone: 'purple',
    action: 'residents',
  },
  {
    icon: Download,
    label: 'Export live timeline',
    hint: 'JSON',
    tone: 'orange',
    action: 'export',
  },
  {
    icon: FileText,
    label: 'Generate weekly PDF',
    hint: 'Gemma 4',
    tone: 'blue',
    action: 'weekly-pdf',
  },
] as const;

const buttonToneClasses: Record<string, string> = {
  blue: 'hover:bg-blue-500/10 hover:border-blue-500/50',
  green: 'hover:bg-green-500/10 hover:border-green-500/50',
  purple: 'hover:bg-purple-500/10 hover:border-purple-500/50',
  orange: 'hover:bg-orange-500/10 hover:border-orange-500/50',
};

const iconToneClasses: Record<string, string> = {
  blue: 'text-blue-500',
  green: 'text-green-500',
  purple: 'text-purple-500',
  orange: 'text-orange-500',
};

export const QuickActions = memo(
  ({
    onRefresh,
    onExport,
    onGenerateWeeklyPdf,
    onOpenResidents,
    onOpenChat,
    onRunDemoFall,
    onRunDemoScan,
    weeklyPdfLoading = false,
    demoMode = false,
    demoActionLoading = false,
  }: QuickActionsProps) => {
    const visibleActions = demoMode
      ? [
          {
            icon: PlayCircle,
            label: 'Simulate likely fall',
            hint: 'Demo',
            tone: 'orange',
            action: 'demo-fall',
          },
          {
            icon: FileText,
            label: 'Run Gemma scan',
            hint: 'Pattern',
            tone: 'blue',
            action: 'demo-scan',
          },
          ...actions,
        ]
      : actions;

    const handleAction = (action: string) => {
      switch (action) {
        case 'demo-fall':
          onRunDemoFall?.();
          break;
        case 'demo-scan':
          onRunDemoScan?.();
          break;
        case 'refresh':
          onRefresh();
          break;
        case 'chat':
          onOpenChat();
          break;
        case 'residents':
          onOpenResidents();
          break;
        case 'export':
          onExport();
          break;
        case 'weekly-pdf':
          onGenerateWeeklyPdf();
          break;
      }
    };

    return (
      <div className="border-border bg-card/75 rounded-2xl border p-6 shadow-sm">
        <h3 className="mb-4 text-xl font-semibold">Quick Actions</h3>
        <div className="space-y-3">
          {visibleActions.map((action) => {
            const Icon = action.icon;
            const isWeeklyPdf = action.action === 'weekly-pdf';
            const isDemoAction = action.action === 'demo-fall' || action.action === 'demo-scan';
            return (
              <motion.div
                key={action.label}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                <Button
                  variant="outline"
                  className={`h-12 w-full justify-start transition-all duration-200 ${buttonToneClasses[action.tone]}`}
                  disabled={(isWeeklyPdf && weeklyPdfLoading) || (isDemoAction && demoActionLoading)}
                  onClick={() => handleAction(action.action)}
                >
                  <Icon className={`mr-3 h-5 w-5 ${iconToneClasses[action.tone]}`} />
                  <span className="font-medium">
                    {isWeeklyPdf && weeklyPdfLoading
                      ? 'Generating weekly PDF'
                      : isDemoAction && demoActionLoading
                        ? 'Running demo'
                        : demoMode && action.action === 'refresh'
                          ? 'Refresh demo data'
                          : demoMode && action.action === 'chat'
                            ? 'Open demo chat'
                        : action.label}
                  </span>
                  <div className="text-muted-foreground ml-auto text-xs">
                    {demoMode && action.action === 'chat' ? 'Demo mode' : action.hint}
                  </div>
                </Button>
              </motion.div>
            );
          })}
        </div>
      </div>
    );
  },
);

QuickActions.displayName = 'QuickActions';
