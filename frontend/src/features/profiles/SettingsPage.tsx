import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { Switch } from "../../components/ui/switch";
import { ConnectionsPanel } from "../connections/ConnectionsPanel";
import "../connections/connections.css";
import { NotificationSettingsPanel } from "./NotificationSettingsPanel";
import "./profiles.css";

/** Everything about *how the account behaves* - connected services and
 * emails - kept apart from the profile page, which is about the listening
 * record itself. */
export function SettingsPage() {
  return (
    <main className="shell settings-shell">
      <Link className="back" to="/profile">
        ← Your profile
      </Link>
      <header className="page-heading settings-heading">
        <div>
          <p className="eyebrow">Your account</p>
          <h1>Settings</h1>
          <p>Manage connected services, email notifications, and appearance.</p>
        </div>
      </header>
      <SetupSection id="connections-title" title="Connected services" eyebrow="Your setup">
        <ConnectionsPanel />
      </SetupSection>
      <SetupSection id="notifications-title" title="Email notifications">
        <NotificationSettingsPanel />
      </SetupSection>
      <SetupSection id="appearance-title" title="Appearance">
        <ColorPaletteSetting />
      </SetupSection>
    </main>
  );
}

function ColorPaletteSetting() {
  const [colorblind, setColorblind] = useState(
    () => window.localStorage.getItem("music-rounds-palette") === "colorblind",
  );
  useEffect(() => {
    document.documentElement.dataset.palette = colorblind ? "colorblind" : "default";
    window.localStorage.setItem("music-rounds-palette", colorblind ? "colorblind" : "default");
  }, [colorblind]);
  return (
    <label className="notification-toggle appearance-toggle">
      <span>
        <span className="notification-toggle-label">Distinguishable result colors</span>
        <span className="notification-toggle-description">
          Show correct and incorrect results in blue and amber.
        </span>
      </span>
      <Switch checked={colorblind} onCheckedChange={setColorblind} />
    </label>
  );
}

function SetupSection({
  id,
  title,
  eyebrow,
  children,
}: {
  id: string;
  title: string;
  /** Only the first section of the group carries the group's eyebrow. */
  eyebrow?: string;
  children: ReactNode;
}) {
  return (
    <section className="profile-setup-section" aria-labelledby={id}>
      <div className="section-heading">
        <div>
          {eyebrow && <p className="eyebrow">{eyebrow}</p>}
          <h2 id={id}>{title}</h2>
        </div>
      </div>
      {children}
    </section>
  );
}
