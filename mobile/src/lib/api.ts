import { Platform } from 'react-native';
import Constants from 'expo-constants';

const DEV_URL = 'http://localhost:8000';
const PROD_URL = Constants.expoConfig?.extra?.apiUrl ?? 'https://mentis-api.onrender.com';

export const BASE_URL = __DEV__ ? DEV_URL : PROD_URL;

export const api = {
  async recognizeProblem(imageUri: string): Promise<{
    type: string;
    title: string;
    content: string;
    difficulty: string;
  }> {
    const formData = new FormData();
    formData.append('file', {
      uri: imageUri,
      type: 'image/jpeg',
      name: 'problem.jpg',
    } as any);

    const res = await fetch(`${BASE_URL}/api/tutor/recognize`, {
      method: 'POST',
      body: formData,
    });
    return res.json();
  },

  async generateLesson(
    problemType: string,
    content: string,
    level: string = 'intermediate',
  ): Promise<{
    steps: {
      number: number;
      instruction: string;
      explanation: string;
      hint: string;
      answer: string;
    }[];
    final_answer: string;
    key_concept: string;
  }> {
    const formData = new FormData();
    formData.append('problem_type', problemType);
    formData.append('content', content);
    formData.append('level', level);

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

  async getStats(userId: string): Promise<{
    totalSessions: number;
    completedSessions: number;
    topTopics: [string, number][];
  }> {
    const res = await fetch(`${BASE_URL}/api/tutor/stats?userId=${encodeURIComponent(userId)}`);
    return res.json();
  },
};
