import { NextResponse } from "next/server";
import { hashPin, setTeacherSession } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as {
      name?: string;
      pin?: string;
    };

    const name = body.name?.trim();
    const pin = body.pin?.trim();

    if (!name || !pin || pin.length < 4) {
      return NextResponse.json(
        { error: "Nombre y PIN (mínimo 4 dígitos) son obligatorios." },
        { status: 400 },
      );
    }

    const existing = await prisma.teacher.findFirst({
      where: { name },
    });

    if (existing) {
      return NextResponse.json(
        { error: "Ya existe un docente con ese nombre. Iniciá sesión." },
        { status: 409 },
      );
    }

    const teacher = await prisma.teacher.create({
      data: {
        name,
        pinHash: hashPin(pin),
      },
    });

    await setTeacherSession(teacher.id);

    return NextResponse.json({
      id: teacher.id,
      name: teacher.name,
    });
  } catch {
    return NextResponse.json(
      { error: "No se pudo registrar al docente." },
      { status: 500 },
    );
  }
}
