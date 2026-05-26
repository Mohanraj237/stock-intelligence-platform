import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "@radix-ui/react-slot";
import { forwardRef } from "react";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors disabled:opacity-50 disabled:pointer-events-none",
  {
    variants: {
      variant: {
        default:    "bg-[var(--color-primary)] text-white hover:opacity-90",
        secondary:  "bg-[var(--color-surface-2)] text-white hover:bg-[var(--color-border)]",
        outline:    "border border-[var(--color-border)] hover:bg-[var(--color-surface-2)]",
        ghost:      "hover:bg-[var(--color-surface-2)]",
        danger:     "bg-[var(--color-danger)] text-white hover:opacity-90",
        success:    "bg-[var(--color-success)] text-white hover:opacity-90",
      },
      size: {
        default: "h-9 px-4",
        sm:      "h-8 px-3 text-xs",
        lg:      "h-10 px-6",
        icon:    "size-9",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild, ...rest }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...rest} />;
  },
);
Button.displayName = "Button";

export { buttonVariants };
