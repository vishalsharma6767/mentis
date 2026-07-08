export interface UserSession {
  userId: string;
  email: string;
  sessionId: string;
}

export interface AuthState {
  isAuthenticated: boolean;
  isLoading: boolean;
  user: UserSession | null;
}

export interface AppwriteConfig {
  endpoint: string;
  projectId: string;
}
