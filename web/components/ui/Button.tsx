import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

const buttonVariants = cva(
  "inline-flex min-h-9 items-center justify-center gap-2 rounded-sm border px-3 font-mono text-[13px] font-semibold transition disabled:cursor-not-allowed disabled:opacity-45",
  {
    variants: {
      variant: {
        primary: "border-accent bg-accent text-bg hover:brightness-110",
        secondary: "border-edge-strong bg-panel-2 text-ink hover:border-muted",
        ghost: "border-transparent bg-transparent text-muted hover:bg-panel-2 hover:text-ink",
        danger: "border-err/60 bg-err/10 text-err hover:bg-err/20",
      },
      size: {
        sm: "min-h-8 px-2.5 text-xs",
        md: "min-h-9 px-3",
        lg: "min-h-11 px-5 text-sm",
      },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export function Button({
  asChild,
  className,
  variant,
  size,
  ...props
}: ButtonProps) {
  const Component = asChild ? Slot : "button";
  return <Component className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}
