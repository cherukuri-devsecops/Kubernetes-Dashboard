export type AuthenticatedUser = {
  email: string;
  name: string;
  role: string;
};

export const AUTH_TOKEN_KEY = "kubernetes-dashboard.stage1.token";
const AUTH_USER_KEY = "kubernetes-dashboard.stage1.user";

export function storeAuth(token: string, user: AuthenticatedUser) {
  window.localStorage.setItem(AUTH_TOKEN_KEY, token);
  window.localStorage.setItem(AUTH_USER_KEY, JSON.stringify(user));
}

export function readStoredAuth(): { token: string; user: AuthenticatedUser } | null {
  const token = window.localStorage.getItem(AUTH_TOKEN_KEY);
  const rawUser = window.localStorage.getItem(AUTH_USER_KEY);

  if (!token || !rawUser) {
    return null;
  }

  try {
    return { token, user: JSON.parse(rawUser) as AuthenticatedUser };
  } catch {
    clearStoredAuth();
    return null;
  }
}

export function clearStoredAuth() {
  window.localStorage.removeItem(AUTH_TOKEN_KEY);
  window.localStorage.removeItem(AUTH_USER_KEY);
}
