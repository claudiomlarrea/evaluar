import type { GradeResult, ParsedQuestion, StudentAnswers } from "./types";

function normalizeAnswer(value: string): string {
  return value.trim().toUpperCase();
}

function parseStoredAnswer(
  value: string | Record<string, string>,
): string | Record<string, string> {
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value) as unknown;
      if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
        return parsed as Record<string, string>;
      }
    } catch {
      return value;
    }
    return value;
  }
  return value;
}

function answersMatch(
  studentAnswer: string,
  correctAnswer: string | Record<string, string>,
  type: ParsedQuestion["type"],
): boolean {
  const correct = parseStoredAnswer(correctAnswer);

  if (type === "MATCHING") {
    if (typeof correct !== "object") return false;
    let studentObj: Record<string, string>;
    try {
      studentObj = JSON.parse(studentAnswer) as Record<string, string>;
    } catch {
      return false;
    }

    const keys = Object.keys(correct);
    if (keys.length === 0) return false;

    return keys.every(
      (key) =>
        normalizeAnswer(studentObj[key] ?? "") ===
        normalizeAnswer(String(correct[key])),
    );
  }

  return (
    normalizeAnswer(studentAnswer) ===
    normalizeAnswer(String(correct))
  );
}

export function gradeSubmission(
  questions: ParsedQuestion[],
  answers: StudentAnswers,
  maxScore: number,
): GradeResult {
  let totalPoints = 0;
  let earnedPoints = 0;
  let correctCount = 0;
  let wrongCount = 0;
  let unansweredCount = 0;
  const wrongQuestions: number[] = [];

  for (const question of questions) {
    totalPoints += question.points;
    const studentAnswer = answers[String(question.order)]?.trim();

    if (!studentAnswer) {
      unansweredCount += 1;
      wrongQuestions.push(question.order);
      continue;
    }

    const isCorrect = answersMatch(
      studentAnswer,
      question.correctAnswer,
      question.type,
    );

    if (isCorrect) {
      correctCount += 1;
      earnedPoints += question.points;
    } else {
      wrongCount += 1;
      wrongQuestions.push(question.order);
    }
  }

  const score =
    totalPoints === 0 ? 0 : Number(((earnedPoints / totalPoints) * maxScore).toFixed(2));

  return {
    score,
    correctCount,
    wrongCount,
    unansweredCount,
    wrongQuestions,
    totalPoints,
    earnedPoints,
  };
}

export function parseQuestionFromDb(question: {
  id: string;
  order: number;
  type: string;
  prompt: string | null;
  options: string;
  correctAnswer: string;
  points: number;
}): ParsedQuestion {
  let options: ParsedQuestion["options"] = [];
  try {
    options = JSON.parse(question.options) as ParsedQuestion["options"];
  } catch {
    options = [];
  }

  let correctAnswer: string | Record<string, string> = question.correctAnswer;
  try {
    const parsed = JSON.parse(question.correctAnswer) as unknown;
    if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
      correctAnswer = parsed as Record<string, string>;
    }
  } catch {
    correctAnswer = question.correctAnswer;
  }

  return {
    id: question.id,
    order: question.order,
    type: question.type as ParsedQuestion["type"],
    prompt: question.prompt,
    options,
    correctAnswer,
    points: question.points,
  };
}
