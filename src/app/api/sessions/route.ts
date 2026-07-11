import { NextResponse } from "next/server";
import { getTeacherIdFromSession } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { generateSessionCode } from "@/lib/utils";

export async function POST(request: Request) {
  const teacherId = await getTeacherIdFromSession();
  if (!teacherId) {
    return NextResponse.json({ error: "No autorizado." }, { status: 401 });
  }

  try {
    const body = (await request.json()) as {
      examId?: string;
      label?: string;
      opensAt?: string | null;
      closesAt?: string | null;
    };

    const examId = body.examId?.trim();
    if (!examId) {
      return NextResponse.json(
        { error: "El examen es obligatorio." },
        { status: 400 },
      );
    }

    const exam = await prisma.exam.findFirst({
      where: { id: examId, teacherId },
    });

    if (!exam) {
      return NextResponse.json({ error: "Examen no encontrado." }, { status: 404 });
    }

    let code = generateSessionCode();
    let attempts = 0;
    while (attempts < 5) {
      const existing = await prisma.session.findUnique({ where: { code } });
      if (!existing) break;
      code = generateSessionCode();
      attempts += 1;
    }

    const session = await prisma.session.create({
      data: {
        examId,
        code,
        label: body.label?.trim() || null,
        opensAt: body.opensAt ? new Date(body.opensAt) : null,
        closesAt: body.closesAt ? new Date(body.closesAt) : null,
        isActive: true,
      },
    });

    return NextResponse.json({ session }, { status: 201 });
  } catch {
    return NextResponse.json(
      { error: "No se pudo crear la sesión." },
      { status: 500 },
    );
  }
}
