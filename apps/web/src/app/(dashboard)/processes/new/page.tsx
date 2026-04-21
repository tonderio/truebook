"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { Header } from "@/components/layout/header";
import { processApi, MONTHS, ACQUIRER_COLORS } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { ArrowLeft, Loader2, Calendar, Check } from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/utils";

const ACQUIRERS = ["OXXOPay", "Bitso", "Kushki", "STP"];
const YEARS = [2024, 2025, 2026];

export default function NewProcessPage() {
  const router = useRouter();
  const now = new Date();

  const [name, setName] = useState(
    `Cierre ${MONTHS[now.getMonth()]} ${now.getFullYear()}`
  );
  const [periodYear, setPeriodYear] = useState(now.getFullYear());
  const [periodMonth, setPeriodMonth] = useState(now.getMonth() + 1);
  const [acquirers, setAcquirers] = useState<string[]>([...ACQUIRERS]);
  const [error, setError] = useState("");

  const mutation = useMutation({
    mutationFn: () =>
      processApi.create({
        name,
        period_year: periodYear,
        period_month: periodMonth,
        acquirers,
      }),
    onSuccess: (data) => {
      router.push(`/processes/${data.id}`);
    },
    onError: (err: Error) => {
      setError(err.message);
    },
  });

  function toggleAcquirer(acq: string) {
    setAcquirers((prev) =>
      prev.includes(acq) ? prev.filter((a) => a !== acq) : [...prev, acq]
    );
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!name.trim()) {
      setError("El nombre es requerido");
      return;
    }
    if (acquirers.length === 0) {
      setError("Selecciona al menos un adquirente");
      return;
    }
    mutation.mutate();
  }

  return (
    <>
      <Header title="Nueva Corrida" subtitle="Configura un nuevo proceso de reconciliación" />

      <div className="p-6 max-w-2xl">
        <Button variant="ghost" size="sm" className="mb-6 text-gray-500" asChild>
          <Link href="/processes">
            <ArrowLeft className="mr-2 h-4 w-4" /> Volver a corridas
          </Link>
        </Button>

        <form onSubmit={handleSubmit}>
          <Card>
            <CardHeader>
              <CardTitle>Configuración del Proceso</CardTitle>
              <CardDescription>
                Define el período y los adquirentes a reconciliar
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Name */}
              <div className="space-y-1.5">
                <Label htmlFor="name" className="text-sm font-medium text-gray-700">
                  Nombre
                </Label>
                <Input
                  id="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Ej: Cierre Enero 2026"
                  className="h-10"
                />
              </div>

              {/* Period */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label className="text-sm font-medium text-gray-700">Año</Label>
                  <select
                    value={periodYear}
                    onChange={(e) => setPeriodYear(Number(e.target.value))}
                    className="flex h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500"
                  >
                    {YEARS.map((y) => (
                      <option key={y} value={y}>{y}</option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-sm font-medium text-gray-700">Mes</Label>
                  <select
                    value={periodMonth}
                    onChange={(e) => setPeriodMonth(Number(e.target.value))}
                    className="flex h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500"
                  >
                    {MONTHS.map((m, i) => (
                      <option key={i} value={i + 1}>{m}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Period info */}
              <div className="flex items-center gap-2 text-xs text-gray-500 bg-gray-50 rounded-lg p-3">
                <Calendar className="h-4 w-4 shrink-0" />
                <span>
                  Ventana: 1 {MONTHS[periodMonth - 1]} {periodYear} 00:00 UTC-6 →{" "}
                  {new Date(periodYear, periodMonth, 0).getDate()} {MONTHS[periodMonth - 1]}{" "}
                  {periodYear} 23:59 UTC-6
                </span>
              </div>

              {/* Acquirers */}
              <div className="space-y-3">
                <Label className="text-sm font-medium text-gray-700">Adquirentes</Label>
                <div className="grid grid-cols-2 gap-3">
                  {ACQUIRERS.map((acq) => {
                    const selected = acquirers.includes(acq);
                    const color = ACQUIRER_COLORS[acq] ?? "#737373";
                    return (
                      <button
                        key={acq}
                        type="button"
                        onClick={() => toggleAcquirer(acq)}
                        className={cn(
                          "flex items-center gap-3 p-3 rounded-lg border-2 transition-all text-left",
                          selected
                            ? "border-current bg-opacity-5"
                            : "border-gray-200 hover:border-gray-300"
                        )}
                        style={selected ? { borderColor: color, backgroundColor: `${color}10` } : {}}
                      >
                        <div
                          className={cn(
                            "w-5 h-5 rounded flex items-center justify-center border-2 shrink-0",
                            selected ? "border-current" : "border-gray-300"
                          )}
                          style={selected ? { borderColor: color, backgroundColor: color } : {}}
                        >
                          {selected && <Check className="h-3 w-3 text-white" />}
                        </div>
                        <span
                          className="text-sm font-medium"
                          style={{ color: selected ? color : "#404040" }}
                        >
                          {acq}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Error */}
              {error && (
                <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                  {error}
                </p>
              )}

              {/* Submit */}
              <Button
                type="submit"
                disabled={mutation.isPending}
                className="w-full h-10 bg-brand-500 hover:bg-brand-600 text-white font-medium"
              >
                {mutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  "Crear Corrida"
                )}
              </Button>
            </CardContent>
          </Card>
        </form>
      </div>
    </>
  );
}
