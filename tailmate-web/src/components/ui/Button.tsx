import { clsx } from "clsx";
import type { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  icon?: ReactNode;
}

const variantClassName: Record<ButtonVariant, string> = {
  primary:
    "bg-[var(--organic-primary)] text-[#f3f4f1] shadow-[var(--shadow-soft)] hover:bg-[var(--organic-primary-hover)]",
  secondary:
    "bg-[var(--organic-secondary)] text-white shadow-[var(--shadow-soft)] hover:bg-[var(--organic-secondary-hover)] rounded-[30%_70%_70%_30%_/_30%_30%_70%_70%]",
  ghost:
    "border border-[color:var(--organic-border)] bg-[rgba(254,254,250,0.8)] text-[var(--organic-foreground)] hover:bg-white",
  danger:
    "bg-[var(--organic-destructive)] text-white shadow-[var(--shadow-soft)] hover:opacity-95",
};

export function buttonClassName(variant: ButtonVariant = "primary", className?: string) {
  return clsx(
    "organic-button inline-flex items-center justify-center gap-2 rounded-full px-5 py-3 text-sm font-bold tracking-[0.01em] disabled:cursor-not-allowed disabled:opacity-60 [&>span]:flex [&>span]:items-center",
    variantClassName[variant],
    className,
  );
}

export function Button({
  children,
  className,
  variant = "primary",
  icon,
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button type={type} className={buttonClassName(variant, className)} {...props}>
      {icon && <span className="flex items-center justify-center">{icon}</span>}
      {children && <span>{children}</span>}
    </button>
  );
}
