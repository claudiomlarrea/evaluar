export type QuestionType = "MULTIPLE_CHOICE" | "TRUE_FALSE" | "MATCHING";

export type MatchingPair = {
  left: string;
  right: string;
};

export type QuestionInput = {
  order: number;
  type: QuestionType;
  prompt?: string;
  options: string[] | MatchingPair[];
  correctAnswer: string | Record<string, string>;
  points?: number;
};

export type StudentAnswers = Record<string, string>;

export type GradeResult = {
  score: number;
  correctCount: number;
  wrongCount: number;
  unansweredCount: number;
  wrongQuestions: number[];
  totalPoints: number;
  earnedPoints: number;
};

export type ParsedQuestion = {
  id: string;
  order: number;
  type: QuestionType;
  prompt: string | null;
  options: string[] | MatchingPair[];
  correctAnswer: string | Record<string, string>;
  points: number;
};
