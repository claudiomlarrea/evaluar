import { NextResponse } from "next/server";
import { getTeacherIdFromSession } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import type { QuestionInput } from "@/lib/types";

export async function GET() {
  const teacherId = await getTeacherIdFromSession();
  if (!teacherId) {
    return NextResponse.json({ error: "No autorizado." }, { status: 401 });
  }

  const exams = await prisma.exam.findMany({
    where: { teacherId },
    include: {
      _count: {
        select: {
          questions: true,
          sessions: true,
        },
      },
    },
    orderBy: { createdAt: "desc" },
  });

  return NextResponse.json({ exams });
}

export async function POST(request: Request) {
  const teacherId = await getTeacherIdFromSession();
  if (!teacherId) {
    return NextResponse.json({ error: "No autorizado." }, { status: 401 });
  }

  try {
    const body = (await request.json()) as {
      title?: string;
      course?: string;
      description?: string;
      maxScore?: number;
      showDetailToStudent?: boolean;
      questions?: QuestionInput[];
    };

    const title = body.title?.trim();
    const questions = body.questions ?? [];

    if (!title) {
      return NextResponse.json(
        { error: "El título del examen es obligatorio." },
        { status: 400 },
      );
    }

    if (questions.length === 0) {
      return NextResponse.json(
        { error: "Debés cargar al menos una pregunta con su respuesta correcta." },
        { status: 400 },
      );
    }

    for (const question of questions) {
      if (!question.correctAnswer) {
        return NextResponse.json(
          {
            error: `La pregunta ${question.order} no tiene respuesta correcta definida.`,
          },
          { status: 400 },
        );
      }
    }

    const exam = await prisma.exam.create({
      data: {
        teacherId,
        title,
        course: body.course?.trim() || null,
        description: body.description?.trim() || null,
        maxScore: body.maxScore ?? 10,
        showDetailToStudent: body.showDetailToStudent ?? true,
        questions: {
          create: questions.map((question) => ({
            order: question.order,
            type: question.type,
            prompt: question.prompt?.trim() || null,
            options: JSON.stringify(question.options ?? []),
            correctAnswer:
              typeof question.correctAnswer === "string"
                ? question.correctAnswer
                : JSON.stringify(question.correctAnswer),
            points: question.points ?? 1,
          })),
        },
      },
      include: {
        questions: {
          orderBy: { order: "asc" },
        },
      },
    });

    return NextResponse.json({ exam }, { status: 201 });
  } catch {
    return NextResponse.json(
      { error: "No se pudo crear el examen." },
      { status: 500 },
    );
  }
}
