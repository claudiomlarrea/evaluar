"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { SiteHeader } from "@/components/site-header";
import { Alert, Button, Card, Field, Input } from "@/components/ui";

export default function TeacherAuthPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setLoading(true);

    const endpoint = mode === "login" ? "/api/auth/login" : "/api/auth/register";

    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, pin }),
    });

    const data = (await response.json()) as { error?: string };

    setLoading(false);

    if (!response.ok) {
      setError(data.error ?? "Ocurrió un error.");
      return;
    }

    router.push("/docente/panel");
    router.refresh();
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <SiteHeader />
      <main className="mx-auto flex max-w-lg flex-col gap-6 px-4 py-12">
        <Card title={mode === "login" ? "Acceso docente" : "Registro docente"}>
          <form className="space-y-4" onSubmit={handleSubmit}>
            <Field label="Nombre completo">
              <Input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Ej. Dra. María López"
                required
              />
            </Field>
            <Field label="PIN de acceso" hint="Mínimo 4 caracteres. Guardalo en un lugar seguro.">
              <Input
                type="password"
                value={pin}
                onChange={(event) => setPin(event.target.value)}
                placeholder="••••"
                minLength={4}
                required
              />
            </Field>

            {error ? <Alert>{error}</Alert> : null}

            <Button type="submit" disabled={loading} className="w-full">
              {loading
                ? "Procesando..."
                : mode === "login"
                  ? "Ingresar"
                  : "Crear cuenta"}
            </Button>
          </form>

          <button
            type="button"
            className="mt-4 text-sm text-teal-700 hover:underline"
            onClick={() => {
              setMode(mode === "login" ? "register" : "login");
              setError("");
            }}
          >
            {mode === "login"
              ? "¿Primera vez? Crear cuenta docente"
              : "¿Ya tenés cuenta? Iniciar sesión"}
          </button>
        </Card>
      </main>
    </div>
  );
}
