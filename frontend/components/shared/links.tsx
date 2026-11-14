import Link from "next/link";
import { ExternalLink as ExternalIcon, FileText } from "lucide-react";
import { cn, hostOf, isHttp } from "@/lib/utils";

/** External evidence link (new tab). internal:// links route to the uploads page. */
export function EvidenceLink({ url, companyId, children, className }: { url: string | null | undefined; companyId: number; children?: React.ReactNode; className?: string }) {
  if (!url) return null;
  if (url.startsWith("internal://")) {
    return (
      <Link href={`/companies/${companyId}/uploads`} className={cn("inline-flex items-center gap-1 text-primary hover:underline", className)}>
        <FileText className="h-3 w-3" aria-hidden />
        {children ?? "Internal document"}
      </Link>
    );
  }
  if (!isHttp(url)) return <span className={cn("text-muted-foreground", className)}>{children ?? url}</span>;
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" className={cn("inline-flex min-w-0 items-center gap-1 text-primary hover:underline", className)}>
      <span className="truncate">{children ?? hostOf(url)}</span>
      <ExternalIcon className="h-3 w-3 shrink-0" aria-hidden />
      <span className="sr-only">(opens in new tab)</span>
    </a>
  );
}
