import { NextResponse } from "next/server";
import { setTeacherSession, verifyPin } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as {
      name?: string;
      pin?: string;
    };

    const name = body.name?.trim();
    const pin = body.pin?.trim();

    if (!name || !pin) {
      return NextResponse.json(
        { error: "Nombre y PIN son obligatorios." },
        { status: 400 },
      );
    }

    const teacher = await prisma.teacher.findFirst({
      where: { name },
    });

    if (!teacher || !verifyPin(pin, teacher.pinHash)) {
      return NextResponse.json(
        { error: "Credenciales incorrectas." },
        { status: 401 },
      );
    }

    await setTeacherSession(teacher.id);

    return NextResponse.json({
      id: teacher.id,
      name: teacher.name,
    });
  } catch {
    return NextResponse.json(
      { error: "No se pudo iniciar sesión." },
      { status: 500 },
    );
  }
}
