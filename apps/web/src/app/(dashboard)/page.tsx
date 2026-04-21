"use client";

import { useQuery } from "@tanstack/react-query";
import { Header } from "@/components/layout/header";
import { processApi, formatMoney, MONTHS, type Process } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  FolderKanban,
  CheckCircle2,
  Loader2,
  AlertTriangle,
  ArrowUpRight,
  Plus,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { format } from "date-fns";
import { es } from "date-fns/locale";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    completed: "bg-[var(--status-success)]",
    running: "bg-[var(--status-info)]",
    failed: "bg-[var(--status-error)]",
    pending: "bg-[var(--status-warning)]",
  };
  const labels: Record<string, string> = {
    completed: "Completado",
    running: "En proceso",
    failed: "Fallido",
    pending: "Pendiente",
  };
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-gray-600">
      <span className={`w-2 h-2 rounded-full ${colors[status] ?? "bg-gray-300"}`} />
      {labels[status] ?? status}
    </span>
  );
}

function getMonthlyActivity(processes: Process[]) {
  const now = new Date();
  const months: { month: string; corridas: number }[] = [];
  for (let i = 5; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const label = MONTHS[d.getMonth()]!.slice(0, 3);
    const count = processes.filter((p) => {
      const pd = new Date(p.created_at);
      return pd.getMonth() === d.getMonth() && pd.getFullYear() === d.getFullYear();
    }).length;
    months.push({ month: label, corridas: count });
  }
  return months;
}

export default function DashboardPage() {
  const { data: processes, isLoading } = useQuery({
    queryKey: ["processes"],
    queryFn: () => processApi.list(),
    refetchInterval: 10_000,
  });

  const total = processes?.length ?? 0;
  const completed = processes?.filter((p) => p.status === "completed").length ?? 0;
  const running = processes?.filter((p) => p.status === "running").length ?? 0;
  const failed = processes?.filter((p) => p.status === "failed").length ?? 0;
  const chartData = processes ? getMonthlyActivity(processes) : [];
  const recent = processes?.slice(0, 6) ?? [];

  const stats = [
    {
      label: "Total Corridas",
      value: total,
      icon: FolderKanban,
      badgeBg: "bg-[var(--badge-teal-bg)]",
      badgeIcon: "text-[var(--badge-teal-icon)]",
    },
    {
      label: "Completadas",
      value: completed,
      icon: CheckCircle2,
      badgeBg: "bg-[var(--badge-green-bg)]",
      badgeIcon: "text-[var(--badge-green-icon)]",
    },
    {
      label: "En Proceso",
      value: running,
      icon: Loader2,
      badgeBg: "bg-[var(--badge-blue-bg)]",
      badgeIcon: "text-[var(--badge-blue-icon)]",
    },
    {
      label: "Fallidas",
      value: failed,
      icon: AlertTriangle,
      badgeBg: "bg-[var(--badge-red-bg)]",
      badgeIcon: "text-[var(--badge-red-icon)]",
    },
  ];

  return (
    <>
      <Header title="Dashboard" subtitle="Resumen de actividad de reconciliación" />

      <div className="p-6 space-y-6">
        {/* KPI Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {stats.map(({ label, value, icon: Icon, badgeBg, badgeIcon }) => (
            <div key={label} className="bg-white border border-gray-200 rounded-xl p-5">
              <div className={`inline-flex items-center justify-center w-10 h-10 rounded-lg ${badgeBg}`}>
                <Icon className={`h-5 w-5 ${badgeIcon}`} />
              </div>
              <p className="mt-4 text-sm text-gray-500">{label}</p>
              {isLoading ? (
                <Skeleton className="h-8 w-16 mt-1" />
              ) : (
                <p className="mt-1 text-2xl font-bold text-gray-900 tracking-tight">{value}</p>
              )}
            </div>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Monthly activity chart */}
          <div className="lg:col-span-2 bg-white border border-gray-200 rounded-xl p-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-semibold text-gray-900">Actividad Mensual</h2>
              <Button variant="outline" size="sm" className="text-xs" asChild>
                <Link href="/processes">
                  Ver todo <ArrowUpRight className="ml-1 h-3 w-3" />
                </Link>
              </Button>
            </div>
            {isLoading ? (
              <Skeleton className="h-48 w-full" />
            ) : (
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="colorCorridas" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="var(--primary)" stopOpacity={0.15} />
                      <stop offset="95%" stopColor="var(--primary)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis dataKey="month" tick={{ fontSize: 12, fill: "var(--muted-foreground)" }} />
                  <YAxis tick={{ fontSize: 12, fill: "var(--muted-foreground)" }} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{
                      background: "white",
                      border: "1px solid var(--border)",
                      borderRadius: 8,
                      fontSize: 13,
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="corridas"
                    stroke="var(--primary)"
                    strokeWidth={2}
                    fill="url(#colorCorridas)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* Quick actions + recent */}
          <div className="space-y-6">
            <div className="bg-white border border-gray-200 rounded-xl p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Acciones Rápidas</h2>
              <Button className="w-full bg-brand-500 hover:bg-brand-600" asChild>
                <Link href="/processes/new">
                  <Plus className="mr-2 h-4 w-4" /> Nueva Corrida
                </Link>
              </Button>
            </div>
          </div>
        </div>

        {/* Recent processes table */}
        <div className="bg-white border border-gray-200 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Corridas Recientes</h2>
          {isLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : recent.length === 0 ? (
            <p className="text-sm text-gray-400 text-center py-8">
              No hay corridas aún. Crea la primera.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-gray-500 font-medium">
                    <td className="pb-3">Nombre</td>
                    <td className="pb-3">Período</td>
                    <td className="pb-3">Estado</td>
                    <td className="pb-3">Progreso</td>
                    <td className="pb-3">Creado</td>
                    <td className="pb-3" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {recent.map((p) => (
                    <tr key={p.id} className="hover:bg-gray-50 transition-colors">
                      <td className="py-3 font-medium text-gray-900">{p.name}</td>
                      <td className="py-3 text-gray-600">
                        {p.period_year}-{String(p.period_month).padStart(2, "0")}
                      </td>
                      <td className="py-3">
                        <StatusDot status={p.status} />
                      </td>
                      <td className="py-3">
                        <div className="flex items-center gap-2">
                          <div className="w-20 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all ${
                                p.status === "failed"
                                  ? "bg-red-500"
                                  : p.status === "completed"
                                  ? "bg-green-500"
                                  : "bg-brand-500"
                              }`}
                              style={{ width: `${p.progress}%` }}
                            />
                          </div>
                          <span className="text-xs text-gray-500">{p.progress}%</span>
                        </div>
                      </td>
                      <td className="py-3 text-gray-500">
                        {format(new Date(p.created_at), "dd MMM, HH:mm", { locale: es })}
                      </td>
                      <td className="py-3 text-right">
                        <Button variant="ghost" size="sm" className="text-brand-500 text-xs" asChild>
                          <Link href={`/processes/${p.id}`}>Ver</Link>
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
