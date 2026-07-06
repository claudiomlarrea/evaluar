"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { SiteHeader } from "@/components/site-header";
import { Alert, Button, Card, Field, Input, Select, TextArea } from "@/components/ui";
import type { MatchingPair, QuestionInput, QuestionType } from "@/lib/types";
import { questionTypeLabel } from "@/lib/utils";

const DEFAULT_MC_OPTIONS = ["A", "B", "C", "D", "E"];

type DraftQuestion = {
  order: number;
  type: QuestionType;
  prompt: string;
  options: string[] | MatchingPair[];
  correctAnswer: string;
  matchingAnswers: Record<string, string>;
  points: number;
};

function createDraft(order: number, type: QuestionType = "MULTIPLE_CHOICE"): DraftQuestion {
  return {
    order,
    type,
    prompt: "",
    options: type === "TRUE_FALSE" ? ["V", "F"] : [...DEFAULT_MC_OPTIONS],
    correctAnswer: type === "TRUE_FALSE" ? "V" : "A",
    matchingAnswers: { "1": "A", "2": "B", "3": "C", "4": "D" },
    points: 1,
  };
}

function buildMatchingOptions(pairs: MatchingPair[]): string[] {
  const letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");
  return pairs.map((_, index) => letters[index] ?? String(index + 1));
}

