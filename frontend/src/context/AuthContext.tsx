import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { fetchMe, loginRequest, signupRequest, Photo, User } from '@/lib/api';
import { clearToken, loadToken, saveToken } from '@/lib/tokenStorage';

type AuthState = {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  signIn: (username: string, password: string) => Promise<void>;
  signUp: (f: { username: string; email: string; password: string; photo?: Photo | null }) => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // On app start: restore a saved session, if any.
  useEffect(() => {
    (async () => {
      try {
        const saved = await loadToken();
        if (saved) {
          setUser(await fetchMe(saved));
          setToken(saved);
        }
      } catch {
        await clearToken(); // expired or invalid token
      } finally {
        setIsLoading(false);
      }
    })();
  }, []);

  const signIn = useCallback(async (username: string, password: string) => {
    const { access_token } = await loginRequest(username, password);
    const me = await fetchMe(access_token);
    await saveToken(access_token);
    setToken(access_token);
    setUser(me);
  }, []);

  const signUp: AuthState['signUp'] = useCallback(async (f) => {
    await signupRequest(f);
    await signIn(f.username, f.password);
  }, [signIn]);

  const signOut = useCallback(async () => {
    await clearToken();
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, token, isLoading, signIn, signUp, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}