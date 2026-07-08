import { account, ID } from './appwrite';
import * as storage from './storage';
import { UserSession } from '../types';

const SESSION_KEY = 'mentis_session';

async function saveSession(userId: string, email: string, sessionId: string) {
  const session: UserSession = { userId, email, sessionId };
  await storage.setItem(SESSION_KEY, JSON.stringify(session));
}

async function getSavedSession(): Promise<UserSession | null> {
  try {
    const data = await storage.getItem(SESSION_KEY);
    return data ? JSON.parse(data) : null;
  } catch {
    return null;
  }
}

async function clearSession() {
  await storage.deleteItem(SESSION_KEY);
}

export async function sendOTP(email: string): Promise<string> {
  const token = await account.createEmailToken(ID.unique(), email);
  return token.userId;
}

export async function verifyOTP(userId: string, secret: string): Promise<UserSession> {
  const session = await account.createSession(userId, secret);
  const user = await account.get();
  const userSession: UserSession = {
    userId: user.$id,
    email: user.email ?? '',
    sessionId: session.$id,
  };
  await saveSession(userSession.userId, userSession.email, userSession.sessionId);
  return userSession;
}

export async function restoreSession(): Promise<UserSession | null> {
  const saved = await getSavedSession();
  if (!saved) return null;
  try {
    await account.get();
    return saved;
  } catch {
    await clearSession();
    return null;
  }
}

export async function logout(): Promise<void> {
  try {
    await account.deleteSession('current');
  } catch {
  } finally {
    await clearSession();
  }
}
