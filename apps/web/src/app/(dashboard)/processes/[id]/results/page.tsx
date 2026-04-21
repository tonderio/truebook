"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { Header } from "@/components/layout/header";
import {
  processApi,
  resultsApi,
  formatMoney,
  downloadBlob,
  type FeesResult,
  type KushkiResult,
  type BanregioResult,
  type ConciliationRecord,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ScrollArea } from "@/components/ui/scroll-area";
import Link from "next/link";
import {
  ArrowLeft,
  Download,
  Loader2,
  DollarSign,
  Users,
  CalendarDays,
  ArrowUpDown,
  TrendingUp,
  ArrowDown,
  ArrowUp,
  CheckCircle2,
  AlertTriangle,
} from "lucide-react";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

function KpiCard({
  label,
  value,
  icon: Icon,
  badgeBg,
  badgeIcon,
}: {
  label: string;
  value: string | number;
  icon: React.ElementType;
  badgeBg: string;
  badgeIcon: string;
}) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5">
      <div className={`inline-flex items-center justify-center w-10 h-10 rounded-lg ${badgeBg}`}>
        <Icon className={`h-5 w-5 ${badgeIcon}`} />
      </div>
      <p className="mt-3 text-sm text-gray-500">{label}</p>
      <p className="mt-1 text-2xl font-bold text-gray-900 tracking-tight">{value}</p>
    </div>
  );
}

// ── FEES Tab ──

