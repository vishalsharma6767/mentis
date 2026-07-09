import Constants from 'expo-constants';
import { Platform } from 'react-native';

const DEV_URL = 'http://localhost:8000';
const PROD_URL = (process as any).env?.EXPO_PUBLIC_API_URL || Constants.expoConfig?.extra?.apiUrl || 'https://mentis-api-t9hk.onrender.com';

export const BASE_URL = __DEV__ ? DEV_URL : PROD_URL;

export type LearningMode = 'math' | 'science' | 'coding' | 'book' | 'homework' | 'language' | 'diagram';
export type LearnerLevel = 'beginner' | 'intermediate' | 'advanced';

async function appendImage(formData: FormData, imageUri: string) {
  if (Platform.OS === 'web') {
    const blob = await fetch(imageUri).then((res) => res.blob());
    formData.append('file', blob, 'problem.jpg');
    return;
  }

  formData.append('file', {
    uri: imageUri,
    type: 'image/jpeg',
    name: 'problem.jpg',
  } as any);
}

export const api = {
  async recognizeProblem(imageUri: string, mode: LearningMode = 'math'): Promise<{
    type: string;
    title: string;
    content: string;
    difficulty: string;
    detectedElements?: string[];
    arTargets?: {
      label: string;
      x: number;
      y: number;
      width: number;
      height: number;
    }[];
  }> {
    const formData = new FormData();
    await appendImage(formData, imageUri);
    formData.append('mode', mode);

    const res = await fetch(`${BASE_URL}/api/tutor/recognize`, {
      method: 'POST',
      body: formData,
    });
    return res.json();
  },

  async generateLesson(
    problemType: string,
    content: string,
    level: LearnerLevel = 'intermediate',
    mode: LearningMode = 'math',
  ): Promise<{
    steps: {
      number: number;
      instruction: string;
      explanation: string;
      hint: string;
      answer: string;
      ar_annotation?: string;
      focus?: string;
    }[];
    final_answer: string;
    key_concept: string;
    confidence_check?: string;
    recommended_practice?: string[];
  }> {
    const formData = new FormData();
    formData.append('problem_type', problemType);
    formData.append('content', content);
    formData.append('level', level);
    formData.append('mode', mode);

    const res = await fetch(`${BASE_URL}/api/tutor/lesson`, {
      method: 'POST',
      body: formData,
    });
    return res.json();
  },

  async getStepHelp(
    problemType: string,
    content: string,
    completed: any[],
    current: any,
  ): Promise<{ help: string }> {
    const formData = new FormData();
    formData.append('problem_type', problemType);
    formData.append('content', content);
    formData.append('completed', JSON.stringify(completed));
    formData.append('current', JSON.stringify(current));

    const res = await fetch(`${BASE_URL}/api/tutor/help`, {
      method: 'POST',
      body: formData,
    });
    return res.json();
  },

  async askDoubt(data: {
    content: string;
    question: string;
    current?: any;
    level?: LearnerLevel;
    mode?: LearningMode;
  }): Promise<{
    reply: string;
    pen_annotation: string;
    follow_up: string;
  }> {
    const formData = new FormData();
    formData.append('content', data.content);
    formData.append('question', data.question);
    formData.append('current', JSON.stringify(data.current ?? {}));
    formData.append('level', data.level ?? 'intermediate');
    formData.append('mode', data.mode ?? 'math');

    const res = await fetch(`${BASE_URL}/api/tutor/doubt`, {
      method: 'POST',
      body: formData,
    });
    return res.json();
  },

  async createSessionPdf(data: {
    title: string;
    problem: string;
    steps: any[];
    transcript: any[];
    penNotes: any[];
  }): Promise<{
    filename: string;
    mime: string;
    base64: string;
  }> {
    const formData = new FormData();
    formData.append('title', data.title);
    formData.append('problem', data.problem);
    formData.append('steps', JSON.stringify(data.steps));
    formData.append('transcript', JSON.stringify(data.transcript));
    formData.append('pen_notes', JSON.stringify(data.penNotes));

    const res = await fetch(`${BASE_URL}/api/tutor/session-pdf`, {
      method: 'POST',
      body: formData,
    });
    return res.json();
  },

  async transcribeAudio(uri: string): Promise<{ text: string }> {
    const formData = new FormData();
    formData.append('file', {
      uri,
      type: 'audio/m4a',
      name: 'recording.m4a',
    } as any);
    const res = await fetch(`${BASE_URL}/api/tutor/transcribe`, {
      method: 'POST',
      body: formData,
    });
    return res.json();
  },

  async saveSession(data: {
    userId: string;
    problemTitle: string;
    problemType: string;
    extractedText: string;
    status: string;
    steps: string;
  }): Promise<{ id: string }> {
    const formData = new FormData();
    Object.entries(data).forEach(([k, v]) => formData.append(k, v));
    const res = await fetch(`${BASE_URL}/api/tutor/sessions`, {
      method: 'POST',
      body: formData,
    });
    return res.json();
  },

  async listSessions(userId: string, limit = 20): Promise<{ sessions: any[] }> {
    const res = await fetch(`${BASE_URL}/api/tutor/sessions?userId=${encodeURIComponent(userId)}&limit=${limit}`);
    return res.json();
  },

  async saveProfile(userId: string, data: { name: string; grade: string; subjects: string[]; goal: string }): Promise<void> {
    const res = await fetch(`${BASE_URL}/api/auth/save-profile`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, ...data }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to save profile' }));
      throw new Error(err.detail);
    }
  },

  async setPassword(userId: string, password: string): Promise<void> {
    const res = await fetch(`${BASE_URL}/api/auth/set-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to set password' }));
      throw new Error(err.detail);
    }
  },

  async getStats(userId: string): Promise<{
    totalSessions: number;
    completedSessions: number;
    topTopics: [string, number][];
  }> {
    const res = await fetch(`${BASE_URL}/api/tutor/stats?userId=${encodeURIComponent(userId)}`);
    return res.json();
  },

  async getStreak(userId: string): Promise<{ streak: number; lastActive: string | null }> {
    const res = await fetch(`${BASE_URL}/api/tutor/streak?userId=${encodeURIComponent(userId)}`);
    return res.json();
  },
};
