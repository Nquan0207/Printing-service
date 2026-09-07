import { useCallback, useEffect, useState } from "react";
import { api, setUserId, type User } from "./api";

const STORAGE_KEY = "stockroom.user";

/**
 * Session state. There is no real authentication: login resolves an email to
 * a user id which is then sent as X-Stockroom-User. It is a user *picker*,
 * not a credential check.
 */
export function useSession() {
  const [user, setUser] = useState<User | null>(() => {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw) as User;
      setUserId(parsed.user_id);
      return parsed;
    } catch {
      return null;
    }
  });

  useEffect(() => {
    setUserId(user?.user_id ?? null);
  }, [user]);

  const login = useCallback(async (email: string, name?: string) => {
    const next = await api.login(email, name);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    setUserId(next.user_id);
    setUser(next);
    return next;
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setUserId(null);
    setUser(null);
  }, []);

  return { user, login, logout };
}
