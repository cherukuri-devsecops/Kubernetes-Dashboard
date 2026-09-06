import { useEffect, useRef, useState } from "react";
import { Navigate, useSearchParams } from "react-router-dom";

import { useAuth } from "@/context/AuthContext";

export function AuthCallbackPage() {
  const [searchParams] = useSearchParams();
  const { loginWithToken, status } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const attempted = useRef(false);

  useEffect(() => {
    if (attempted.current) {
      return;
    }
    attempted.current = true;

    const oauthError = searchParams.get("error");
    if (oauthError) {
      setError(oauthError);
      return;
    }

    const accessToken = searchParams.get("access_token");
    if (!accessToken) {
      setError("Login failed: no access token was returned.");
      return;
    }

    loginWithToken(accessToken).catch((caught) => {
      setError(caught instanceof Error ? caught.message : "Unable to sign in");
    });
  }, [loginWithToken, searchParams]);

  if (status === "authenticated") {
    return <Navigate to="/" replace />;
  }

  return (
    <main className="grid min-h-screen place-items-center bg-app px-4 py-10 text-content-primary">
      <section className="w-full max-w-md rounded-lg border border-line bg-surface p-6 text-center shadow-panel">
        {error ? (
          <>
            <p className="mb-4 text-sm text-signal-red">{error}</p>
            <a href="/login" className="text-sm font-semibold text-brand-400 hover:underline">
              Back to sign in
            </a>
          </>
        ) : (
          <p className="text-sm text-content-muted">Signing you in…</p>
        )}
      </section>
    </main>
  );
}
