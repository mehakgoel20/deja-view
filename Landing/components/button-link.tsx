import Link from "next/link";
import type { ComponentProps } from "react";

const styles = {
  primary: "bg-ink text-paper hover:bg-brand-dark",
  secondary: "border border-line text-ink hover:border-ink",
};

type Props = ComponentProps<typeof Link> & { variant?: keyof typeof styles; size?: "md" | "lg" };

export function ButtonLink({ variant = "primary", size = "md", className = "", ...props }: Props) {
  const sizing = size === "lg" ? "px-5 py-3 text-base" : "px-3.5 py-2 text-sm";
  return (
    <Link
      className={`inline-flex items-center justify-center rounded-md font-semibold whitespace-nowrap ${sizing} ${styles[variant]} ${className}`}
      {...props}
    />
  );
}
