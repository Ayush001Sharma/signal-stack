import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 whitespace-nowrap rounded-md border px-2 py-0.5 text-[11px] font-medium leading-4 transition-colors focus:outline-none focus:ring-2 focus:ring-ring",
  {
    variants: {
      tone: {
        default: "border-primary/30 bg-primary/10 text-primary",
        slate: "border-slate-500/30 bg-slate-500/10 text-slate-600 dark:text-slate-300",
        rose: "border-rose-500/30 bg-rose-500/10 text-rose-600 dark:text-rose-300",
        amber: "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300",
        emerald: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
        blue: "border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300",
        orange: "border-orange-500/30 bg-orange-500/10 text-orange-700 dark:text-orange-300",
        violet: "border-violet-500/30 bg-violet-500/10 text-violet-700 dark:text-violet-300",
        outline: "border-border text-muted-foreground",
      },
    },
    defaultVariants: { tone: "default" },
  },
);

export type BadgeTone = NonNullable<VariantProps<typeof badgeVariants>["tone"]>;

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

function Badge({ className, tone, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}

export { Badge, badgeVariants };
