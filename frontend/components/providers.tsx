"use client";

import * as React from "react";
import { ThemeProvider, useTheme } from "next-themes";
import { SWRConfig } from "swr";
import { Toaster } from "sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { swrFetcher } from "@/lib/api";

function ThemedToaster() {
  const { resolvedTheme } = useTheme();
  return <Toaster theme={(resolvedTheme as "light" | "dark") ?? "dark"} position="bottom-right" richColors closeButton toastOptions={{ className: "text-sm" }} />;
}

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false} disableTransitionOnChange>
      <SWRConfig value={{ fetcher: swrFetcher, revalidateOnFocus: true, shouldRetryOnError: true, errorRetryCount: 2, dedupingInterval: 1500 }}>
        <TooltipProvider delayDuration={200}>
          {children}
          <ThemedToaster />
        </TooltipProvider>
      </SWRConfig>
    </ThemeProvider>
  );
}
