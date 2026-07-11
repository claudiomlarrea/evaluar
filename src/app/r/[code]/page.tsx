"use client";

import { useParams } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { Alert, Button, Card, Field, Input, Select } from "@/components/ui";
import type { MatchingPair, QuestionType, StudentAnswers } from "@/lib/types";
import { formatScore } from "@/lib/utils";

type PublicQuestion = {
  order: number;
  type: QuestionType;
  prompt: string | null;
  options: string[] | MatchingPair[];
  points: number;
};

type SessionPayload = {
  session: {
    code: string;
    label: string | null;
    isOpen: boolean;
  };
  exam: {
    title: string;
    course: string | null;
    description: string | null;
    maxScore: number;
    showDetailToStudent: boolean;
    questionCount: number;
  };
  questions: PublicQuestion[];
};

type SubmissionResult = {
  score: number;
  correctCount: number;
  wrongCount: number;
  unansweredCount: number;
  wrongQuestions: number[];
  totalQuestions: number;
  showDetail: boolean;
  maxScore: number;
};

export default function StudentExamPage() {
  const params = useParams<{ code: string }>();
  const [payload, setPayload] = useState<SessionPayload | null>(null);
  const [studentName, setStudentName] = useState("");
  const [studentDni, setStudentDni] = useState("");
  const [answers, setAnswers] = useState<StudentAnswers>({});
  const [step, setStep] = useState<"identify" | "answer" | "done">("identify");
  const [result, setResult] = useState<SubmissionResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [page, setPage] = useState(0);

  const pageSize = 10;

  useEffect(() => {
    async function load() {
      const response = await fetch(`/api/r/${params.code}`);
      const data = (await response.json()) as SessionPayload & { error?: string };

      if (!response.ok) {
        setError(data.error ?? "Sesión no encontrada.");
        setLoading(false);
        return;
      }

      setPayload(data);
      setLoading(false);
    }

    load();
  }, [params.code]);

  const totalPages = useMemo(() => {
    if (!payload) return 0;
    return Math.ceil(payload.questions.length / pageSize);
  }, [payload]);

  const visibleQuestions = useMemo(() => {
    if (!payload) return [];
    const start = page * pageSize;
    return payload.questions.slice(start, start + pageSize);
  }, [payload, page]);

  function setAnswer(order: number, value: string) {
    setAnswers((current) => ({
      ...current,
      [String(order)]: value,
    }));
  }

  function setMatchingAnswer(order: number, itemKey: string, value: string) {
    const currentRaw = answers[String(order)];
    let current: Record<string, string> = {};
    if (currentRaw) {
      try {
        current = JSON.parse(currentRaw) as Record<string, string>;
      } catch {
        current = {};
      }
    }
    const next = { ...current, [itemKey]: value };
    setAnswer(order, JSON.stringify(next));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!payload) return;

    const confirmed = window.confirm(
      "¿Confirmás el envío? No podrás modificar tus respuestas después.",
    );
    if (!confirmed) return;

    setSubmitting(true);
    setError("");

    const response = await fetch(`/api/r/${params.code}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        studentName,
        studentDni,
        answers,
      }),
    });

    const data = (await response.json()) as {
      error?: string;
      submission?: SubmissionResult;
    };

    setSubmitting(false);

    if (!response.ok || !data.submission) {
      setError(data.error ?? "No se pudieron enviar las respuestas.");
      return;
    }

    setResult(data.submission);
    setStep("done");
  }

  if (loading) {
    return (
      <main className="mx-auto flex min-h-screen max-w-3xl items-center justify-center px-4">
        <p className="text-slate-600">Cargando examen...</p>
      </main>
    );
  }

  if (!payload) {
    return (
      <main className="mx-auto flex min-h-screen max-w-3xl items-center px-4 py-12">
        <Alert>{error || "Sesión no disponible."}</Alert>
      </main>
    );
  }

  if (!payload.session.isOpen) {
    return (
      <main className="mx-auto max-w-3xl space-y-4 px-4 py-12">
        <Card title="Sesión cerrada">
          <p className="text-sm text-slate-600">
            Esta sesión no está abierta para envío de respuestas. Consultá con
            tu docente.
          </p>
        </Card>
      </main>
    );
  }

  if (step === "done" && result) {
    return (
      <main className="mx-auto max-w-3xl space-y-6 px-4 py-12">
        <div className="text-center">
          <p className="text-sm uppercase tracking-wide text-teal-700">
            EvaluAR
          </p>
          <h1 className="text-3xl font-bold text-slate-900">Respuestas enviadas</h1>
          <p className="text-slate-600">{payload.exam.title}</p>
        </div>

        <Card>
          <div className="text-center">
            <p className="text-sm text-slate-500">Tu nota</p>
            <p className="text-5xl font-bold text-teal-700">
              {formatScore(result.score)}
            </p>
            <p className="text-sm text-slate-500">
              sobre {result.maxScore}
            </p>
          </div>
          <div className="mt-6 grid grid-cols-3 gap-3 text-center text-sm">
            <div className="rounded-xl bg-emerald-50 p-3">
              <p className="font-semibold text-emerald-800">{result.correctCount}</p>
              <p className="text-emerald-700">Aciertos</p>
            </div>
            <div className="rounded-xl bg-red-50 p-3">
              <p className="font-semibold text-red-800">{result.wrongCount}</p>
              <p className="text-red-700">Errores</p>
            </div>
            <div className="rounded-xl bg-slate-100 p-3">
              <p className="font-semibold text-slate-800">
                {result.unansweredCount}
              </p>
              <p className="text-slate-600">Sin responder</p>
            </div>
          </div>

          {result.showDetail && result.wrongQuestions.length > 0 ? (
            <div className="mt-6 rounded-xl bg-amber-50 p-4 text-sm text-amber-900">
              <p className="font-medium">Preguntas incorrectas u omitidas:</p>
              <p>{result.wrongQuestions.join(", ")}</p>
            </div>
          ) : null}
        </Card>
      </main>
    );
  }

  return (
    <main className="mx-auto min-h-screen max-w-3xl space-y-6 px-4 py-8">
      <header className="space-y-2 text-center">
        <p className="text-sm uppercase tracking-wide text-teal-700">EvaluAR</p>
        <h1 className="text-2xl font-bold text-slate-900">{payload.exam.title}</h1>
        {payload.exam.course ? (
          <p className="text-slate-600">{payload.exam.course}</p>
        ) : null}
        {payload.session.label ? (
          <p className="text-sm text-slate-500">{payload.session.label}</p>
        ) : null}
        {payload.exam.description ? (
          <p className="rounded-xl bg-white p-4 text-left text-sm text-slate-600 shadow-sm">
            {payload.exam.description}
          </p>
        ) : null}
      </header>

      {step === "identify" ? (
        <Card title="Identificación">
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              if (!studentName.trim() || !studentDni.trim()) {
                setError("Completá nombre y DNI/matrícula.");
                return;
              }
              setError("");
              setStep("answer");
            }}
          >
            <Field label="Apellido y nombre">
              <Input
                value={studentName}
                onChange={(event) => setStudentName(event.target.value)}
                placeholder="Ej. García, Ana"
                required
              />
            </Field>
            <Field label="DNI o matrícula">
              <Input
                value={studentDni}
                onChange={(event) => setStudentDni(event.target.value)}
                placeholder="Ej. 45123456"
                required
              />
            </Field>
            {error ? <Alert>{error}</Alert> : null}
            <Button type="submit" className="w-full">
              Continuar a las respuestas
            </Button>
          </form>
        </Card>
      ) : null}

      {step === "answer" ? (
        <form className="space-y-6" onSubmit={handleSubmit}>
          <Card title={`Respuestas (${page + 1} de ${totalPages})`}>
            <p className="mb-4 text-sm text-slate-600">
              Marcá la opción que elegiste en tu cuadernillo de papel. Preguntas{" "}
              {visibleQuestions[0]?.order} a{" "}
              {visibleQuestions[visibleQuestions.length - 1]?.order} de{" "}
              {payload.exam.questionCount}.
            </p>

            <div className="space-y-5">
              {visibleQuestions.map((question) => (
                <div
                  key={question.order}
                  className="rounded-xl border border-slate-200 p-4"
                >
                  <p className="mb-3 font-semibold text-slate-900">
                    Pregunta {question.order}
                  </p>
                  {question.prompt ? (
                    <p className="mb-3 text-sm text-slate-500">{question.prompt}</p>
                  ) : null}

                  {question.type === "MULTIPLE_CHOICE" ? (
                    <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
                      {(question.options as string[]).map((option) => (
                        <label
                          key={option}
                          className={`cursor-pointer rounded-xl border px-4 py-3 text-center text-sm font-medium ${
                            answers[String(question.order)] === option
                              ? "border-teal-600 bg-teal-50 text-teal-800"
                              : "border-slate-200 bg-white text-slate-700"
                          }`}
                        >
                          <input
                            type="radio"
                            name={`q-${question.order}`}
                            value={option}
                            checked={answers[String(question.order)] === option}
                            onChange={() => setAnswer(question.order, option)}
                            className="sr-only"
                          />
                          {option}
                        </label>
                      ))}
                    </div>
                  ) : null}

                  {question.type === "TRUE_FALSE" ? (
                    <div className="grid grid-cols-2 gap-2">
                      {["V", "F"].map((option) => (
                        <label
                          key={option}
                          className={`cursor-pointer rounded-xl border px-4 py-3 text-center text-sm font-medium ${
                            answers[String(question.order)] === option
                              ? "border-teal-600 bg-teal-50 text-teal-800"
                              : "border-slate-200 bg-white text-slate-700"
                          }`}
                        >
                          <input
                            type="radio"
                            name={`q-${question.order}`}
                            value={option}
                            checked={answers[String(question.order)] === option}
                            onChange={() => setAnswer(question.order, option)}
                            className="sr-only"
                          />
                          {option === "V" ? "Verdadero" : "Falso"}
                        </label>
                      ))}
                    </div>
                  ) : null}

                  {question.type === "MATCHING" ? (
                    <div className="space-y-3">
                      {(question.options as MatchingPair[]).map((pair, index) => {
                        const key = String(index + 1);
                        const currentRaw = answers[String(question.order)];
                        let current: Record<string, string> = {};
                        if (currentRaw) {
                          try {
                            current = JSON.parse(currentRaw) as Record<string, string>;
                          } catch {
                            current = {};
                          }
                        }

                        return (
                          <div
                            key={key}
                            className="grid gap-2 sm:grid-cols-[1fr_auto]"
                          >
                            <p className="rounded-xl bg-slate-100 px-3 py-2 text-sm">
                              {index + 1}. {pair.left}
                            </p>
                            <Select
                              value={current[key] ?? ""}
                              onChange={(event) =>
                                setMatchingAnswer(
                                  question.order,
                                  key,
                                  event.target.value,
                                )
                              }
                              required
                            >
                              <option value="">Elegir</option>
                              {["A", "B", "C", "D", "E"].map((option) => (
                                <option key={option} value={option}>
                                  {option}
                                </option>
                              ))}
                            </Select>
                          </div>
                        );
                      })}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>

            <div className="mt-6 flex flex-wrap justify-between gap-3">
              <Button
                type="button"
                variant="secondary"
                disabled={page === 0}
                onClick={() => setPage((current) => current - 1)}
              >
                Anterior
              </Button>
              {page < totalPages - 1 ? (
                <Button type="button" onClick={() => setPage((current) => current + 1)}>
                  Siguiente
                </Button>
              ) : (
                <Button type="submit" disabled={submitting}>
                  {submitting ? "Enviando..." : "Enviar respuestas"}
                </Button>
              )}
            </div>
          </Card>

          {error ? <Alert>{error}</Alert> : null}
        </form>
      ) : null}
    </main>
  );
}
