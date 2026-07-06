import { NextResponse } from "next/server";
import { gradeSubmission, parseQuestionFromDb } from "@/lib/grading";
import { prisma } from "@/lib/prisma";
import { isSessionOpen } from "@/lib/utils";
import type { StudentAnswers } from "@/lib/types";

type RouteParams = {
  params: Promise<{ code: string }>;
};

export async function GET(_request: Request, { params }: RouteParams) {
  const { code } = await params;

  const session = await prisma.session.findUnique({
    where: { code: code.toUpperCase() },
    include: {
      exam: {
        include: {
          questions: {
            orderBy: { order: "asc" },
          },
        },
      },
    },
  });

  if (!session) {
    return NextResponse.json({ error: "Sesión no encontrada." }, { status: 404 });
  }

  const open = isSessionOpen(session);
  const questions = session.exam.questions.map((question) => {
    const parsed = parseQuestionFromDb(question);
    return {
      order: parsed.order,
      type: parsed.type,
      prompt: parsed.prompt,
      options: parsed.options,
      points: parsed.points,
    };
  });

  return NextResponse.json({
    session: {
      code: session.code,
      label: session.label,
      isActive: session.isActive,
      isOpen: open,
      opensAt: session.opensAt,
      closesAt: session.closesAt,
    },
    exam: {
      title: session.exam.title,
      course: session.exam.course,
      description: session.exam.description,
      maxScore: session.exam.maxScore,
      showDetailToStudent: session.exam.showDetailToStudent,
      questionCount: questions.length,
    },
    questions,
  });
}

export async function POST(request: Request, { params }: RouteParams) {
  const { code } = await params;

  try {
    const body = (await request.json()) as {
      studentName?: string;
      studentDni?: string;
      answers?: StudentAnswers;
    };

    const studentName = body.studentName?.trim();
    const studentDni = body.studentDni?.trim().replace(/\D/g, "");
    const answers = body.answers ?? {};

    if (!studentName || !studentDni) {
      return NextResponse.json(
        { error: "Nombre y DNI/matrícula son obligatorios." },
        { status: 400 },
      );
    }

    const session = await prisma.session.findUnique({
      where: { code: code.toUpperCase() },
      include: {
        exam: {
          include: {
            questions: {
              orderBy: { order: "asc" },
            },
          },
        },
      },
    });

    if (!session) {
      return NextResponse.json({ error: "Sesión no encontrada." }, { status: 404 });
    }

    if (!isSessionOpen(session)) {
      return NextResponse.json(
        { error: "Esta sesión no está abierta para envíos." },
        { status: 403 },
      );
    }

    const existing = await prisma.submission.findUnique({
      where: {
        sessionId_studentDni: {
          sessionId: session.id,
          studentDni,
        },
      },
    });

    if (existing) {
      return NextResponse.json(
        { error: "Ya enviaste tus respuestas para este examen." },
        { status: 409 },
      );
    }

    const parsedQuestions = session.exam.questions.map(parseQuestionFromDb);
    const result = gradeSubmission(
      parsedQuestions,
      answers,
      session.exam.maxScore,
    );

    const submission = await prisma.submission.create({
      data: {
        sessionId: session.id,
        studentName,
        studentDni,
        answers: JSON.stringify(answers),
        score: result.score,
        correctCount: result.correctCount,
        wrongCount: result.wrongCount,
        unansweredCount: result.unansweredCount,
        wrongQuestions: JSON.stringify(result.wrongQuestions),
      },
    });

    return NextResponse.json({
      submission: {
        id: submission.id,
        score: submission.score,
        correctCount: submission.correctCount,
        wrongCount: submission.wrongCount,
        unansweredCount: submission.unansweredCount,
        wrongQuestions: result.wrongQuestions,
        totalQuestions: parsedQuestions.length,
        showDetail: session.exam.showDetailToStudent,
        maxScore: session.exam.maxScore,
      },
    });
  } catch {
    return NextResponse.json(
      { error: "No se pudieron enviar las respuestas." },
      { status: 500 },
    );
  }
}
