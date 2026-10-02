interface RecoveryGuidanceBannerProps {
  text: string;
  /** "primary" for neutral recovery hints, "destructive" for blocking issues. */
  tone?: "primary" | "destructive";
}

/**
 * Reusable guidance banner shown when a recovery action auto-locates a
 * destination. Mirrors the visual treatment of the existing beat-sheet hint so
 * every auto-located card reads consistently.
 */
export function RecoveryGuidanceBanner({ text, tone = "primary" }: RecoveryGuidanceBannerProps) {
  const className = tone === "destructive"
    ? "mb-3 rounded-lg border border-destructive/40 bg-destructive/[0.06] p-3 text-sm text-foreground"
    : "mb-3 rounded-lg border border-primary/40 bg-primary/[0.06] p-3 text-sm text-foreground";
  return (
    <div className={className}>
      <span className="font-medium">提示：</span>
      {text}
    </div>
  );
}
