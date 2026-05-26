import { cn } from "@/lib/utils";

export function EmptyState({
  title, description, action, icon: Icon, className,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  icon?: React.ComponentType<{ className?: string }>;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-md border border-dashed border-[var(--color-border)] bg-[var(--color-surface)]/40",
        "py-10 px-4 text-center",
        className,
      )}
    >
      {Icon && <Icon className="size-8 mx-auto mb-2 text-[var(--color-text-muted)]" />}
      <div className="text-sm font-medium text-white">{title}</div>
      {description && (
        <p className="text-xs muted mt-1 max-w-sm mx-auto">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <EmptyState
      title="Couldn't load data"
      description={message}
      action={
        retry && (
          <button
            type="button"
            onClick={retry}
            className="text-xs underline text-[var(--color-primary)] hover:text-white focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)] rounded"
          >
            Retry
          </button>
        )
      }
    />
  );
}
