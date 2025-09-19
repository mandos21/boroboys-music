import { useMemo } from "react";
import type { AppView, AuthState, UserSummary } from "../types";

type TopBarProps = {
  authState: AuthState;
  user: UserSummary | null;
  activeView: AppView;
  onSelectView: (view: AppView) => void;
  onLogin: () => void;
  onLogout: () => void;
};

function TopBar({ authState, user, activeView, onSelectView, onLogin, onLogout }: TopBarProps) {
  const navOptions = useMemo(() => {
    const options: Array<{ id: AppView; label: string }> = [
      { id: "submit", label: "Submit Track" },
      { id: "history", label: "Playlist History" },
      { id: "lookup", label: "Song Lookup" },
    ];

    if (user?.role === "admin") {
      options.push({ id: "admin", label: "Admin" });
    }

    return options;
  }, [user]);

  return (
    <header className="topbar">
      <div className="topbar__brand">Boro Crew Music</div>
      <nav className="topbar__nav">
        {navOptions.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            className={`topbar__pill${id === activeView ? " topbar__pill--active" : ""}`}
            onClick={() => onSelectView(id)}
            disabled={authState !== "authenticated"}
          >
            {label}
          </button>
        ))}
      </nav>
      <div className="topbar__auth">
        {authState === "authenticated" && user ? (
          <>
            <span className="topbar__user">{user.display_name?.trim() || user.username}</span>
            <button className="secondary small" onClick={onLogout}>
              Log out
            </button>
          </>
        ) : authState === "unauthenticated" ? (
          <button className="primary small" onClick={onLogin}>
            Log in
          </button>
        ) : null}
      </div>
    </header>
  );
}

export default TopBar;
