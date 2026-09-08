import { Link } from "react-router";

import { ConnectionsPanel } from "./ConnectionsPanel";

/** A direct settings route retained for links outside the profile page. */
export function ConnectionsPage() {
  return (
    <main className="shell settings-shell">
      <Link className="back" to="/profile">
        ← Your profile
      </Link>
      <header className="page-heading settings-heading">
        <div>
          <p className="eyebrow">Your profile</p>
          <h1>Profile &amp; connected services</h1>
          <p>
            Bring the services you already use into your series. You stay in control of what is
            connected and what listening evidence is shared.
          </p>
        </div>
      </header>
      <ConnectionsPanel />
    </main>
  );
}

export { ConnectionsPanel } from "./ConnectionsPanel";
