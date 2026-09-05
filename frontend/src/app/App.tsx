import { Link, Route, Routes } from "react-router";

function HomePage() {
  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">Music Rounds</p>
        <h1>Curated listening, on your group&apos;s schedule.</h1>
        <p>The v2 frontend foundation is ready for OIDC and round workflows.</p>
      </section>
    </main>
  );
}

function SignedOutPage() {
  return (
    <main className="shell">
      <section className="panel">
        <h1>You have been signed out.</h1>
        <Link to="/">Return to Music Rounds</Link>
      </section>
    </main>
  );
}

export function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/signed-out" element={<SignedOutPage />} />
    </Routes>
  );
}
