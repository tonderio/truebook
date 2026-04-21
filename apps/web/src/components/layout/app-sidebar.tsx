"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  FolderKanban,
  Sparkles,
  Settings,
  HelpCircle,
  LogOut,
  BookOpen,
  ChevronLeft,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";

const mainNav = [
  { label: "Resumen", href: "/", icon: LayoutDashboard },
  { label: "Corridas", href: "/processes", icon: FolderKanban },
  { label: "AI Insights", href: "/ai", icon: Sparkles },
];

const bottomNav = [
  { label: "Configuración", href: "/settings", icon: Settings },
  { label: "Ayuda", href: "#", icon: HelpCircle },
];

type AppSidebarProps = {
  collapsed?: boolean;
  onToggle?: () => void;
};

export function AppSidebar({ collapsed, onToggle }: AppSidebarProps) {
  const pathname = usePathname();

  function isActive(href: string) {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  }

  return (
    <aside
      className={cn(
        "flex flex-col h-screen bg-white border-r border-gray-200 transition-all duration-200",
        collapsed ? "w-16" : "w-[260px]"
      )}
    >
      {/* Logo */}
      <div className="flex items-center justify-between h-16 px-4 shrink-0">
        {!collapsed && (
          <Link href="/" className="flex items-center gap-2.5">
            <BookOpen className="h-6 w-6 text-brand-500" />
            <span className="text-lg font-bold text-gray-900 tracking-tight">
              TrueBook
            </span>
          </Link>
        )}
        {collapsed && (
          <Link href="/" className="mx-auto">
            <BookOpen className="h-6 w-6 text-brand-500" />
          </Link>
        )}
        {!collapsed && (
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-gray-400 hover:text-gray-600"
            onClick={onToggle}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
        )}
      </div>

      <Separator />

      {/* Navigation */}
      <ScrollArea className="flex-1 py-4">
        <div className="px-3 space-y-1">
          {!collapsed && (
            <p className="px-3 mb-2 text-[11px] font-medium text-gray-400 uppercase tracking-wider">
              Menú Principal
            </p>
          )}
          {mainNav.map(({ label, href, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 h-10 text-sm font-medium transition-colors",
                isActive(href)
                  ? "bg-gray-100 text-gray-900"
                  : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
              )}
            >
              <Icon
                className={cn(
                  "h-5 w-5 shrink-0",
                  isActive(href) ? "text-brand-500" : "text-gray-400"
                )}
              />
              {!collapsed && label}
            </Link>
          ))}
        </div>

        {/* AI feature card */}
        {!collapsed && (
          <div className="mx-3 mt-8 p-4 rounded-xl bg-brand-50 border border-brand-200">
            <div className="flex items-center gap-2 mb-2">
              <Sparkles className="h-4 w-4 text-brand-600" />
              <span className="text-sm font-semibold text-brand-700">
                AI Copilot
              </span>
            </div>
            <p className="text-xs text-brand-600 leading-relaxed">
              Analiza reconciliaciones con inteligencia artificial.
            </p>
            <Button
              size="sm"
              variant="outline"
              className="mt-3 w-full text-brand-600 border-brand-300 hover:bg-brand-100 text-xs h-8"
              asChild
            >
              <Link href="/ai">Explorar</Link>
            </Button>
          </div>
        )}
      </ScrollArea>

      {/* Bottom nav */}
      <div className="p-3 space-y-1 shrink-0">
        <Separator className="mb-3" />
        {bottomNav.map(({ label, href, icon: Icon }) => (
          <Link
            key={label}
            href={href}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 h-10 text-sm font-medium transition-colors",
              isActive(href)
                ? "bg-gray-100 text-gray-900"
                : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
            )}
          >
            <Icon className="h-5 w-5 text-gray-400 shrink-0" />
            {!collapsed && label}
          </Link>
        ))}
        <button className="flex items-center gap-3 rounded-lg px-3 h-10 text-sm font-medium text-red-600 hover:bg-red-50 w-full transition-colors">
          <LogOut className="h-5 w-5 shrink-0" />
          {!collapsed && "Cerrar Sesión"}
        </button>
      </div>
    </aside>
  );
}
