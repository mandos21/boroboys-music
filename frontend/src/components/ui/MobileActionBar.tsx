import { useEffect, useState, type ReactNode } from "react";

/** A mobile-only, action-specific footer for pages where the primary control
 * can otherwise drift beyond a comfortably reachable scroll position. */
export function MobileActionBar({ children, label }: { children: ReactNode; label: string }) {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const updateVisibility = () => setIsVisible(window.scrollY > 180);
    updateVisibility();
    window.addEventListener("scroll", updateVisibility, { passive: true });
    return () => window.removeEventListener("scroll", updateVisibility);
  }, []);

  if (!isVisible) return null;
  return (
    <aside className="mobile-action-bar" aria-label={label}>
      {children}
    </aside>
  );
}
