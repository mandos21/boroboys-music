import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Dialog } from "@base-ui/react/dialog";
import { LogOut, Menu, Music2, Settings2, ShieldCheck, X } from "lucide-react";
import { Link, NavLink, useLocation } from "react-router";

import { api, logout } from "../../api/client";

type Session = {
  user: {
    email: string | null;
    displayName: string | null;
    platformRole: string;
  };
};

type AppShellProps = {
  children: ReactNode;
};

function navigation(onNavigate?: () => void) {
  return (
    <nav aria-label="Primary navigation" className="app-nav">
      <NavLink end onClick={onNavigate} to="/">
        <Music2 aria-hidden="true" size={18} />
        My rounds
      </NavLink>
      <NavLink onClick={onNavigate} to="/settings/connections">
        <Settings2 aria-hidden="true" size={18} />
        Connections
      </NavLink>
      <NavLink onClick={onNavigate} to="/admin">
        <ShieldCheck aria-hidden="true" size={18} />
        Manage
      </NavLink>
    </nav>
  );
}

export function AppShell({ children }: AppShellProps) {
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const session = useQuery({
    queryKey: ["session"],
    queryFn: () => api<Session>("/auth/session"),
    retry: false,
  });
  const user = session.data?.user;
  const isSignedIn = Boolean(user);

  async function signOut() {
    try {
      window.location.assign(await logout());
    } catch {
      window.location.assign("/signed-out");
    }
  }

  return (
    <div className="app-frame">
      <header className="app-header">
        <div className="app-header-inner">
          <Link aria-label="Music Rounds home" className="brand" to="/">
            <span className="brand-mark" aria-hidden="true">
              <Music2 size={20} strokeWidth={2.4} />
            </span>
            <span>
              <strong>Music Rounds</strong>
              <small>Shared listening, thoughtfully timed</small>
            </span>
          </Link>
          {isSignedIn ? (
            <>
              <div className="desktop-navigation">{navigation()}</div>
              <div className="desktop-account">
                <span className="account-avatar" aria-hidden="true">
                  {(user?.displayName ?? user?.email ?? "M").slice(0, 1).toUpperCase()}
                </span>
                <span className="account-copy">
                  <strong>{user?.displayName ?? "Listener"}</strong>
                  <small>{user?.platformRole}</small>
                </span>
                <button className="icon-button" type="button" onClick={signOut} aria-label="Sign out">
                  <LogOut aria-hidden="true" size={18} />
                </button>
              </div>
              <Dialog.Root open={menuOpen} onOpenChange={setMenuOpen}>
                <Dialog.Trigger className="mobile-menu-trigger" aria-label="Open navigation">
                  <Menu aria-hidden="true" size={22} />
                </Dialog.Trigger>
                <Dialog.Portal>
                  <Dialog.Backdrop className="mobile-nav-backdrop" />
                  <Dialog.Popup className="mobile-nav-dialog" aria-label="Navigation menu">
                    <div className="mobile-nav-heading">
                      <span className="eyebrow">Music Rounds</span>
                      <Dialog.Close className="icon-button" aria-label="Close navigation">
                        <X aria-hidden="true" size={20} />
                      </Dialog.Close>
                    </div>
                    {navigation(() => setMenuOpen(false))}
                    <div className="mobile-account">
                      <span className="account-avatar" aria-hidden="true">
                        {(user?.displayName ?? user?.email ?? "M").slice(0, 1).toUpperCase()}
                      </span>
                      <span>
                        <strong>{user?.displayName ?? "Listener"}</strong>
                        <small>{user?.email ?? user?.platformRole}</small>
                      </span>
                    </div>
                    <button className="button button-secondary mobile-sign-out" type="button" onClick={signOut}>
                      <LogOut aria-hidden="true" size={17} />
                      Sign out
                    </button>
                  </Dialog.Popup>
                </Dialog.Portal>
              </Dialog.Root>
            </>
          ) : (
            <a className="header-sign-in" href={`/api/v1/auth/login?return=${encodeURIComponent(location.pathname)}`}>
              Sign in
            </a>
          )}
        </div>
      </header>
      <div className="app-content">{children}</div>
    </div>
  );
}
