"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import {
  Activity,
  BarChart3,
  Bot,
  Building2,
  CalendarClock,
  FileText,
  History,
  Layers,
  LayoutDashboard,
  Menu,
  MessagesSquare,
  Moon,
  Newspaper,
  Plus,
  Radar,
  Settings,
  ShieldCheck,
  Sun,
  Swords,
  Upload,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { useApi } from "@/hooks/use-api";
import { paths } from "@/lib/api";
import type { CompanySummary } from "@/lib/types";
import { cn, initials } from "@/lib/utils";

type NavItem = { href: string; label: string; icon: React.ComponentType<{ className?: string }> };

const NAV_GROUPS: Array<{ label: string; items: NavItem[] }> = [
  {
    label: "Intelligence",
    items: [
      { href: "", label: "Overview", icon: LayoutDashboard },
      { href: "/feed", label: "Intelligence Feed", icon: Newspaper },
      { href: "/brief", label: "Monday Brief", icon: FileText },
      { href: "/competitors", label: "Competitors", icon: Swords },
      { href: "/history", label: "Reports History", icon: History },
    ],
  },
  {
    label: "Company",
    items: [
      { href: "/profile", label: "Intelligence Profile", icon: Building2 },
      { href: "/interview", label: "AI Interview", icon: MessagesSquare },
      { href: "/uploads", label: "Internal Uploads", icon: Upload },
    ],
  },
  {
    label: "Sources",
    items: [
      { href: "/signal-stack", label: "Signal Stack", icon: Layers },
      { href: "/sources", label: "Source Manager", icon: Radar },
      { href: "/health", label: "Health & Audit", icon: ShieldCheck },
    ],
  },
  {
    label: "System",
    items: [
      { href: "/automation", label: "Automation", icon: CalendarClock },
      { href: "/settings", label: "Settings", icon: Settings },
    ],
  },
];

function useCompanyIdFromPath(): number | null {
  const pathname = usePathname();
  const m = pathname?.match(/^\/companies\/(\d+)/);
  return m ? Number(m[1]) : null;
}

function Brand() {
  return (
    <Link href="/" className="flex items-center gap-2.5 rounded-md px-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 shadow-lg shadow-indigo-500/30">
        <Activity className="h-4 w-4 text-white" aria-hidden />
      </div>
      <div className="leading-tight">
        <div className="text-sm font-semibold tracking-tight">Signal Stack</div>
        <div className="text-[10px] text-muted-foreground">Company Intelligence</div>
      </div>
    </Link>
  );
}

function SidebarNav({ companyId, onNavigate }: { companyId: number | null; onNavigate?: () => void }) {
  const pathname = usePathname();
  if (!companyId) {
    return (
      <nav aria-label="Main" className="space-y-1 px-3">
        <NavLink href="/" label="All companies" icon={BarChart3} active={pathname === "/"} onNavigate={onNavigate} />
        <NavLink href="/companies/new" label="Add company" icon={Plus} active={pathname === "/companies/new"} onNavigate={onNavigate} />
      </nav>
    );
  }
  const base = `/companies/${companyId}`;
  return (
    <nav aria-label="Main" className="space-y-5 px-3">
      {NAV_GROUPS.map((g) => (
        <div key={g.label}>
          <div className="mb-1.5 px-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/80">{g.label}</div>
          <div className="space-y-0.5">
            {g.items.map((it) => {
              const href = base + it.href;
              const active =
                it.href === ""
                  ? pathname === base
                  : it.href === "/brief"
                    ? pathname === href || pathname.startsWith(`${base}/briefs/`)
                    : it.href === "/history"
                      ? pathname.startsWith(href) || pathname.startsWith(`${base}/audits/`)
                      : pathname.startsWith(href);
              return <NavLink key={it.href} href={href} label={it.label} icon={it.icon} active={active} onNavigate={onNavigate} />;
            })}
          </div>
        </div>
      ))}
    </nav>
  );
}

