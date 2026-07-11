import { createHash, randomBytes, timingSafeEqual } from "crypto";
import { cookies } from "next/headers";

const TEACHER_COOKIE = "evaluar_teacher_id";
const TEACHER_TOKEN_COOKIE = "evaluar_teacher_token";

export function hashPin(pin: string): string {
  return createHash("sha256").update(pin).digest("hex");
}

export function verifyPin(pin: string, pinHash: string): boolean {
  const input = Buffer.from(hashPin(pin));
  const stored = Buffer.from(pinHash);
  if (input.length !== stored.length) return false;
  return timingSafeEqual(input, stored);
}

export function createTeacherToken(): string {
  return randomBytes(32).toString("hex");
}

export async function getTeacherIdFromSession(): Promise<string | null> {
  const cookieStore = await cookies();
  const teacherId = cookieStore.get(TEACHER_COOKIE)?.value;
  const token = cookieStore.get(TEACHER_TOKEN_COOKIE)?.value;

  if (!teacherId || !token) return null;
  return teacherId;
}

export async function setTeacherSession(teacherId: string): Promise<string> {
  const token = createTeacherToken();
  const cookieStore = await cookies();
  cookieStore.set(TEACHER_COOKIE, teacherId, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 30,
  });
  cookieStore.set(TEACHER_TOKEN_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 30,
  });
  return token;
}

export async function clearTeacherSession(): Promise<void> {
  const cookieStore = await cookies();
  cookieStore.delete(TEACHER_COOKIE);
  cookieStore.delete(TEACHER_TOKEN_COOKIE);
}
