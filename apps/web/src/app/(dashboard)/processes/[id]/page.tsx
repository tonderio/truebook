"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { Header } from "@/components/layout/header";
import {
  processApi,
  filesApi,
  STAGES,
  STAGE_LABELS,
  ACQUIRER_COLORS,
  type UploadedFile,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import Link from "next/link";
import { format } from "date-fns";
import { es } from "date-fns/locale";
import { cn } from "@/lib/utils";
import {
  ArrowLeft,
  Play,
  Upload,
  File,
  Trash2,
  CheckCircle2,
  Circle,
  Loader2,
  AlertCircle,
  Clock,
  BarChart3,
  X,
} from "lucide-react";

export default function ProcessDetailPage() {
  const { id } = useParams<{ id: string }>();
  const processId = Number(id);
  const qc = useQueryClient();
  const router = useRouter();
  const logsEndRef = useRef<HTMLDivElement>(null);

  const { data: process, isLoading } = useQuery({
    queryKey: ["process", processId],
    queryFn: () => processApi.get(processId),
    refetchInterval: (query) =>
      query.state.data?.status === "running" ? 2000 : false,
  });

  const { data: progress } = useQuery({
    queryKey: ["progress", processId],
    queryFn: () => processApi.progress(processId),
    refetchInterval: (query) =>
      query.state.data?.status === "running" ? 2000 : 10000,
  });

  const { data: files } = useQuery({
    queryKey: ["files", processId],
    queryFn: () => filesApi.list(processId),
  });

  const { data: config } = useQuery({
    queryKey: ["process-config"],
    queryFn: () => processApi.config(),
    staleTime: Infinity,
  });

  const runMutation = useMutation({
    mutationFn: () => processApi.run(processId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["process", processId] });
      qc.invalidateQueries({ queryKey: ["progress", processId] });
    },
  });

  const uploadMutation = useMutation({
    mutationFn: ({ fileType, file }: { fileType: string; file: File }) =>
      filesApi.upload(processId, fileType, file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["files", processId] });
    },
  });

  const deleteFileMutation = useMutation({
    mutationFn: (fileId: number) => filesApi.delete(fileId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["files", processId] });
    },
  });

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [progress?.logs?.length]);

  const handleFileDrop = useCallback(
    (fileType: string) => (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      const file = e.dataTransfer.files[0];
      if (file) uploadMutation.mutate({ fileType, file });
    },
    [uploadMutation]
  );

  const handleFileSelect = useCallback(
    (fileType: string) => (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) uploadMutation.mutate({ fileType, file });
      e.target.value = "";
    },
    [uploadMutation]
  );

  if (isLoading) {
    return (
      <>
        <Header title="Cargando..." />
        <div className="p-6 space-y-4">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-64 w-full" />
        </div>
      </>
    );
  }

  if (!process) {
    return (
      <>
        <Header title="Error" />
        <div className="p-6 text-center text-gray-500">
          Proceso no encontrado.
        </div>
      </>
    );
  }

  const isRunning = process.status === "running";
  const isCompleted = process.status === "completed";
  const isFailed = process.status === "failed";
  const currentStageIdx = STAGES.indexOf(
    (progress?.current_stage ?? process.current_stage ?? "") as (typeof STAGES)[number]
  );
  const logs = progress?.logs ?? [];
  const kushkiFiles = (files ?? []).filter((f) => f.file_type === "kushki");
  const banregioFiles = (files ?? []).filter((f) => f.file_type === "banregio");

  return (
    <>
      <Header
        title={process.name}
        subtitle={`${process.period_year}-${String(process.period_month).padStart(2, "0")} · ${(process.acquirers ?? []).join(", ")}`}
      />

      <div className="p-6">
        <div className="flex items-center gap-3 mb-6">
          <Button variant="ghost" size="sm" className="text-gray-500" asChild>
            <Link href="/processes">
              <ArrowLeft className="mr-1 h-4 w-4" /> Corridas
            </Link>
          </Button>
          <div className="flex-1" />
          {isCompleted && (
            <Button className="bg-brand-500 hover:bg-brand-600" asChild>
              <Link href={`/processes/${processId}/results`}>
                <BarChart3 className="mr-2 h-4 w-4" /> Ver Resultados
              </Link>
            </Button>
          )}
          {!isRunning && !isCompleted && (
            <Button
              className="bg-brand-500 hover:bg-brand-600"
              onClick={() => runMutation.mutate()}
              disabled={runMutation.isPending}
            >
              {runMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Play className="mr-2 h-4 w-4" />
              )}
              Ejecutar
            </Button>
          )}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left column: files + logs */}
          <div className="lg:col-span-2 space-y-6">
            {/* File Upload */}
            {!isRunning && !isCompleted && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Archivos</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {/* Kushki upload (unless SFTP enabled) */}
                  {!config?.kushki_sftp_enabled && (
                    <FileUploadZone
                      label="Kushki"
                      files={kushkiFiles}
                      fileType="kushki"
                      uploading={uploadMutation.isPending}
                      onDrop={handleFileDrop("kushki")}
                      onSelect={handleFileSelect("kushki")}
                      onDelete={(id) => deleteFileMutation.mutate(id)}
                    />
                  )}
                  {config?.kushki_sftp_enabled && (
                    <div className="p-3 rounded-lg bg-blue-50 border border-blue-200 text-sm text-blue-700">
                      Kushki SFTP habilitado — los archivos se descargan automáticamente.
                    </div>
                  )}
                  {/* Banregio upload */}
                  <FileUploadZone
                    label="Banregio"
                    files={banregioFiles}
                    fileType="banregio"
                    uploading={uploadMutation.isPending}
                    onDrop={handleFileDrop("banregio")}
                    onSelect={handleFileSelect("banregio")}
                    onDelete={(id) => deleteFileMutation.mutate(id)}
                  />
                </CardContent>
              </Card>
            )}

            {/* Execution Logs */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Logs de Ejecución</CardTitle>
              </CardHeader>
              <CardContent>
                {logs.length === 0 ? (
                  <p className="text-sm text-gray-400 text-center py-6">
                    {isRunning ? "Esperando logs..." : "Ejecuta el proceso para ver los logs"}
                  </p>
                ) : (
                  <ScrollArea className="h-72">
                    <div className="space-y-1 font-mono text-xs">
                      {logs.map((log) => (
                        <div
                          key={log.id}
                          className={cn(
                            "px-2 py-1 rounded",
                            log.level === "error" && "bg-red-50 text-red-700",
                            log.level === "warning" && "bg-amber-50 text-amber-700",
                            log.level === "info" && "text-gray-600"
                          )}
                        >
                          <span className="text-gray-400">
                            [{format(new Date(log.created_at), "HH:mm:ss")}]
                          </span>{" "}
                          <span className="text-gray-500">[{log.stage}]</span>{" "}
                          {log.message}
                        </div>
                      ))}
                      <div ref={logsEndRef} />
                    </div>
                  </ScrollArea>
                )}
              </CardContent>
            </Card>

            {/* Error message */}
            {isFailed && process.error_message && (
              <div className="p-4 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700">
                <p className="font-semibold mb-1">Error</p>
                <p>{process.error_message}</p>
              </div>
            )}
          </div>

          {/* Right column: stage timeline + info */}
          <div className="space-y-6">
            {/* Progress */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Progreso</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-3 mb-4">
                  <div className="text-3xl font-bold text-gray-900 tracking-tight">
                    {process.progress}%
                  </div>
                  {isRunning && (
                    <Badge className="bg-blue-100 text-blue-700 border-0">
                      <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                      En proceso
                    </Badge>
                  )}
                  {isCompleted && (
                    <Badge className="bg-green-100 text-green-700 border-0">
                      <CheckCircle2 className="mr-1 h-3 w-3" />
                      Completado
                    </Badge>
                  )}
                  {isFailed && (
                    <Badge className="bg-red-100 text-red-700 border-0">
                      <AlertCircle className="mr-1 h-3 w-3" />
                      Fallido
                    </Badge>
                  )}
                </div>
                <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden mb-6">
                  <div
                    className={cn(
                      "h-full rounded-full transition-all duration-500",
                      isFailed ? "bg-red-500" : isCompleted ? "bg-green-500" : "bg-brand-500"
                    )}
                    style={{ width: `${process.progress}%` }}
                  />
                </div>

                {/* Stage timeline */}
                <div className="space-y-0">
                  {STAGES.map((stage, idx) => {
                    const isDone = idx < currentStageIdx || isCompleted;
                    const isCurrent = idx === currentStageIdx && isRunning;
                    const isFutureOrFailed = !isDone && !isCurrent;

                    return (
                      <div key={stage} className="flex gap-3">
                        {/* Vertical line + icon */}
                        <div className="flex flex-col items-center">
                          {isDone ? (
                            <CheckCircle2 className="h-5 w-5 text-green-500 shrink-0" />
                          ) : isCurrent ? (
                            <Loader2 className="h-5 w-5 text-brand-500 animate-spin shrink-0" />
                          ) : (
                            <Circle className="h-5 w-5 text-gray-300 shrink-0" />
                          )}
                          {idx < STAGES.length - 1 && (
                            <div
                              className={cn(
                                "w-px flex-1 min-h-6",
                                isDone ? "bg-green-300" : "bg-gray-200"
                              )}
                            />
                          )}
                        </div>
                        <div className="pb-4">
                          <p
                            className={cn(
                              "text-sm font-medium",
                              isDone ? "text-green-700" : isCurrent ? "text-brand-600" : "text-gray-400"
                            )}
                          >
                            {STAGE_LABELS[stage] ?? stage}
                          </p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>

            {/* Process info */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Información</CardTitle>
              </CardHeader>
              <CardContent className="text-sm space-y-3">
                <div className="flex justify-between">
                  <span className="text-gray-500">ID</span>
                  <span className="font-mono text-gray-900">#{process.id}</span>
                </div>
                <Separator />
                <div className="flex justify-between">
                  <span className="text-gray-500">Período</span>
                  <span className="text-gray-900">
                    {process.period_year}-{String(process.period_month).padStart(2, "0")}
                  </span>
                </div>
                <Separator />
                <div className="flex justify-between">
                  <span className="text-gray-500">Adquirentes</span>
                  <div className="flex gap-1">
                    {(process.acquirers ?? []).map((a) => (
                      <Badge
                        key={a}
                        variant="outline"
                        className="text-[10px] px-1.5 py-0"
                        style={{ borderColor: ACQUIRER_COLORS[a], color: ACQUIRER_COLORS[a] }}
                      >
                        {a}
                      </Badge>
                    ))}
                  </div>
                </div>
                <Separator />
                <div className="flex justify-between">
                  <span className="text-gray-500">Creado</span>
                  <span className="text-gray-900">
                    {format(new Date(process.created_at), "dd MMM yyyy, HH:mm", { locale: es })}
                  </span>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </>
  );
}

// ── File Upload Zone Component ──

function FileUploadZone({
  label,
  files,
  fileType,
  uploading,
  onDrop,
  onSelect,
  onDelete,
}: {
  label: string;
  files: UploadedFile[];
  fileType: string;
  uploading: boolean;
  onDrop: (e: React.DragEvent<HTMLDivElement>) => void;
  onSelect: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onDelete: (id: number) => void;
}) {
  const inputId = `file-${fileType}`;
  return (
    <div>
      <p className="text-sm font-medium text-gray-700 mb-2">{label}</p>
      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={onDrop}
        className="border-2 border-dashed border-gray-200 rounded-lg p-6 text-center hover:border-brand-300 hover:bg-brand-50/30 transition-colors cursor-pointer"
        onClick={() => document.getElementById(inputId)?.click()}
      >
        <Upload className="h-6 w-6 text-gray-400 mx-auto mb-2" />
        <p className="text-sm text-gray-500">
          {uploading ? (
            <span className="flex items-center justify-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" /> Subiendo...
            </span>
          ) : (
            <>
              Arrastra un archivo aquí o{" "}
              <span className="text-brand-500 font-medium">selecciona</span>
            </>
          )}
        </p>
        <p className="text-xs text-gray-400 mt-1">.csv, .xlsx, .xls, .pdf</p>
        <input
          id={inputId}
          type="file"
          accept=".csv,.xlsx,.xls,.pdf"
          onChange={onSelect}
          className="hidden"
        />
      </div>

      {/* Uploaded files list */}
      {files.length > 0 && (
        <div className="mt-3 space-y-2">
          {files.map((f) => (
            <div
              key={f.id}
              className="flex items-center gap-3 p-2 rounded-lg bg-gray-50 text-sm"
            >
              <File className="h-4 w-4 text-gray-400 shrink-0" />
              <span className="flex-1 text-gray-700 truncate">{f.original_name}</span>
              <span className="text-xs text-gray-400">
                {(f.file_size / 1024).toFixed(0)} KB
              </span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(f.id);
                }}
                className="p-1 hover:bg-red-100 rounded text-gray-400 hover:text-red-600 transition-colors"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
