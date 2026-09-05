import { useState, type FormEvent } from "react";
import type { User } from "../lib/api";

type Props = {
  onLogin: (email: string, name?: string) => Promise<User>;
  shopEnabled: boolean;
};

const SUGGESTED = ["alice@stockroom.local", "bob@stockroom.local", "admin@stockroom.local"];

export default function Login({ onLogin, shopEnabled }: Props) {
  const [email, setEmail] = useState("alice@stockroom.local");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onLogin(email.trim(), name.trim() || undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <form onSubmit={submit}>
        <h1>
          RAKSUL <span>Stockroom</span>
        </h1>
        <p className="lede">
          Enter an email to continue. Unknown addresses create a new account.
        </p>

        <label>
          Email
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
        </label>
        <label>
          Name <small>(new accounts only)</small>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Optional" />
        </label>

        <button type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Continue"}
        </button>

        {error && <p className="error">{error}</p>}

        <div className="suggest">
          {SUGGESTED.map((s) => (
            <button key={s} type="button" onClick={() => setEmail(s)}>
              {s}
            </button>
          ))}
        </div>

        {!shopEnabled && (
          <p className="warn">
            The shop is currently disabled (<code>SHOP_ENABLED=false</code>). Signing in as a
            non-admin will show <strong>Page not found</strong>.
          </p>
        )}

        <p className="fineprint">
          No password is taken and nothing is verified — this is a demo user picker, not
          authentication.
        </p>
      </form>
    </div>
  );
}
