import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badge = cva(
  "inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider",
  {
    variants: {
      variant: {
        default: "bg-[var(--color-surface-2)] text-[var(--color-text)]",
        success: "bg-[color-mix(in_oklab,var(--color-success)_18%,transparent)] text-[var(--color-success)]",
        warning: "bg-[color-mix(in_oklab,var(--color-warning)_18%,transparent)] text-[var(--color-warning)]",
        danger:  "bg-[color-mix(in_oklab,var(--color-danger)_18%,transparent)] text-[var(--color-danger)]",
        info:    "bg-[color-mix(in_oklab,var(--color-primary)_18%,transparent)] text-[var(--color-primary)]",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export function Badge({ className, variant, ...rest }: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badge>) {
  return <span className={cn(badge({ variant }), className)} {...rest} />;
}
