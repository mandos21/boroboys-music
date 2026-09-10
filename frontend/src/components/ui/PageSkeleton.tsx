type PageSkeletonProps = {
  label: string;
  variant?: "dashboard" | "detail" | "profile" | "workspace";
};

/** Preserve the destination's visual rhythm while route data is loading. */
export function PageSkeleton({ label, variant = "detail" }: PageSkeletonProps) {
  const blocks = variant === "dashboard" ? 4 : variant === "profile" ? 6 : 3;
  return (
    <main
      className={`shell page-skeleton page-skeleton-${variant}`}
      aria-busy="true"
      aria-label={label}
    >
      <span className="skeleton-sr-status" role="status">
        {label}
      </span>
      <Skeleton className="skeleton-line skeleton-kicker" />
      <Skeleton className="skeleton-line skeleton-title" />
      <Skeleton className="skeleton-line skeleton-copy" />
      <Skeleton className="skeleton-line skeleton-copy skeleton-copy-short" />
      <div className="skeleton-grid">
        {Array.from({ length: blocks }, (_, index) => (
          <div className="skeleton-card" key={index}>
            <Skeleton className="skeleton-line skeleton-card-title" />
            <Skeleton className="skeleton-line skeleton-card-copy" />
            <Skeleton className="skeleton-line skeleton-card-copy skeleton-card-copy-short" />
          </div>
        ))}
      </div>
    </main>
  );
}
import { Skeleton } from "./skeleton";
