import { NextResponse } from "next/server";
import { getTeacherIdFromSession } from "@/lib/auth";
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

  const exam = await prisma.exam.findFirst({
    where: { id, teacherId },
    include: {
      questions: {
        orderBy: { order: "asc" },
      },
      sessions: {
        include: {
          _count: {
            select: { submissions: true },
          },
        },
        orderBy: { createdAt: "desc" },
      },
    },
  });

  if (!exam) {
    return NextResponse.json({ error: "Examen no encontrado." }, { status: 404 });
  }

  return NextResponse.json({ exam });
}

export async function DELETE(_request: Request, { params }: RouteParams) {
  const teacherId = await getTeacherIdFromSession();
  if (!teacherId) {
    return NextResponse.json({ error: "No autorizado." }, { status: 401 });
  }

  const { id } = await params;

  const exam = await prisma.exam.findFirst({
    where: { id, teacherId },
  });

  if (!exam) {
    return NextResponse.json({ error: "Examen no encontrado." }, { status: 404 });
  }

  await prisma.exam.delete({ where: { id } });

  return NextResponse.json({ ok: true });
}