function NavLink({ href, label, icon: Icon, active, onNavigate }: { href: string; label: string; icon: NavItem["icon"]; active: boolean; onNavigate?: () => void }) {
  return (
    <Link
      href={href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={cn(
        "group flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        active ? "bg-primary/10 font-medium text-foreground ring-1 ring-inset ring-primary/20" : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
      )}
    >
      <Icon className={cn("h-4 w-4 shrink-0", active ? "text-primary" : "text-muted-foreground group-hover:text-foreground")} />
      <span className="truncate">{label}</span>
    </Link>
  );
}

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => setMounted(true), []);
  const dark = !mounted || resolvedTheme !== "light";
  return (
    <Button variant="ghost" size="icon-sm" onClick={() => setTheme(dark ? "light" : "dark")} aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}>
      {dark ? <Sun /> : <Moon />}
    </Button>
  );
}

function CompanySwitcher({ companyId }: { companyId: number | null }) {
  const router = useRouter();
  const pathname = usePathname();
  const { data: companies } = useApi<CompanySummary[]>(paths.companies());
  const value = companyId ? String(companyId) : undefined;

  const onChange = (v: string) => {
    if (v === "__new") {
      router.push("/companies/new");
      return;
    }
    // Keep the current section when switching (detail pages fall back to the section root).
    let rest = "";
    const m = pathname.match(/^\/companies\/\d+(\/[^/]+)?/);
    if (m && m[1]) rest = m[1] === "/briefs" ? "/brief" : m[1] === "/audits" ? "/history" : m[1];
    router.push(`/companies/${v}${rest}`);
  };

  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="h-9 w-[200px] sm:w-[260px]" aria-label="Switch company">
        <SelectValue placeholder="Select a company" />
      </SelectTrigger>
      <SelectContent>
        {(companies ?? []).map((c) => (
          <SelectItem key={c.id} value={String(c.id)}>
            <span className="flex items-center gap-2">
              <span className="flex h-5 w-5 items-center justify-center rounded bg-primary/15 text-[9px] font-semibold text-primary">{initials(c.name)}</span>
              {c.name}
            </span>
          </SelectItem>
        ))}
        <SelectItem value="__new">
          <span className="flex items-center gap-2 text-primary">
            <Plus className="h-4 w-4" /> Add company
          </span>
        </SelectItem>
      </SelectContent>
    </Select>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const companyId = useCompanyIdFromPath();
  const [open, setOpen] = React.useState(false);

  return (
    <div className="flex min-h-screen">
      <a href="#main" className="sr-only z-50 rounded bg-primary px-3 py-2 text-primary-foreground focus:not-sr-only focus:fixed focus:left-2 focus:top-2">
        Skip to content
      </a>
      {/* Desktop sidebar */}
      <aside className="no-print sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground lg:flex">
        <div className="flex h-14 items-center border-b px-4">
          <Brand />
        </div>
        <div className="flex-1 overflow-y-auto py-4">
          <SidebarNav companyId={companyId} />
        </div>
        <div className="border-t p-3 text-[11px] text-muted-foreground">
          <div className="flex items-center gap-2">
            <Bot className="h-3.5 w-3.5" aria-hidden /> Evidence first. AI is interpretation, never proof.
          </div>
        </div>
      </aside>

      {/* Mobile sidebar */}
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="left" className="w-72 p-0">
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <div className="flex h-14 items-center border-b px-4">
            <Brand />
          </div>
          <div className="overflow-y-auto py-4">
            <SidebarNav companyId={companyId} onNavigate={() => setOpen(false)} />
          </div>
        </SheetContent>
      </Sheet>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="no-print sticky top-0 z-30 flex h-14 items-center gap-3 border-b bg-background/80 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/60 sm:px-6">
          <Button variant="ghost" size="icon-sm" className="lg:hidden" onClick={() => setOpen(true)} aria-label="Open navigation">
            <Menu />
          </Button>
          <div className="lg:hidden">
            <span className="sr-only">Signal Stack</span>
          </div>
          <CompanySwitcher companyId={companyId} />
          <div className="ml-auto flex items-center gap-1">
            <Button asChild variant="ghost" size="sm" className="hidden sm:inline-flex">
              <Link href="/companies/new">
                <Plus /> New company
              </Link>
            </Button>
            <ThemeToggle />
          </div>
        </header>
        <main id="main" className="print-full mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 sm:px-6 lg:px-8">
          {children}
        </main>
      </div>
    </div>
  );
}
