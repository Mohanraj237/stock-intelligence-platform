import { cn } from "@/lib/utils";

export function Table({ className, ...rest }: React.TableHTMLAttributes<HTMLTableElement>) {
  return (
    <div className="w-full overflow-x-auto">
      <table
        className={cn("w-full caption-bottom text-sm border-collapse", className)}
        {...rest}
      />
    </div>
  );
}

export function THead({ className, ...rest }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className={cn("border-b border-[var(--color-border)] bg-[var(--color-surface-2)]", className)} {...rest} />;
}

export function TBody({ className, ...rest }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn("[&_tr:last-child]:border-0", className)} {...rest} />;
}

export function TR({ className, ...rest }: React.HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr
      className={cn(
        "border-b border-[var(--color-border)] transition-colors hover:bg-[var(--color-surface-2)]/60",
        className,
      )}
      {...rest}
    />
  );
}

export function TH({ className, ...rest }: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={cn(
        "h-9 px-3 text-left align-middle font-medium text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] whitespace-nowrap",
        className,
      )}
      {...rest}
    />
  );
}

export function TD({ className, ...rest }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("px-3 py-2 align-middle whitespace-nowrap", className)} {...rest} />;
}
