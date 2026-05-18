'use client';

import { memo } from 'react';
import { useTheme } from 'next-themes';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  useSidebar,
} from '@/components/ui/sidebar';
import {
  LayoutDashboard,
  MessageSquare,
  FileText,
  Database,
  Settings,
  Moon,
  Sun,
  User,
} from 'lucide-react';

const menuItems = [
  { title: 'Overview', icon: LayoutDashboard, href: '/dashboard' },
  { title: 'Chat', icon: MessageSquare, href: '/chat?mode=live' },
  { title: 'Reports', icon: FileText, href: '/reports' },
  { title: 'Sensors', icon: Database, href: '/sensors' },
  { title: 'Residents', icon: User, href: '/residents' },
  { title: 'Settings', icon: Settings, href: '/settings' },
];

export const AdminSidebar = memo(() => {
  const { theme, setTheme } = useTheme();
  const pathname = usePathname();
  const { isMobile, setOpenMobile } = useSidebar();
  const closeMobileSidebar = () => {
    if (isMobile) {
      setOpenMobile(false);
    }
  };

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild>
              <Link prefetch={false} href="/dashboard" onClick={closeMobileSidebar}>
                <div className="bg-primary text-primary-foreground flex aspect-square size-8 items-center justify-center rounded-lg">
                  <LayoutDashboard className="h-5 w-5" />
                </div>
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-semibold">Emergyx Care</span>
                  <span className="truncate text-xs">Local caregiver hub</span>
                </div>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Navigation</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {menuItems.map((item) => {
                const Icon = item.icon;
                const isActive =
                  (item.href === '/dashboard' && pathname === '/dashboard') ||
                  (item.href.startsWith('/chat') && pathname === '/chat') ||
                  (item.href.startsWith('/reports') && pathname === '/reports') ||
                  (item.href.startsWith('/residents') && pathname === '/residents') ||
                  (item.href.startsWith('/sensors') && pathname === '/sensors') ||
                  (item.href.startsWith('/settings') && pathname === '/settings');
                return (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton asChild isActive={isActive}>
                      <Link prefetch={false} href={item.href} onClick={closeMobileSidebar}>
                        <Icon />
                        <span>{item.title}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            >
              {theme === 'dark' ? <Sun /> : <Moon />}
              <span>{theme === 'dark' ? 'Light Mode' : 'Dark Mode'}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
});

AdminSidebar.displayName = 'AdminSidebar';
