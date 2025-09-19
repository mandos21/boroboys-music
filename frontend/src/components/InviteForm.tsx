import { useState, type FormEvent } from "react";
import type { Role } from "../types";

type InviteFormProps = {
  onCreate: (payload: { email?: string | null; role: Role; expires_in_days: number }) => Promise<void>;
  busy: boolean;
};

function InviteForm({ onCreate, busy }: InviteFormProps) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("member");
  const [expiresInDays, setExpiresInDays] = useState(7);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    try {
      await onCreate({ email: email.trim() ? email.trim() : null, role, expires_in_days: expiresInDays });
      setEmail("");
      setRole("member");
      setExpiresInDays(7);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to create invite";
      setError(message);
    }
  };

  return (
    <form className="invite-form" onSubmit={handleSubmit}>
      <div className="field">
        <label>Email (optional)</label>
        <input type="email" placeholder="friend@example.com" value={email} onChange={(event) => setEmail(event.target.value)} />
      </div>
      <div className="field-row">
        <label>Role</label>
        <select value={role} onChange={(event) => setRole(event.target.value as Role)}>
          <option value="member">Member</option>
          <option value="admin">Admin</option>
        </select>
      </div>
      <div className="field-row">
        <label>Expires in</label>
        <input min={1} max={30} type="number" value={expiresInDays} onChange={(event) => setExpiresInDays(Number(event.target.value))} />
        <span>days</span>
      </div>
      <button className="primary invite-button" type="submit" disabled={busy}>
        {busy ? "Creating…" : "Create invite"}
      </button>
      {error && <p className="error">{error}</p>}
    </form>
  );
}

export default InviteForm;
