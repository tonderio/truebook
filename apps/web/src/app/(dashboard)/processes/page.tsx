"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Header } from "@/components/layout/header";
import { processApi, ACQUIRER_COLORS, type Process } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import Link from "next/link";
import { format } from "date-fns";
import { es } from "date-fns/locale";
import {
  Plus,
  Search,
  MoreHorizontal,
  Eye,
  Trash2,
  ArrowUpDown,
} from "lucide-react";

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
    <span className="inline-flex items-center gap-1.5 text-sm text-gray-600">
      <span className={`w-2 h-2 rounded-full ${colors[status] ?? "bg-gray-300"}`} />
      {labels[status] ?? status}
    </span>
  );
}

type SortKey = "id" | "name" | "period" | "status" | "progress" | "created_at";

export default function ProcessListPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("created_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const { data: processes, isLoading } = useQuery({
    queryKey: ["processes"],
    queryFn: () => processApi.list(),
    refetchInterval: 8_000,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => processApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["processes"] }),
  });

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  const filtered = (processes ?? [])
    .filter((p) => {
      if (statusFilter !== "all" && p.status !== statusFilter) return false;
      if (search && !p.name.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    })
    .sort((a, b) => {
      const dir = sortDir === "asc" ? 1 : -1;
      switch (sortKey) {
        case "id":
          return (a.id - b.id) * dir;
        case "name":
          return a.name.localeCompare(b.name) * dir;
        case "period":
          return (a.period_year * 100 + a.period_month - (b.period_year * 100 + b.period_month)) * dir;
        case "status":
          return a.status.localeCompare(b.status) * dir;
        case "progress":
          return (a.progress - b.progress) * dir;
        case "created_at":
          return (new Date(a.created_at).getTime() - new Date(b.created_at).getTime()) * dir;
        default:
          return 0;
      }
    });

  const SortableHeader = ({ label, sortKeyName }: { label: string; sortKeyName: SortKey }) => (
    <button
      className="inline-flex items-center gap-1 hover:text-gray-900 transition-colors"
      onClick={() => toggleSort(sortKeyName)}
    >
      {label}
      <ArrowUpDown className="h-3 w-3" />
    </button>
  );

  return (
    <>
      <Header title="Corridas" subtitle="Gestiona tus procesos de reconciliación" />

      <div className="p-6 space-y-4">
        {/* Toolbar */}
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 flex-1">
            <div className="relative max-w-sm flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              <Input
                placeholder="Buscar corrida..."
                className="pl-9 h-9"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <div className="flex gap-1">
              {["all", "completed", "running", "failed"].map((s) => (
                <Button
                  key={s}
                  variant={statusFilter === s ? "default" : "outline"}
                  size="sm"
                  className={`text-xs h-8 ${statusFilter === s ? "bg-brand-500 hover:bg-brand-600" : ""}`}
                  onClick={() => setStatusFilter(s)}
                >
                  {s === "all" ? "Todos" : s === "completed" ? "Completados" : s === "running" ? "En proceso" : "Fallidos"}
                </Button>
              ))}
            </div>
          </div>
          <Button className="bg-brand-500 hover:bg-brand-600" asChild>
            <Link href="/processes/new">
              <Plus className="mr-2 h-4 w-4" /> Nueva Corrida
            </Link>
          </Button>
        </div>

        {/* Table */}
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
          {isLoading ? (
            <div className="p-6 space-y-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-16 text-gray-400 text-sm">
              {processes?.length === 0
                ? "No hay corridas aún. Crea la primera."
                : "No se encontraron corridas con esos filtros."}
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="text-xs"><SortableHeader label="ID" sortKeyName="id" /></TableHead>
                  <TableHead className="text-xs"><SortableHeader label="Nombre" sortKeyName="name" /></TableHead>
                  <TableHead className="text-xs"><SortableHeader label="Período" sortKeyName="period" /></TableHead>
                  <TableHead className="text-xs">Adquirentes</TableHead>
                  <TableHead className="text-xs"><SortableHeader label="Estado" sortKeyName="status" /></TableHead>
                  <TableHead className="text-xs"><SortableHeader label="Progreso" sortKeyName="progress" /></TableHead>
                  <TableHead className="text-xs"><SortableHeader label="Creado" sortKeyName="created_at" /></TableHead>
                  <TableHead className="text-xs w-10" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((p) => (
                  <TableRow key={p.id} className="cursor-pointer">
                    <TableCell className="text-gray-500 font-mono text-xs">#{p.id}</TableCell>
                    <TableCell className="font-medium text-gray-900">{p.name}</TableCell>
                    <TableCell className="text-gray-600">
                      {p.period_year}-{String(p.period_month).padStart(2, "0")}
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1 flex-wrap">
                        {(p.acquirers ?? []).map((a) => (
                          <Badge
                            key={a}
                            variant="outline"
                            className="text-[10px] font-medium px-1.5 py-0"
                            style={{ borderColor: ACQUIRER_COLORS[a], color: ACQUIRER_COLORS[a] }}
                          >
                            {a}
                          </Badge>
                        ))}
                      </div>
                    </TableCell>
                    <TableCell>
                      <StatusDot status={p.status} />
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              p.status === "failed"
                                ? "bg-red-500"
                                : p.status === "completed"
                                ? "bg-green-500"
                                : "bg-brand-500"
                            }`}
                            style={{ width: `${p.progress}%` }}
                          />
                        </div>
                        <span className="text-xs text-gray-500 w-8">{p.progress}%</span>
                      </div>
                    </TableCell>
                    <TableCell className="text-gray-500 text-xs">
                      {format(new Date(p.created_at), "dd/MM/yyyy HH:mm", { locale: es })}
                    </TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <MoreHorizontal className="h-4 w-4 text-gray-400" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem asChild>
                            <Link href={`/processes/${p.id}`}>
                              <Eye className="mr-2 h-4 w-4" /> Ver detalle
                            </Link>
                          </DropdownMenuItem>
                          {p.status !== "running" && (
                            <DropdownMenuItem
                              className="text-red-600 focus:text-red-600"
                              onClick={() => deleteMutation.mutate(p.id)}
                            >
                              <Trash2 className="mr-2 h-4 w-4" /> Eliminar
                            </DropdownMenuItem>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          {/* Pagination info */}
          {!isLoading && filtered.length > 0 && (
            <div className="px-6 py-3 border-t border-gray-100 text-xs text-gray-500">
              Mostrando {filtered.length} de {processes?.length ?? 0} corridas
            </div>
          )}
        </div>
      </div>
    </>
  );
}
