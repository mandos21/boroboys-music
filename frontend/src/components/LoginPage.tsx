type LoginPageProps = {
  onLogin: () => void;
  loading: boolean;
  error: string | null;
};

function LoginPage({ onLogin, loading, error }: LoginPageProps) {
  return (
    <section className="card auth">
      <h1>Boro Crew Music</h1>
      <p>Sign in with Spotify to access the monthly playlist tools.</p>
      <button onClick={onLogin} disabled={loading} className="primary">
        {loading ? "Contacting Spotify…" : "Continue with Spotify"}
      </button>
      {error && <p className="error">{error}</p>}
    </section>
  );
}

export default LoginPage;
