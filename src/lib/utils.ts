import { customAlphabet } from "nanoid";

const alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ";
export const generateSessionCode = customAlphabet(alphabet, 8);

export function formatScore(score: number): string {
  return score.toFixed(2).replace(/\.00$/, "");
}

export function formatDateTime(value: Date | string | null): string {
  if (!value) return "Sin límite";
  const date = typeof value === "string" ? new Date(value) : value;
  return new Intl.DateTimeFormat("es-AR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(date);
}

export function isSessionOpen(session: {
  isActive: boolean;
  opensAt: Date | null;
  closesAt: Date | null;
}): boolean {
  if (!session.isActive) return false;
  const now = new Date();
  if (session.opensAt && now < session.opensAt) return false;
  if (session.closesAt && now > session.closesAt) return false;
  return true;
}

export function questionTypeLabel(type: string): string {
  switch (type) {
    case "MULTIPLE_CHOICE":
      return "Opción múltiple";
    case "TRUE_FALSE":
      return "Verdadero / Falso";
    case "MATCHING":
      return "Emparejamiento";
    default:
      return type;
  }
}
