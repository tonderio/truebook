"use client";

import { useState } from "react";
import { signIn } from "next-auth/react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  BarChart3,
  FileCheck,
  Shield,
  Sparkles,
  BookOpen,
  Loader2,
} from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    const result = await signIn("credentials", {
      email,
      password,
      redirect: false,
    });

    setLoading(false);

    if (result?.error) {
      setError("Credenciales incorrectas. Intenta de nuevo.");
    } else {
      router.push("/");
      router.refresh();
    }
  }

  return (
    <>
      {/* Left panel — branding */}
      <div className="hidden lg:flex lg:flex-1 bg-brand-500 relative overflow-hidden">
        <div className="relative z-10 flex flex-col justify-between p-12 text-white">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <BookOpen className="h-8 w-8" />
              <span className="text-2xl font-bold tracking-tight">TrueBook</span>
            </div>
            <p className="text-brand-100 text-sm">by Tonder</p>
          </div>

          <div className="space-y-8">
            <h1 className="text-4xl font-bold leading-tight tracking-tight">
              Cierre contable
              <br />
              automatizado.
            </h1>
            <p className="text-brand-100 text-lg max-w-md">
              Reconcilia pagos, valida comisiones y genera reportes en minutos,
              no en días.
            </p>

            <div className="grid grid-cols-2 gap-4 max-w-md">
              {[
                { icon: BarChart3, label: "Reconciliación 3-vías" },
                { icon: FileCheck, label: "Exportar a Excel" },
                { icon: Shield, label: "Auditoría completa" },
                { icon: Sparkles, label: "AI Insights" },
              ].map(({ icon: Icon, label }) => (
                <div
                  key={label}
                  className="flex items-center gap-3 bg-white/10 rounded-xl px-4 py-3"
                >
                  <Icon className="h-5 w-5 shrink-0" />
                  <span className="text-sm font-medium">{label}</span>
                </div>
              ))}
            </div>
          </div>

          <p className="text-brand-200 text-xs">
            &copy; {new Date().getFullYear()} Tonder. Todos los derechos reservados.
          </p>
        </div>

        {/* Decorative circles */}
        <div className="absolute -top-32 -right-32 w-96 h-96 bg-white/5 rounded-full" />
        <div className="absolute -bottom-48 -left-24 w-[500px] h-[500px] bg-white/5 rounded-full" />
      </div>

      {/* Right panel — login form */}
      <div className="flex flex-1 flex-col justify-center px-6 lg:px-16 xl:px-24 bg-white">
        <div className="mx-auto w-full max-w-sm">
          {/* Mobile logo */}
          <div className="lg:hidden flex items-center gap-2 mb-10">
            <BookOpen className="h-6 w-6 text-brand-500" />
            <span className="text-xl font-bold text-gray-900 tracking-tight">
              TrueBook
            </span>
          </div>

          <h2 className="text-2xl font-bold text-gray-900 tracking-tight">
            Iniciar sesión
          </h2>
          <p className="mt-2 text-sm text-gray-500">
            Ingresa tus credenciales para acceder a la plataforma
          </p>

          <form onSubmit={handleSubmit} className="mt-8 space-y-5">
            <div className="space-y-1.5">
              <Label htmlFor="email" className="text-gray-700 text-sm font-medium">
                Correo electrónico
              </Label>
              <Input
                id="email"
                type="email"
                placeholder="tu@correo.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="h-10"
                autoComplete="email"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="password" className="text-gray-700 text-sm font-medium">
                Contraseña
              </Label>
              <Input
                id="password"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="h-10"
                autoComplete="current-password"
              />
            </div>

            {error && (
              <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                {error}
              </p>
            )}

            <Button
              type="submit"
              disabled={loading}
              className="w-full h-10 bg-brand-500 hover:bg-brand-600 text-white font-medium"
            >
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                "Ingresar"
              )}
            </Button>
          </form>
        </div>
      </div>
    </>
  );
}
