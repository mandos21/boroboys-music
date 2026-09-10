import { useEffect, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { LogOut, Menu, Music2, UserRound, X } from "lucide-react";
import { Link, useLocation } from "react-router";

import { api, logout } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { avatarStyle } from "../../lib/avatar";
import { markPerformance } from "../../lib/performance";
import { Sheet, SheetClose, SheetContent, SheetTitle, SheetTrigger } from "../ui/sheet";
import { ThemeToggle } from "../ui/ThemeToggle";
import { TooltipProvider } from "../ui/tooltip";
import { Button } from "../ui/button";

type Session = { user: { email: string | null; displayName: string | null; platformRole: string } };
type AppShellProps = { children: ReactNode };

function AccountIdentity({ user, compact = false }: { user: Session["user"]; compact?: boolean }) {
  return (
    <>
      <span
        className="account-avatar"
        style={avatarStyle(user.displayName ?? user.email)}
        aria-hidden="true"
      >
        {(user.displayName ?? user.email ?? "M").slice(0, 1).toUpperCase()}
      </span>
      {!compact && (
        <span className="account-copy">
          <strong>{user.displayName ?? "Listener"}</strong>
          <small>{user.platformRole}</small>
        </span>
      )}
    </>
  );
}

export function AppShell({ children }: AppShellProps) {
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const session = useQuery({
    queryKey: queryKeys.session(),
    queryFn: () => api<Session>("/auth/session"),
    retry: false,
  });
  const user = session.data?.user;

  useEffect(() => {
    if (session.isSuccess) markPerformance("shell-ready", "app-start");
  }, [session.isSuccess]);

  async function signOut() {
    try {
      window.location.assign(await logout());
    } catch {
      window.location.assign("/signed-out");
    }
  }

  return (
    <TooltipProvider closeDelay={80} delay={250}>
      <div className="app-frame">
        <header className="app-header">
          <div className="app-header-inner">
            <Link aria-label="BoroCrew Music home" className="brand" to="/">
              <span className="brand-mark" aria-hidden="true">
                <Music2 size={20} strokeWidth={2.4} />
              </span>
              <span>
                <strong>BoroCrew Music</strong>
                <small>What are you listening to?</small>
              </span>
            </Link>
            {user ? (
              <>
                <ThemeToggle />
                <div className="desktop-account">
                  <Link
                    className="account-profile-link"
                    to="/profile"
                    aria-label="Open your profile"
                  >
                    <AccountIdentity user={user} />
                  </Link>
                  <Button
                    className="icon-button"
                    size="icon"
                    variant="ghost"
                    type="button"
                    onClick={signOut}
                    aria-label="Sign out"
                  >
                    <LogOut aria-hidden="true" size={18} />
                  </Button>
                </div>
                <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
                  <SheetTrigger className="mobile-menu-trigger" aria-label="Open account menu">
                    <Menu aria-hidden="true" size={22} />
                  </SheetTrigger>
                  <SheetContent
                    aria-label="Account menu"
                    className="mobile-nav-dialog"
                    showCloseButton={false}
                  >
                    <div className="mobile-nav-heading">
                      <SheetTitle className="sr-only">Account menu</SheetTitle>
                      <span className="eyebrow">BoroCrew Music</span>
                      <SheetClose className="icon-button" aria-label="Close account menu">
                        <X aria-hidden="true" size={20} />
                      </SheetClose>
                    </div>
                    <Link
                      className="mobile-profile-link"
                      to="/profile"
                      onClick={() => setMenuOpen(false)}
                    >
                      <UserRound aria-hidden="true" size={18} />
                      <AccountIdentity user={user} />
                    </Link>
                    <Button
                      className="mobile-sign-out"
                      variant="secondary"
                      type="button"
                      onClick={signOut}
                    >
                      <LogOut aria-hidden="true" size={17} />
                      Sign out
                    </Button>
                  </SheetContent>
                </Sheet>
              </>
            ) : (
              <div className="header-signed-out-actions">
                <ThemeToggle />
                <a
                  className="header-sign-in"
                  href={`/api/v1/auth/login?return=${encodeURIComponent(location.pathname)}`}
                >
                  Sign in
                </a>
              </div>
            )}
          </div>
        </header>
        <div className="app-content">{children}</div>
      </div>
    </TooltipProvider>
  );
}
