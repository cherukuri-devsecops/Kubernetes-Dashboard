import { FormEvent, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { LogIn } from "lucide-react";

import { useAuth } from "@/context/AuthContext";
import { API_BASE_URL } from "@/api/client";

type LocationState = {
  from?: {
    pathname?: string;
  };
};

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { loginWithPassword, provider, status } = useAuth();
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("admin123");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (status === "authenticated") {
    return <Navigate to="/" replace />;
  }

  const locationState = location.state as LocationState | null;
  const nextPath = locationState?.from?.pathname ?? "/";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await loginWithPassword(email, password);
      navigate(nextPath, { replace: true });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to sign in");
    } finally {
      setSubmitting(false);
    }
  }

  function handleGoogleSignIn() {
    const callbackUrl = `${window.location.origin}/auth/callback`;
    const startUrl = `${API_BASE_URL}/api/auth/google/start?redirect_after=${encodeURIComponent(callbackUrl)}`;
    window.location.href = startUrl;
  }

  return (
    <main className="grid min-h-screen place-items-center bg-app px-4 py-10 text-content-primary">
      <section className="w-full max-w-md rounded-lg border border-line bg-surface p-6 shadow-panel">
        <div className="mb-8 flex items-center gap-3">
          <img
            src="/logo.png"
            alt="Kubernetes Dashboard"
            className="h-11 w-11 rounded-lg object-contain"
          />
          <div>
            <h1 className="text-xl font-semibold text-content-primary">Kubernetes Dashboard</h1>
            <p className="text-sm text-content-muted">Sign in to continue</p>
          </div>
        </div>

        {provider === "external" ? (
          <div className="space-y-4">
            {error ? (
              <div className="rounded-md border border-signal-red/30 bg-signal-red/10 px-3 py-2 text-sm text-signal-red">
                {error}
              </div>
            ) : null}
            <button
              type="button"
              onClick={handleGoogleSignIn}
              className="flex h-11 w-full items-center justify-center gap-2 rounded-md bg-brand px-4 text-sm font-semibold text-white transition hover:bg-brand-600"
            >
              <LogIn className="h-4 w-4" aria-hidden="true" />
              Sign in with Google
            </button>
          </div>
        ) : provider === "demo" ? (
          <form className="space-y-4" onSubmit={handleSubmit}>
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-content-secondary">Email</span>
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="email"
                className="h-11 w-full rounded-md border border-line bg-surface-hover/60 px-3 text-sm text-content-primary outline-none transition placeholder:text-content-muted focus:border-brand/50 focus:ring-2 focus:ring-brand/20"
                required
              />
            </label>

            <label className="block">
              <span className="mb-2 block text-sm font-medium text-content-secondary">Password</span>
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                className="h-11 w-full rounded-md border border-line bg-surface-hover/60 px-3 text-sm text-content-primary outline-none transition placeholder:text-content-muted focus:border-brand/50 focus:ring-2 focus:ring-brand/20"
                required
              />
            </label>

            {error ? (
              <div className="rounded-md border border-signal-red/30 bg-signal-red/10 px-3 py-2 text-sm text-signal-red">
                {error}
              </div>
            ) : null}

            <button
              type="submit"
              disabled={submitting}
              className="flex h-11 w-full items-center justify-center gap-2 rounded-md bg-brand px-4 text-sm font-semibold text-white transition hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <LogIn className="h-4 w-4" aria-hidden="true" />
              {submitting ? "Signing in" : "Sign in"}
            </button>
          </form>
        ) : (
          <p className="text-sm text-content-muted">Loading sign-in options…</p>
        )}
      </section>
    </main>
  );
}