function FeesTab({ processId }: { processId: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ["fees", processId],
    queryFn: () => resultsApi.fees(processId),
  });
  const [exporting, setExporting] = useState(false);

  async function handleExport() {
    setExporting(true);
    try {
      const { blob, filename } = await resultsApi.exportFees(processId);
      downloadBlob(blob, filename);
    } finally {
      setExporting(false);
    }
  }

  if (isLoading) return <Skeleton className="h-96 w-full" />;
  if (!data) return <p className="text-gray-400 text-sm py-8 text-center">Sin datos de FEES</p>;

  const chartData = (data.merchant_summary ?? []).slice(0, 10).map((m) => ({
    name: (m.merchant_name || m.merchant_id).slice(0, 14),
    fee: m.total_fee,
    txs: m.tx_count,
  }));

  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <Button variant="outline" size="sm" onClick={handleExport} disabled={exporting}>
          {exporting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Download className="mr-2 h-4 w-4" />}
          Exportar FEES
        </Button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <KpiCard label="Total FEES" value={`$${formatMoney(data.total_fees)}`} icon={DollarSign} badgeBg="bg-[var(--badge-teal-bg)]" badgeIcon="text-[var(--badge-teal-icon)]" />
        <KpiCard label="Merchants" value={data.merchant_summary?.length ?? 0} icon={Users} badgeBg="bg-[var(--badge-blue-bg)]" badgeIcon="text-[var(--badge-blue-icon)]" />
        <KpiCard label="Registros diarios" value={data.daily_breakdown?.length ?? 0} icon={CalendarDays} badgeBg="bg-[var(--badge-purple-bg)]" badgeIcon="text-[var(--badge-purple-icon)]" />
      </div>

      {/* Bar chart */}
      {chartData.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-base">Top 10 Merchants por Fee</CardTitle></CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="name" tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} angle={-20} textAnchor="end" height={60} />
                <YAxis tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} />
                <Tooltip contentStyle={{ background: "white", border: "1px solid var(--border)", borderRadius: 8, fontSize: 13 }} formatter={(v) => [`$${formatMoney(Number(v ?? 0))}`, "Fee"]} />
                <Bar dataKey="fee" fill="var(--primary)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* Merchant table */}
      <Card>
        <CardHeader><CardTitle className="text-base">Resumen por Merchant</CardTitle></CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-xs">Merchant</TableHead>
                <TableHead className="text-xs text-right">Transacciones</TableHead>
                <TableHead className="text-xs text-right">Monto bruto</TableHead>
                <TableHead className="text-xs text-right">Total fee</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(data.merchant_summary ?? []).map((m, i) => (
                <TableRow key={i}>
                  <TableCell className="font-medium text-gray-900">{m.merchant_name || m.merchant_id}</TableCell>
                  <TableCell className="text-right text-gray-600">{m.tx_count.toLocaleString()}</TableCell>
                  <TableCell className="text-right text-gray-600">${formatMoney(m.gross_amount)}</TableCell>
                  <TableCell className="text-right font-medium text-gray-900">${formatMoney(m.total_fee)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

// ── Kushki Tab ──

function KushkiTab({ processId }: { processId: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ["kushki", processId],
    queryFn: () => resultsApi.kushki(processId),
  });
  const [exporting, setExporting] = useState(false);

  async function handleExport() {
    setExporting(true);
    try {
      const { blob, filename } = await resultsApi.exportKushki(processId);
      downloadBlob(blob, filename);
    } finally {
      setExporting(false);
    }
  }

  if (isLoading) return <Skeleton className="h-96 w-full" />;
  if (!data) return <p className="text-gray-400 text-sm py-8 text-center">Sin datos de Kushki</p>;

  const chartData = (data.daily_summary ?? []).map((d) => ({
    date: d.date,
    gross: parseFloat(String(d.gross_amount ?? 0)),
    net: parseFloat(String(d.net_deposit ?? 0)),
    commission: parseFloat(String(d.commission ?? 0)),
  }));

  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <Button variant="outline" size="sm" onClick={handleExport} disabled={exporting}>
          {exporting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Download className="mr-2 h-4 w-4" />}
          Exportar Kushki
        </Button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <KpiCard label="Net Deposit Total" value={`$${formatMoney(data.total_net_deposit)}`} icon={TrendingUp} badgeBg="bg-[var(--badge-green-bg)]" badgeIcon="text-[var(--badge-green-icon)]" />
        <KpiCard label="Días procesados" value={data.daily_summary?.length ?? 0} icon={CalendarDays} badgeBg="bg-[var(--badge-blue-bg)]" badgeIcon="text-[var(--badge-blue-icon)]" />
      </div>

      {chartData.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-base">Desglose Diario</CardTitle></CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
                <YAxis tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} />
                <Tooltip contentStyle={{ background: "white", border: "1px solid var(--border)", borderRadius: 8, fontSize: 13 }} formatter={(v) => `$${formatMoney(Number(v ?? 0))}`} />
                <Legend />
                <Line type="monotone" dataKey="gross" stroke="#6366f1" strokeWidth={2} dot={false} name="Bruto" />
                <Line type="monotone" dataKey="net" stroke="#10b981" strokeWidth={2} dot={false} name="Neto" />
                <Line type="monotone" dataKey="commission" stroke="#f59e0b" strokeWidth={2} dot={false} name="Comisión" />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader><CardTitle className="text-base">Resumen Diario</CardTitle></CardHeader>
        <CardContent>
          <ScrollArea className="max-h-96">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Fecha</TableHead>
                  <TableHead className="text-xs text-right">Txs</TableHead>
                  <TableHead className="text-xs text-right">Bruto</TableHead>
                  <TableHead className="text-xs text-right">Comisión</TableHead>
                  <TableHead className="text-xs text-right">Rolling Reserve</TableHead>
                  <TableHead className="text-xs text-right">Depósito neto</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(data.daily_summary ?? []).map((d, i) => (
                  <TableRow key={i}>
                    <TableCell className="text-gray-700">{d.date}</TableCell>
                    <TableCell className="text-right text-gray-600">{Number(d.tx_count).toLocaleString()}</TableCell>
                    <TableCell className="text-right text-gray-600">${formatMoney(d.gross_amount)}</TableCell>
                    <TableCell className="text-right text-gray-600">${formatMoney(d.commission)}</TableCell>
                    <TableCell className="text-right text-gray-600">${formatMoney(d.rolling_reserve)}</TableCell>
                    <TableCell className="text-right font-medium text-gray-900">${formatMoney(d.net_deposit)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
}

// ── Banregio Tab ──

function BanregioTab({ processId }: { processId: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ["banregio", processId],
    queryFn: () => resultsApi.banregio(processId),
  });
  const [exporting, setExporting] = useState(false);

  async function handleExport() {
    setExporting(true);
    try {
      const { blob, filename } = await resultsApi.exportBanregio(processId);
      downloadBlob(blob, filename);
    } finally {
      setExporting(false);
    }
  }

  if (isLoading) return <Skeleton className="h-96 w-full" />;
  if (!data) return <p className="text-gray-400 text-sm py-8 text-center">Sin datos de Banregio</p>;

  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <Button variant="outline" size="sm" onClick={handleExport} disabled={exporting}>
          {exporting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Download className="mr-2 h-4 w-4" />}
          Exportar Banregio
        </Button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <KpiCard label="Total abonos" value={`$${formatMoney(data.summary?.total_credits)}`} icon={ArrowDown} badgeBg="bg-[var(--badge-green-bg)]" badgeIcon="text-[var(--badge-green-icon)]" />
        <KpiCard label="Total cargos" value={`$${formatMoney(data.summary?.total_debits)}`} icon={ArrowUp} badgeBg="bg-[var(--badge-red-bg)]" badgeIcon="text-[var(--badge-red-icon)]" />
        <KpiCard label="Movimientos" value={data.movements?.length ?? 0} icon={ArrowUpDown} badgeBg="bg-[var(--badge-blue-bg)]" badgeIcon="text-[var(--badge-blue-icon)]" />
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">Movimientos</CardTitle></CardHeader>
        <CardContent>
          <ScrollArea className="max-h-96">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Fecha</TableHead>
                  <TableHead className="text-xs">Descripción</TableHead>
                  <TableHead className="text-xs text-right">Cargo</TableHead>
                  <TableHead className="text-xs text-right">Abono</TableHead>
                  <TableHead className="text-xs text-right">Ref depósito</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(data.movements ?? []).map((m, i) => (
                  <TableRow key={i}>
                    <TableCell className="text-gray-700">{m.date}</TableCell>
                    <TableCell className="text-gray-600 max-w-xs truncate">{m.description}</TableCell>
                    <TableCell className="text-right text-red-600">
                      {m.debit ? `$${formatMoney(m.debit)}` : "—"}
                    </TableCell>
                    <TableCell className="text-right text-green-600">
                      {m.credit ? `$${formatMoney(m.credit)}` : "—"}
                    </TableCell>
                    <TableCell className="text-right text-gray-600">
                      {m.deposit_ref ? `$${formatMoney(m.deposit_ref)}` : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
}

// ── Conciliaciones Tab ──

const CONC_TYPE_LABELS: Record<string, string> = {
  fees: "FEES",
  kushki_daily: "Kushki Diario",
  kushki_vs_banregio: "Kushki vs Banregio",
};

function ConciliacionesTab({ processId }: { processId: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ["conciliation", processId],
    queryFn: () => resultsApi.conciliation(processId),
  });

  if (isLoading) return <Skeleton className="h-96 w-full" />;
  if (!data || data.length === 0)
    return <p className="text-gray-400 text-sm py-8 text-center">Sin datos de conciliación</p>;

  return (
    <div className="space-y-6">
      {data.map((c) => (
        <Card key={c.id}>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">
                {CONC_TYPE_LABELS[c.conciliation_type] ?? c.conciliation_type}
              </CardTitle>
              <div className="flex gap-2">
                <Badge className="bg-green-100 text-green-700 border-0">
                  <CheckCircle2 className="mr-1 h-3 w-3" />
                  Conciliado: ${formatMoney(c.total_conciliated)}
                </Badge>
                {Number(c.total_difference) > 0 && (
                  <Badge className="bg-amber-100 text-amber-700 border-0">
                    <AlertTriangle className="mr-1 h-3 w-3" />
                    Diferencia: ${formatMoney(c.total_difference)}
                  </Badge>
                )}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {/* Stats */}
            <div className="grid grid-cols-4 gap-4 mb-4">
              <div className="text-center p-3 bg-green-50 rounded-lg">
                <p className="text-2xl font-bold text-green-700">{c.matched?.length ?? 0}</p>
                <p className="text-xs text-green-600">Conciliados</p>
              </div>
              <div className="text-center p-3 bg-amber-50 rounded-lg">
                <p className="text-2xl font-bold text-amber-700">{c.differences?.length ?? 0}</p>
                <p className="text-xs text-amber-600">Diferencias</p>
              </div>
              <div className="text-center p-3 bg-red-50 rounded-lg">
                <p className="text-2xl font-bold text-red-700">{(c.unmatched_kushki as unknown[])?.length ?? 0}</p>
                <p className="text-xs text-red-600">Sin match Kushki</p>
              </div>
              <div className="text-center p-3 bg-purple-50 rounded-lg">
                <p className="text-2xl font-bold text-purple-700">{(c.unmatched_banregio as unknown[])?.length ?? 0}</p>
                <p className="text-xs text-purple-600">Sin match Banregio</p>
              </div>
            </div>

            {/* Matched table for kushki_vs_banregio */}
            {c.conciliation_type === "kushki_vs_banregio" && c.matched && c.matched.length > 0 && (
              <ScrollArea className="max-h-64">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-xs">Fecha</TableHead>
                      <TableHead className="text-xs text-right">Kushki (Col I)</TableHead>
                      <TableHead className="text-xs text-right">Banregio (Col H)</TableHead>
                      <TableHead className="text-xs text-right">Diferencia</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {c.matched.map((m, i) => (
                      <TableRow key={i}>
                        <TableCell className="text-gray-700">{m.date}</TableCell>
                        <TableCell className="text-right text-gray-600">${formatMoney(m.kushki_amount)}</TableCell>
                        <TableCell className="text-right text-gray-600">${formatMoney(m.banregio_amount)}</TableCell>
                        <TableCell className={`text-right font-medium ${Number(m.difference) === 0 ? "text-green-600" : "text-amber-600"}`}>
                          ${formatMoney(m.difference)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </ScrollArea>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

// ── Main Results Page ──

export default function ResultsPage() {
  const { id } = useParams<{ id: string }>();
  const processId = Number(id);

  const { data: process, isLoading } = useQuery({
    queryKey: ["process", processId],
    queryFn: () => processApi.get(processId),
  });

  if (isLoading) {
    return (
      <>
        <Header title="Cargando..." />
        <div className="p-6"><Skeleton className="h-96 w-full" /></div>
      </>
    );
  }

  return (
    <>
      <Header
        title="Resultados"
        subtitle={process ? `${process.name} · ${process.period_year}-${String(process.period_month).padStart(2, "0")}` : ""}
      />

      <div className="p-6">
        <Button variant="ghost" size="sm" className="text-gray-500 mb-6" asChild>
          <Link href={`/processes/${processId}`}>
            <ArrowLeft className="mr-1 h-4 w-4" /> Volver al proceso
          </Link>
        </Button>

        <Tabs defaultValue="fees">
          <TabsList className="mb-6">
            <TabsTrigger value="fees">FEES</TabsTrigger>
            <TabsTrigger value="kushki">Kushki</TabsTrigger>
            <TabsTrigger value="banregio">Banregio</TabsTrigger>
            <TabsTrigger value="conciliaciones">Conciliaciones</TabsTrigger>
          </TabsList>

          <TabsContent value="fees"><FeesTab processId={processId} /></TabsContent>
          <TabsContent value="kushki"><KushkiTab processId={processId} /></TabsContent>
          <TabsContent value="banregio"><BanregioTab processId={processId} /></TabsContent>
          <TabsContent value="conciliaciones"><ConciliacionesTab processId={processId} /></TabsContent>
        </Tabs>
      </div>
    </>
  );
}
