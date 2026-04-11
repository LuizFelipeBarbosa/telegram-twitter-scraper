import { clsx } from "clsx";

interface RuleProps {
  variant?: "bold" | "thin" | "dashed";
  className?: string;
}

export function Rule({ variant = "bold", className }: RuleProps) {
  return (
    <hr
      className={clsx(
        "border-0 border-t w-full m-0",
        variant === "bold" && "border-ink",
        variant === "thin" && "border-ink/20",
        variant === "dashed" && "border-ink/30 border-dashed",
        className,
      )}
    />
  );
}
