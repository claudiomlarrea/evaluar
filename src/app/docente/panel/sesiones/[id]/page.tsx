"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { SiteHeader } from "@/components/site-header";
import { Alert, Button, Card } from "@/components/ui";
import { formatDateTime, formatScore } from "@/lib/utils";

type Submission = {
  id: string;
  studentName: string;
  studentDni: string;
  score: number;
  correctCount: number;
  wrongCount: number;
  unansweredCount: number;
  wrongQuestions: number[];
  submittedAt: string;
};

type QuestionStat = {
  order: number;
  type: string;
  correct: number;
  incorrect: number;
  unanswered: number;
  successRate: number;
};

type ResultsPayload = {
  session: {
    id: string;
    code: string;
    label: string | null;
    isActive: boolean;
  };
  exam: {
    title: string;
    course: string | null;
    maxScore: number;
    questionCount: number;
  };
  submissions: Submission[];
  questionStats: QuestionStat[];
};

export default function SessionResultsPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [data, setData] = useState<ResultsPayload | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      const response = await fetch(`/api/sessions/${params.id}/results`);
      if (response.status === 401) {
        router.push("/docente");
        return;
      }
      if (!response.ok) {
        setError("No se pudieron cargar los resultados.");
        setLoading(false);
        return;
      }
      const payload = (await response.json()) as ResultsPayload;
      setData(payload);
      setLoading(false);
    }

    load();
  }, [params.id, router]);

  function exportCsv() {
    if (!data) return;

    const headers = [
      "Nombre",
      "DNI",
      "Nota",
      "Aciertos",
      "Errores",
      "Sin responder",
      "Preguntas falladas",
      "Fecha envío",
    ];

    const rows = data.submissions.map((submission) => [
      submission.studentName,
      submission.studentDni,
      formatScore(submission.score),
      submission.correctCount,
      submission.wrongCount,
      submission.unansweredCount,
      submission.wrongQuestions.join("; "),
      formatDateTime(submission.submittedAt),
    ]);

    const csv = [headers, ...rows]
      .map((row) =>
        row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(","),
      )
      .join("\n");

    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `evaluar-${data.session.code}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50">
        <SiteHeader />
        <main className="mx-auto max-w-6xl px-4 py-12">Cargando resultados...</main>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="min-h-screen bg-slate-50">
        <SiteHeader />
        <main className="mx-auto max-w-6xl px-4 py-12">
          <Alert>{error || "Sesión no encontrada."}</Alert>
        </main>
      </div>
    );
  }

  const average =
    data.submissions.length === 0
      ? 0
      : data.submissions.reduce((sum, item) => sum + item.score, 0) /
        data.submissions.length;

  return (
    <div className="min-h-screen bg-slate-50">
      <SiteHeader />
      <main className="mx-auto max-w-6xl space-y-6 px-4 py-10">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm text-teal-700">
              Sesión {data.session.code}
              {data.session.label ? ` · ${data.session.label}` : ""}
            </p>
            <h1 className="text-3xl font-bold text-slate-900">{data.exam.title}</h1>
            {data.exam.course ? (
              <p className="text-slate-600">{data.exam.course}</p>
            ) : null}
            <p className="mt-2 text-sm text-slate-500">
              {data.submissions.length} envíos · Promedio{" "}
              {formatScore(average)} / {data.exam.maxScore}
            </p>
          </div>
          <div className="flex gap-3">
            <Button variant="secondary" onClick={exportCsv}>
              Exportar CSV
            </Button>
            <Link href={`/r/${data.session.code}`} target="_blank">
              <Button variant="secondary">Link alumno</Button>
            </Link>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <Card>
            <p className="text-sm text-slate-500">Alumnos evaluados</p>
            <p className="text-3xl font-bold text-slate-900">
              {data.submissions.length}
            </p>
          </Card>
          <Card>
            <p className="text-sm text-slate-500">Promedio</p>
            <p className="text-3xl font-bold text-slate-900">
              {formatScore(average)}
            </p>
          </Card>
          <Card>
            <p className="text-sm text-slate-500">Estado</p>
            <p className="text-3xl font-bold text-slate-900">
              {data.session.isActive ? "Abierta" : "Cerrada"}
            </p>
          </Card>
        </div>

        <Card title="Resultados por alumno">
          {data.submissions.length === 0 ? (
            <p className="text-sm text-slate-600">
              Todavía no hay respuestas enviadas.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="border-b border-slate-200 text-slate-500">
                  <tr>
                    <th className="px-3 py-2">Alumno</th>
                    <th className="px-3 py-2">DNI</th>
                    <th className="px-3 py-2">Nota</th>
                    <th className="px-3 py-2">Aciertos</th>
                    <th className="px-3 py-2">Errores</th>
                    <th className="px-3 py-2">Preguntas falladas</th>
                    <th className="px-3 py-2">Enviado</th>
                  </tr>
                </thead>
                <tbody>
                  {data.submissions.map((submission) => (
                    <tr
                      key={submission.id}
                      className="border-b border-slate-100 align-top"
                    >
                      <td className="px-3 py-2 font-medium">
                        {submission.studentName}
                      </td>
                      <td className="px-3 py-2 font-mono">{submission.studentDni}</td>
                      <td className="px-3 py-2 font-semibold text-teal-700">
                        {formatScore(submission.score)}
                      </td>
                      <td className="px-3 py-2">{submission.correctCount}</td>
                      <td className="px-3 py-2">{submission.wrongCount}</td>
                      <td className="px-3 py-2 text-slate-600">
                        {submission.wrongQuestions.length > 0
                          ? submission.wrongQuestions.join(", ")
                          : "—"}
                      </td>
                      <td className="px-3 py-2 text-slate-500">
                        {formatDateTime(submission.submittedAt)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card title="Estadísticas por pregunta">
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-slate-200 text-slate-500">
                <tr>
                  <th className="px-3 py-2">#</th>
                  <th className="px-3 py-2">Aciertos</th>
                  <th className="px-3 py-2">Errores</th>
                  <th className="px-3 py-2">Sin responder</th>
                  <th className="px-3 py-2">% acierto</th>
                </tr>
              </thead>
              <tbody>
                {data.questionStats.map((stat) => (
                  <tr key={stat.order} className="border-b border-slate-100">
                    <td className="px-3 py-2 font-medium">{stat.order}</td>
                    <td className="px-3 py-2">{stat.correct}</td>
                    <td className="px-3 py-2">{stat.incorrect}</td>
                    <td className="px-3 py-2">{stat.unanswered}</td>
                    <td className="px-3 py-2">
                      <span
                        className={
                          stat.successRate < 50
                            ? "font-semibold text-red-600"
                            : "text-slate-700"
                        }
                      >
                        {stat.successRate}%
                      </span>
                    </td>
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
