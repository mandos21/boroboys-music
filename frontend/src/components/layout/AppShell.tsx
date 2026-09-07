import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Dialog } from "@base-ui/react/dialog";
import { LogOut, Menu, Music2, UserRound, X } from "lucide-react";
import { Link, useLocation } from "react-router";

import { api, logout } from "../../api/client";
import { ThemeToggle } from "../ui/ThemeToggle";

type Session = { user: { email: string | null; displayName: string | null; platformRole: string } };
type AppShellProps = { children: ReactNode };

function AccountIdentity({ user, compact = false }: { user: Session["user"]; compact?: boolean }) {
  return <><span className="account-avatar" aria-hidden="true">{(user.displayName ?? user.email ?? "M").slice(0, 1).toUpperCase()}</span>{!compact && <span className="account-copy"><strong>{user.displayName ?? "Listener"}</strong><small>{user.platformRole}</small></span>}</>;
}

export function AppShell({ children }: AppShellProps) {
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const session = useQuery({ queryKey: ["session"], queryFn: () => api<Session>("/auth/session"), retry: false });
  const user = session.data?.user;

  async function signOut() {
    try { window.location.assign(await logout()); } catch { window.location.assign("/signed-out"); }
  }

  return (
    <div className="app-frame">
      <header className="app-header">
        <div className="app-header-inner">
          <Link aria-label="BoroCrew Music home" className="brand" to="/"><span className="brand-mark" aria-hidden="true"><Music2 size={20} strokeWidth={2.4} /></span><span><strong>BoroCrew Music</strong><small>What are you listening to?</small></span></Link>
          {user ? <>
            <ThemeToggle />
            <div className="desktop-account"><Link className="account-profile-link" to="/profile" aria-label="Open your profile"><AccountIdentity user={user} /></Link><button className="icon-button" type="button" onClick={signOut} aria-label="Sign out"><LogOut aria-hidden="true" size={18} /></button></div>
            <Dialog.Root open={menuOpen} onOpenChange={setMenuOpen}>
              <Dialog.Trigger className="mobile-menu-trigger" aria-label="Open account menu"><Menu aria-hidden="true" size={22} /></Dialog.Trigger>
              <Dialog.Portal><Dialog.Backdrop className="mobile-nav-backdrop" /><Dialog.Popup className="mobile-nav-dialog" aria-label="Account menu">
                <div className="mobile-nav-heading"><span className="eyebrow">BoroCrew Music</span><Dialog.Close className="icon-button" aria-label="Close account menu"><X aria-hidden="true" size={20} /></Dialog.Close></div>
                <Link className="mobile-profile-link" to="/profile" onClick={() => setMenuOpen(false)}><UserRound aria-hidden="true" size={18} /><AccountIdentity user={user} /></Link>
                <button className="button button-secondary mobile-sign-out" type="button" onClick={signOut}><LogOut aria-hidden="true" size={17} />Sign out</button>
              </Dialog.Popup></Dialog.Portal>
            </Dialog.Root>
          </> : <div className="header-signed-out-actions"><ThemeToggle /><a className="header-sign-in" href={`/api/v1/auth/login?return=${encodeURIComponent(location.pathname)}`}>Sign in</a></div>}
        </div>
      </header>
      <div className="app-content">{children}</div>
    </div>
  );
}
