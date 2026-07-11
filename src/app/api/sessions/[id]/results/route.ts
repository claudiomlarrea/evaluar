import { NextResponse } from "next/server";
import { getTeacherIdFromSession } from "@/lib/auth";
import { parseQuestionFromDb } from "@/lib/grading";
import { prisma } from "@/lib/prisma";

type RouteParams = {
  params: Promise<{ id: string }>;
};

export async function GET(_request: Request, { params }: RouteParams) {
  const teacherId = await getTeacherIdFromSession();
  if (!teacherId) {
    return NextResponse.json({ error: "No autorizado." }, { status: 401 });
  }

  const { id } = await params;

  const session = await prisma.session.findFirst({
    where: {
      id,
      exam: { teacherId },
    },
    include: {
      exam: {
        include: {
          questions: {
            orderBy: { order: "asc" },
          },
        },
      },
      submissions: {
        orderBy: [{ score: "desc" }, { studentName: "asc" }],
      },
    },
  });

  if (!session) {
    return NextResponse.json({ error: "Sesión no encontrada." }, { status: 404 });
  }

  const questions = session.exam.questions.map(parseQuestionFromDb);
  const questionStats = questions.map((question) => {
    let correct = 0;
    let incorrect = 0;
    let unanswered = 0;

    for (const submission of session.submissions) {
      const answers = JSON.parse(submission.answers) as Record<string, string>;
      const answer = answers[String(question.order)]?.trim();
      if (!answer) {
        unanswered += 1;
        continue;
      }

      const wrongList = JSON.parse(submission.wrongQuestions) as number[];
      if (wrongList.includes(question.order)) {
        incorrect += 1;
      } else {
        correct += 1;
      }
    }

    const total = session.submissions.length;
    return {
      order: question.order,
      type: question.type,
      correct,
      incorrect,
      unanswered,
      successRate: total === 0 ? 0 : Math.round((correct / total) * 100),
    };
  });

  const submissions = session.submissions.map((submission) => ({
    id: submission.id,
    studentName: submission.studentName,
    studentDni: submission.studentDni,
    score: submission.score,
    correctCount: submission.correctCount,
    wrongCount: submission.wrongCount,
    unansweredCount: submission.unansweredCount,
    wrongQuestions: JSON.parse(submission.wrongQuestions) as number[],
    submittedAt: submission.submittedAt,
  }));

  return NextResponse.json({
    session: {
      id: session.id,
      code: session.code,
      label: session.label,
      isActive: session.isActive,
      opensAt: session.opensAt,
      closesAt: session.closesAt,
    },
    exam: {
      id: session.exam.id,
      title: session.exam.title,
      course: session.exam.course,
      maxScore: session.exam.maxScore,
      questionCount: questions.length,
    },
    submissions,
    questionStats,
  });
}

export async function PATCH(request: Request, { params }: RouteParams) {
  const teacherId = await getTeacherIdFromSession();
  if (!teacherId) {
    return NextResponse.json({ error: "No autorizado." }, { status: 401 });
  }

  const { id } = await params;

  try {
    const body = (await request.json()) as {
      isActive?: boolean;
      opensAt?: string | null;
      closesAt?: string | null;
    };

    const session = await prisma.session.findFirst({
      where: {
        id,
        exam: { teacherId },
      },
    });

    if (!session) {
      return NextResponse.json({ error: "Sesión no encontrada." }, { status: 404 });
    }

    const updated = await prisma.session.update({
      where: { id },
      data: {
        isActive: body.isActive ?? session.isActive,
        opensAt:
          body.opensAt === undefined
            ? session.opensAt
            : body.opensAt
              ? new Date(body.opensAt)
              : null,
        closesAt:
          body.closesAt === undefined
            ? session.closesAt
            : body.closesAt
              ? new Date(body.closesAt)
              : null,
      },
    });

    return NextResponse.json({ session: updated });
  } catch {
    return NextResponse.json(
      { error: "No se pudo actualizar la sesión." },
      { status: 500 },
    );
  }
}
