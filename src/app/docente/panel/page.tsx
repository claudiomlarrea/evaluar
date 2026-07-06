"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { SiteHeader } from "@/components/site-header";
import { Alert, Button, Card } from "@/components/ui";
import { formatDateTime } from "@/lib/utils";

type ExamSummary = {
  id: string;
  title: string;
  course: string | null;
  maxScore: number;
  createdAt: string;
  _count: {
    questions: number;
    sessions: number;
  };
};

export default function TeacherPanelPage() {
  const router = useRouter();
  const [teacherName, setTeacherName] = useState<string | null>(null);
  const [exams, setExams] = useState<ExamSummary[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      const authResponse = await fetch("/api/auth/me");
      const authData = (await authResponse.json()) as {
        teacher: { name: string } | null;
      };

      if (!authData.teacher) {
        router.push("/docente");
        return;
      }

      setTeacherName(authData.teacher.name);

      const examsResponse = await fetch("/api/exams");
      if (!examsResponse.ok) {
        setError("No se pudieron cargar los exámenes.");
        setLoading(false);
        return;
      }

      const examsData = (await examsResponse.json()) as { exams: ExamSummary[] };
      setExams(examsData.exams);
      setLoading(false);
    }

    load();
  }, [router]);

  async function handleLogout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/docente");
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50">
        <SiteHeader />
        <main className="mx-auto max-w-6xl px-4 py-12 text-slate-600">
          Cargando panel...
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <SiteHeader />
      <main className="mx-auto max-w-6xl space-y-6 px-4 py-10">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-slate-900">Panel docente</h1>
            <p className="text-slate-600">Hola, {teacherName}</p>
          </div>
          <div className="flex gap-3">
            <Link href="/docente/panel/nuevo">
              <Button>Nuevo examen</Button>
            </Link>
            <Button variant="secondary" onClick={handleLogout}>
              Salir
            </Button>
          </div>
        </div>

        {error ? <Alert>{error}</Alert> : null}

        {exams.length === 0 ? (
          <Card title="Todavía no hay exámenes">
            <p className="text-sm text-slate-600">
              Creá tu primer examen, cargá la clave de respuestas y generá un
              link para que los alumnos envíen sus respuestas después del
              examen en papel.
            </p>
          </Card>
        ) : (
          <div className="grid gap-4">
            {exams.map((exam) => (
              <Card key={exam.id}>
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <h2 className="text-xl font-semibold text-slate-900">
                      {exam.title}
                    </h2>
                    {exam.course ? (
                      <p className="text-sm text-slate-500">{exam.course}</p>
                    ) : null}
                    <p className="mt-2 text-sm text-slate-600">
                      {exam._count.questions} preguntas · Nota máxima{" "}
                      {exam.maxScore} · {exam._count.sessions} sesiones
                    </p>
                    <p className="text-xs text-slate-400">
                      Creado {formatDateTime(exam.createdAt)}
                    </p>
                  </div>
                  <Link href={`/docente/panel/examenes/${exam.id}`}>
                    <Button variant="secondary">Administrar</Button>
                  </Link>
                </div>
              </Card>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
