'use client';

import { memo } from 'react';
import { motion } from 'framer-motion';
import type { LucideIcon } from 'lucide-react';
import { TrendingUp } from 'lucide-react';

interface DashboardCardProps {
  stat: {
    title: string;
    value: string;
    change: string;
    changeType: 'positive' | 'negative';
    icon: LucideIcon;
    color: string;
    bgColor: string;
    progressClass?: string;
    progress?: number;
  };
  index: number;
}

export const DashboardCard = memo(({ stat, index }: DashboardCardProps) => {
  const Icon = stat.icon;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.1 }}
      whileHover={{ scale: 1.02, transition: { duration: 0.2 } }}
      className="group relative h-full"
    >
      <div className="border-border bg-card/75 relative flex h-full min-h-[190px] overflow-hidden rounded-2xl border p-5 shadow-sm transition-all duration-300 hover:-translate-y-0.5 hover:shadow-lg sm:p-6">
        <div className="from-primary/5 to-primary/10 absolute inset-0 bg-gradient-to-br via-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
        <div className="absolute inset-x-5 top-0 h-px bg-gradient-to-r from-transparent via-white/80 to-transparent dark:via-white/20" />

        <div className="relative flex min-w-0 flex-1 flex-col">
          <div className="mb-4 flex items-start justify-between gap-3">
            <div className={`shrink-0 rounded-xl p-3 ${stat.bgColor}`}>
              <Icon className={`h-6 w-6 ${stat.color}`} />
            </div>

            <div
              className={`min-w-0 rounded-full px-2.5 py-1 text-right text-xs font-semibold ${
                stat.changeType === 'positive'
                  ? 'bg-green-500/10 text-green-600 dark:text-green-300'
                  : 'bg-red-500/10 text-red-600 dark:text-red-300'
              }`}
            >
              <span className="inline-flex max-w-[9rem] items-center gap-1 truncate">
                <TrendingUp
                  className={`h-3.5 w-3.5 shrink-0 ${
                    stat.changeType === 'negative' ? 'rotate-180' : ''
                  }`}
                />
                <span className="truncate">{stat.change}</span>
              </span>
            </div>
          </div>

          <div className="mb-5 min-w-0">
            <h3
              className="text-foreground mb-1 min-h-[4.5rem] text-2xl font-bold leading-tight tracking-tight [overflow-wrap:anywhere] sm:text-3xl"
              title={stat.value}
            >
              {stat.value}
            </h3>
            <p className="text-muted-foreground text-sm font-medium">
              {stat.title}
            </p>
          </div>

          <div className="bg-muted mt-auto h-2 overflow-hidden rounded-full">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${stat.progress ?? 65 + index * 8}%` }}
              transition={{ duration: 1, delay: index * 0.1 }}
              className={`h-full rounded-full ${stat.progressClass ?? (
                index === 0
                  ? 'bg-blue-500'
                  : index === 1
                    ? 'bg-green-500'
                    : index === 2
                      ? 'bg-purple-500'
                      : 'bg-orange-500'
              )}`}
            />
          </div>
        </div>
      </div>
    </motion.div>
  );
});

DashboardCard.displayName = 'DashboardCard';