export default function NewExamPage() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [course, setCourse] = useState("");
  const [description, setDescription] = useState("");
  const [maxScore, setMaxScore] = useState(10);
  const [showDetailToStudent, setShowDetailToStudent] = useState(true);
  const [questionCount, setQuestionCount] = useState(50);
  const [defaultType, setDefaultType] = useState<QuestionType>("MULTIPLE_CHOICE");
  const [questions, setQuestions] = useState<DraftQuestion[]>(
    Array.from({ length: 50 }, (_, index) => createDraft(index + 1)),
  );
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [visibleRange, setVisibleRange] = useState({ from: 1, to: 10 });

  const totalPoints = useMemo(
    () => questions.reduce((sum, question) => sum + question.points, 0),
    [questions],
  );

  function regenerateQuestions(count: number, type: QuestionType) {
    setQuestions(Array.from({ length: count }, (_, index) => createDraft(index + 1, type)));
    setQuestionCount(count);
    setDefaultType(type);
  }

  function updateQuestion(order: number, patch: Partial<DraftQuestion>) {
    setQuestions((current) =>
      current.map((question) =>
        question.order === order ? { ...question, ...patch } : question,
      ),
    );
  }

  function handleTypeChange(order: number, type: QuestionType) {
    const base = createDraft(order, type);
    updateQuestion(order, base);
  }

  function buildPayload(): QuestionInput[] {
    return questions.map((question) => {
      if (question.type === "MATCHING") {
        const pairs =
          question.options.length > 0 &&
          typeof question.options[0] === "object"
            ? (question.options as MatchingPair[])
            : [
                { left: "Ítem 1", right: "" },
                { left: "Ítem 2", right: "" },
                { left: "Ítem 3", right: "" },
                { left: "Ítem 4", right: "" },
              ];

        return {
          order: question.order,
          type: question.type,
          prompt: question.prompt || undefined,
          options: pairs,
          correctAnswer: question.matchingAnswers,
          points: question.points,
        };
      }

      return {
        order: question.order,
        type: question.type,
        prompt: question.prompt || undefined,
        options:
          question.type === "TRUE_FALSE"
            ? ["V", "F"]
            : (question.options as string[]),
        correctAnswer: question.correctAnswer,
        points: question.points,
      };
    });
  }

  async function handleSubmit() {
    setError("");
    setLoading(true);

    const response = await fetch("/api/exams", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title,
        course,
        description,
        maxScore,
        showDetailToStudent,
        questions: buildPayload(),
      }),
    });

    const data = (await response.json()) as {
      error?: string;
      exam?: { id: string };
    };

    setLoading(false);

    if (!response.ok || !data.exam) {
      setError(data.error ?? "No se pudo crear el examen.");
      return;
    }

    router.push(`/docente/panel/examenes/${data.exam.id}`);
  }

  const visibleQuestions = questions.filter(
    (question) =>
      question.order >= visibleRange.from && question.order <= visibleRange.to,
  );

  return (
    <div className="min-h-screen bg-slate-50">
      <SiteHeader />
      <main className="mx-auto max-w-6xl space-y-6 px-4 py-10">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-slate-900">Nuevo examen</h1>
            <p className="text-slate-600">
              Cargá la rúbrica con las respuestas correctas para cada pregunta.
            </p>
          </div>
          <Link href="/docente/panel">
            <Button variant="secondary">Volver</Button>
          </Link>
        </div>

        <Card title="Datos generales">
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Título del examen">
              <Input
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="Examen 2 - Fisiopatología"
                required
              />
            </Field>
            <Field label="Materia / Cátedra">
              <Input
                value={course}
                onChange={(event) => setCourse(event.target.value)}
                placeholder="Medicina - 2° año"
              />
            </Field>
            <Field label="Nota máxima">
              <Input
                type="number"
                min={1}
                step={0.5}
                value={maxScore}
                onChange={(event) => setMaxScore(Number(event.target.value))}
              />
            </Field>
            <Field label="Cantidad de preguntas">
              <Input
                type="number"
                min={1}
                max={200}
                value={questionCount}
                onChange={(event) => {
                  const count = Number(event.target.value);
                  setQuestionCount(count);
                  regenerateQuestions(count, defaultType);
                }}
              />
            </Field>
            <Field label="Tipo por defecto">
              <Select
                value={defaultType}
                onChange={(event) => {
                  const type = event.target.value as QuestionType;
                  regenerateQuestions(questionCount, type);
                }}
              >
                <option value="MULTIPLE_CHOICE">Opción múltiple</option>
                <option value="TRUE_FALSE">Verdadero / Falso</option>
                <option value="MATCHING">Emparejamiento</option>
              </Select>
            </Field>
            <Field label="Feedback al alumno">
              <Select
                value={showDetailToStudent ? "yes" : "no"}
                onChange={(event) =>
                  setShowDetailToStudent(event.target.value === "yes")
                }
              >
                <option value="yes">Mostrar preguntas falladas</option>
                <option value="no">Solo mostrar nota</option>
              </Select>
            </Field>
            <div className="md:col-span-2">
              <Field label="Instrucciones para el aula (opcional)">
                <TextArea
                  rows={3}
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  placeholder="Recuerden que tienen 90 minutos. Luego de entregar el cuadernillo, ingresen al link..."
                />
              </Field>
            </div>
          </div>
        </Card>

        <Card title="Clave de respuestas (rúbrica)">
          <div className="mb-4 flex flex-wrap items-end gap-3">
            <Field label="Ver preguntas del">
              <Input
                type="number"
                min={1}
                max={questionCount}
                value={visibleRange.from}
                onChange={(event) =>
                  setVisibleRange((current) => ({
                    ...current,
                    from: Number(event.target.value),
                  }))
                }
              />
            </Field>
            <Field label="Al">
              <Input
                type="number"
                min={visibleRange.from}
                max={questionCount}
                value={visibleRange.to}
                onChange={(event) =>
                  setVisibleRange((current) => ({
                    ...current,
                    to: Number(event.target.value),
                  }))
                }
              />
            </Field>
            <p className="text-sm text-slate-500">
              Puntaje total: {totalPoints} pts · Escala final: {maxScore}
            </p>
          </div>

          <div className="space-y-4">
            {visibleQuestions.map((question) => (
              <div
                key={question.order}
                className="rounded-xl border border-slate-200 bg-slate-50 p-4"
              >
                <div className="mb-3 flex flex-wrap items-center gap-3">
                  <span className="rounded-lg bg-teal-100 px-3 py-1 text-sm font-semibold text-teal-800">
                    Pregunta {question.order}
                  </span>
                  <Select
                    value={question.type}
                    onChange={(event) =>
                      handleTypeChange(
                        question.order,
                        event.target.value as QuestionType,
                      )
                    }
                    className="max-w-xs"
                  >
                    <option value="MULTIPLE_CHOICE">Opción múltiple</option>
                    <option value="TRUE_FALSE">Verdadero / Falso</option>
                    <option value="MATCHING">Emparejamiento</option>
                  </Select>
                  <span className="text-xs text-slate-500">
                    {questionTypeLabel(question.type)}
                  </span>
                </div>

                {question.type === "MULTIPLE_CHOICE" ? (
                  <div className="grid gap-3 md:grid-cols-[1fr_auto]">
                    <Field label="Referencia breve (opcional)">
                      <Input
                        value={question.prompt}
                        onChange={(event) =>
                          updateQuestion(question.order, {
                            prompt: event.target.value,
                          })
                        }
                        placeholder="Ej. Caso clínico sobre insuficiencia cardíaca"
                      />
                    </Field>
                    <Field label="Respuesta correcta">
                      <Select
                        value={question.correctAnswer}
                        onChange={(event) =>
                          updateQuestion(question.order, {
                            correctAnswer: event.target.value,
                          })
                        }
                      >
                        {DEFAULT_MC_OPTIONS.map((option) => (
                          <option key={option} value={option}>
                            {option}
                          </option>
                        ))}
                      </Select>
                    </Field>
                  </div>
                ) : null}

                {question.type === "TRUE_FALSE" ? (
                  <Field label="Respuesta correcta">
                    <Select
                      value={question.correctAnswer}
                      onChange={(event) =>
                        updateQuestion(question.order, {
                          correctAnswer: event.target.value,
                        })
                      }
                      className="max-w-xs"
                    >
                      <option value="V">Verdadero</option>
                      <option value="F">Falso</option>
                    </Select>
                  </Field>
                ) : null}

                {question.type === "MATCHING" ? (
                  <div className="space-y-3">
                    <p className="text-sm text-slate-600">
                      Definí los ítems a emparejar y la letra correcta para cada
                      uno (A, B, C, D...).
                    </p>
                    {[1, 2, 3, 4].map((index) => {
                      const key = String(index);
                      const pairs =
                        question.options.length > 0 &&
                        typeof question.options[0] === "object"
                          ? (question.options as MatchingPair[])
                          : [];
                      const left = pairs[index - 1]?.left ?? `Ítem ${index}`;

                      return (
                        <div
                          key={key}
                          className="grid gap-3 md:grid-cols-[1fr_auto]"
                        >
                          <Field label={`Ítem ${index}`}>
                            <Input
                              value={left}
                              onChange={(event) => {
                                const nextPairs = [1, 2, 3, 4].map((item) => {
                                  const existing =
                                    (question.options as MatchingPair[])[
                                      item - 1
                                    ] ?? {
                                      left: `Ítem ${item}`,
                                      right: "",
                                    };
                                  return item === index
                                    ? { ...existing, left: event.target.value }
                                    : existing;
                                });
                                updateQuestion(question.order, {
                                  options: nextPairs,
                                });
                              }}
                            />
                          </Field>
                          <Field label="Respuesta">
                            <Select
                              value={question.matchingAnswers[key] ?? "A"}
                              onChange={(event) =>
                                updateQuestion(question.order, {
                                  matchingAnswers: {
                                    ...question.matchingAnswers,
                                    [key]: event.target.value,
                                  },
                                })
                              }
                            >
                              {buildMatchingOptions(
                                (question.options as MatchingPair[]) ?? [],
                              ).map((option) => (
                                <option key={option} value={option}>
                                  {option}
                                </option>
                              ))}
                            </Select>
                          </Field>
                        </div>
                      );
                    })}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </Card>

        {error ? <Alert>{error}</Alert> : null}

        <div className="flex justify-end gap-3">
          <Link href="/docente/panel">
            <Button variant="secondary">Cancelar</Button>
          </Link>
          <Button onClick={handleSubmit} disabled={loading || !title.trim()}>
            {loading ? "Guardando..." : "Crear examen y continuar"}
          </Button>
        </div>
      </main>
    </div>
  );
}
