"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { SiteHeader } from "@/components/site-header";
import { Alert, Button, Card, Field, Input } from "@/components/ui";
import { formatDateTime, questionTypeLabel } from "@/lib/utils";

type Question = {
  id: string;
  order: number;
  type: string;
  prompt: string | null;
  correctAnswer: string;
  points: number;
};

type Session = {
  id: string;
  code: string;
  label: string | null;
  isActive: boolean;
  opensAt: string | null;
  closesAt: string | null;
  _count: { submissions: number };
};

type ExamDetail = {
  id: string;
  title: string;
  course: string | null;
  description: string | null;
  maxScore: number;
  showDetailToStudent: boolean;
  questions: Question[];
  sessions: Session[];
};

export default function ExamDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [exam, setExam] = useState<ExamDetail | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [sessionLabel, setSessionLabel] = useState("");
  const [creatingSession, setCreatingSession] = useState(false);
  const [copiedCode, setCopiedCode] = useState("");

  async function loadExam() {
    const response = await fetch(`/api/exams/${params.id}`);
    if (response.status === 401) {
      router.push("/docente");
      return;
    }
    if (!response.ok) {
      setError("No se pudo cargar el examen.");
      setLoading(false);
      return;
    }
    const data = (await response.json()) as { exam: ExamDetail };
    setExam(data.exam);
    setLoading(false);
  }

  useEffect(() => {
    loadExam();
  }, [params.id]);

  async function createSession() {
    if (!exam) return;
    setCreatingSession(true);
    setError("");

    const response = await fetch("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        examId: exam.id,
        label: sessionLabel,
      }),
    });

    const data = (await response.json()) as { error?: string };

    setCreatingSession(false);

    if (!response.ok) {
      setError(data.error ?? "No se pudo crear la sesión.");
      return;
    }

    setSessionLabel("");
    await loadExam();
  }

  async function copyLink(code: string) {
    const url = `${window.location.origin}/r/${code}`;
    await navigator.clipboard.writeText(url);
    setCopiedCode(code);
    setTimeout(() => setCopiedCode(""), 2000);
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50">
        <SiteHeader />
        <main className="mx-auto max-w-6xl px-4 py-12">Cargando...</main>
      </div>
    );
  }

  if (!exam) {
    return (
      <div className="min-h-screen bg-slate-50">
        <SiteHeader />
        <main className="mx-auto max-w-6xl px-4 py-12">
          <Alert>{error || "Examen no encontrado."}</Alert>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <SiteHeader />
      <main className="mx-auto max-w-6xl space-y-6 px-4 py-10">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <Link
              href="/docente/panel"
              className="text-sm text-teal-700 hover:underline"
            >
              ← Volver al panel
            </Link>
            <h1 className="mt-2 text-3xl font-bold text-slate-900">{exam.title}</h1>
            {exam.course ? (
              <p className="text-slate-600">{exam.course}</p>
            ) : null}
            <p className="mt-2 text-sm text-slate-500">
              {exam.questions.length} preguntas · Nota máxima {exam.maxScore}
            </p>
            {exam.description ? (
              <p className="mt-3 rounded-xl bg-white p-4 text-sm text-slate-600 shadow-sm">
                {exam.description}
              </p>
            ) : null}
          </div>
        </div>

        <Card title="Nueva sesión de aula">
          <p className="mb-4 text-sm text-slate-600">
            Generá un link para que los alumnos carguen sus respuestas después
            de rendir el examen en papel. Proyectá el QR o el link en el aula.
          </p>
          <div className="flex flex-wrap gap-3">
            <Field label="Etiqueta (opcional)">
              <Input
                value={sessionLabel}
                onChange={(event) => setSessionLabel(event.target.value)}
                placeholder="Comisión A - 05/07/2026"
              />
            </Field>
            <div className="flex items-end">
              <Button onClick={createSession} disabled={creatingSession}>
                {creatingSession ? "Creando..." : "Generar link de sesión"}
              </Button>
            </div>
          </div>
        </Card>

        <Card title="Sesiones activas">
          {exam.sessions.length === 0 ? (
            <p className="text-sm text-slate-600">
              Todavía no hay sesiones. Creá una para obtener el link del examen.
            </p>
          ) : (
            <div className="space-y-4">
              {exam.sessions.map((session) => (
                <div
                  key={session.id}
                  className="rounded-xl border border-slate-200 p-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <p className="font-semibold text-slate-900">
                        {session.label || "Sesión sin etiqueta"}
                      </p>
                      <p className="text-sm text-slate-600">
                        Código:{" "}
                        <span className="font-mono text-base">{session.code}</span>
                      </p>
                      <p className="text-sm text-slate-500">
                        {session._count.submissions} envíos ·{" "}
                        {session.isActive ? "Abierta" : "Cerrada"}
                      </p>
                      <p className="text-xs text-slate-400">
                        Apertura: {formatDateTime(session.opensAt)} · Cierre:{" "}
                        {formatDateTime(session.closesAt)}
                      </p>
                      <p className="mt-2 font-mono text-sm text-teal-700">
                        /r/{session.code}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        variant="secondary"
                        onClick={() => copyLink(session.code)}
                      >
                        {copiedCode === session.code ? "Copiado" : "Copiar link"}
                      </Button>
                      <Link href={`/r/${session.code}`} target="_blank">
                        <Button variant="secondary">Vista alumno</Button>
                      </Link>
                      <Link href={`/docente/panel/sesiones/${session.id}`}>
                        <Button>Ver resultados</Button>
                      </Link>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Clave de respuestas cargada">
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-slate-200 text-slate-500">
                <tr>
                  <th className="px-3 py-2">#</th>
                  <th className="px-3 py-2">Tipo</th>
                  <th className="px-3 py-2">Referencia</th>
                  <th className="px-3 py-2">Correcta</th>
                  <th className="px-3 py-2">Pts</th>
                </tr>
              </thead>
              <tbody>
                {exam.questions.map((question) => (
                  <tr key={question.id} className="border-b border-slate-100">
                    <td className="px-3 py-2 font-medium">{question.order}</td>
                    <td className="px-3 py-2">{questionTypeLabel(question.type)}</td>
                    <td className="px-3 py-2 text-slate-600">
                      {question.prompt || "—"}
                    </td>
                    <td className="px-3 py-2 font-mono">{question.correctAnswer}</td>
                    <td className="px-3 py-2">{question.points}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        {error ? <Alert>{error}</Alert> : null}
      </main>
    </div>
  );
}
