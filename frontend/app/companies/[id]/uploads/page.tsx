"use client";

import * as React from "react";
import { toast } from "sonner";
import { ChevronDown, FileSpreadsheet, FileText, Trash2, UploadCloud, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Confirm } from "@/components/shared/confirm";
import { EmptyState, ErrorBanner, ListSkeleton, PageHeader } from "@/components/shared/states";
import { SignalCard } from "@/components/signal-card";
import { useApi } from "@/hooks/use-api";
import { useCompanyId } from "@/hooks/use-company-id";
import { api, errorMessage, paths } from "@/lib/api";
import type { InternalDocument, Page, Signal } from "@/lib/types";
import { cn, fmtBytes, fmtDateTime, humanize } from "@/lib/utils";

const MAX_MB = 10;
const ACCEPT = [".csv", ".xlsx", ".pdf", ".txt"];

function validateFile(f: File): string | null {
  const ext = f.name.slice(f.name.lastIndexOf(".")).toLowerCase();
  if (!ACCEPT.includes(ext)) return `${f.name}: unsupported type. Use CSV, XLSX, PDF or TXT.`;
  if (f.size > MAX_MB * 1024 * 1024) return `${f.name}: ${fmtBytes(f.size)} exceeds the ${MAX_MB} MB limit.`;
  if (f.size === 0) return `${f.name}: file is empty.`;
  return null;
}

function DocumentCard({ doc, companyId, onDeleted }: { doc: InternalDocument; companyId: number; onDeleted: () => void }) {
  const labels = doc.insights?.labels ?? {};
  const themes = doc.insights?.themes ?? [];
  const del = async () => {
    try {
      await api.deleteDocument(companyId, doc.id);
      toast.success(`Deleted ${doc.filename}`);
      onDeleted();
    } catch (e) {
      toast.error("Could not delete document", { description: errorMessage(e) });
    }
  };
  const Icon = doc.file_type === "csv" || doc.file_type === "xlsx" ? FileSpreadsheet : FileText;
  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-3">
            <Icon className="mt-0.5 h-5 w-5 shrink-0 text-emerald-500" aria-hidden />
            <div className="min-w-0">
              <CardTitle className="truncate">{doc.filename}</CardTitle>
              <CardDescription>
                {doc.file_type.toUpperCase()} · {fmtBytes(doc.size_bytes)} · {doc.record_count} records · uploaded {fmtDateTime(doc.uploaded_at)}
              </CardDescription>
              {doc.description ? <p className="mt-1 text-sm text-muted-foreground">{doc.description}</p> : null}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <Badge tone={doc.status === "processed" ? "emerald" : doc.status === "error" ? "rose" : "amber"}>{humanize(doc.status)}</Badge>
            <Confirm title={`Delete ${doc.filename}?`} description="The file and its extracted insights are removed." confirmLabel="Delete" onConfirm={del}>
              <Button variant="ghost" size="icon-sm" aria-label={`Delete ${doc.filename}`}>
                <Trash2 />
              </Button>
            </Confirm>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {doc.error ? <p className="rounded-md bg-rose-500/10 p-2 text-xs text-rose-400">{doc.error}</p> : null}
        {Object.keys(labels).length ? (
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(labels)
              .sort((a, b) => b[1] - a[1])
              .map(([k, v]) => (
                <Badge key={k} tone="outline">
                  {humanize(k)} · {v}
                </Badge>
              ))}
            {doc.insights.unlabelled_records ? <Badge tone="slate">Unlabelled · {doc.insights.unlabelled_records}</Badge> : null}
          </div>
        ) : null}
        {themes.length ? (
          <Collapsible>
            <CollapsibleTrigger asChild>
              <Button variant="ghost" size="sm" className="group -ml-2">
                {themes.length} themes with quotes <ChevronDown className="transition-transform group-data-[state=open]:rotate-180" />
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="space-y-2">
              {themes.map((t, i) => (
                <div key={i} className="rounded-lg border p-3">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm font-medium">{t.title}</p>
                    <Badge tone="slate">{t.count}</Badge>
                  </div>
                  <ul className="mt-1.5 space-y-1">
                    {t.quotes.map((q, j) => (
                      <li key={j} className="border-l-2 border-emerald-500/40 pl-2 text-xs text-muted-foreground">
                        “{q.text}” <span className="font-mono text-[10px] text-foreground/60">({q.ref})</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </CollapsibleContent>
          </Collapsible>
        ) : doc.status === "processed" ? (
          <p className="text-xs text-muted-foreground">No recurring themes were found in this document.</p>
        ) : null}
      </CardContent>
    </Card>
  );
}

export default function UploadsPage() {
  const id = useCompanyId();
  const docs = useApi<InternalDocument[]>(paths.documents(id));
  const signals = useApi<Page<Signal>>(paths.signals(id, { category: "internal", meaningful_only: false, page_size: 20 }));
  const [files, setFiles] = React.useState<File[]>([]);
  const [description, setDescription] = React.useState("");
  const [drag, setDrag] = React.useState(false);
  const [uploading, setUploading] = React.useState(false);
  const [errs, setErrs] = React.useState<string[]>([]);
  const inputRef = React.useRef<HTMLInputElement>(null);

  const addFiles = (list: FileList | File[]) => {
    const arr = Array.from(list);
    const bad = arr.map(validateFile).filter((x): x is string => !!x);
    setErrs(bad);
    setFiles((prev) => [...prev, ...arr.filter((f) => !validateFile(f))]);
  };

  const upload = async () => {
    if (!files.length) return;
    setUploading(true);
    let ok = 0;
    for (const f of files) {
      try {
        const d = await api.uploadDocument(id, f, description.trim() || undefined);
        ok++;
        toast.success(`${d.filename} processed`, { description: `${d.record_count} records · ${d.insights?.themes?.length ?? 0} themes` });
      } catch (e) {
        toast.error(`Upload failed: ${f.name}`, { description: errorMessage(e) });
      }
    }
    setUploading(false);
    if (ok) {
      setFiles([]);
      setDescription("");
      await Promise.all([docs.mutate(), signals.mutate()]);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Internal intelligence" title="Uploads" description="Upload CRM exports, call notes, support logs or survey results. Themes and quotes become internal signals in the Monday Brief." />

      <Card>
        <CardContent className="space-y-4 p-5">
          <div
            role="button"
            tabIndex={0}
            aria-label="Upload files: drop here or press Enter to browse"
            onClick={() => inputRef.current?.click()}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                inputRef.current?.click();
              }
            }}
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              addFiles(e.dataTransfer.files);
            }}
            className={cn(
              "flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              drag ? "border-primary bg-primary/10" : "border-border hover:border-primary/50 hover:bg-muted/30",
            )}
          >
            <UploadCloud className="mb-2 h-8 w-8 text-primary" aria-hidden />
            <p className="text-sm font-medium">Drag & drop files here, or click to browse</p>
            <p className="mt-1 text-xs text-muted-foreground">CSV, XLSX, PDF or TXT · up to {MAX_MB} MB each</p>
            <input ref={inputRef} type="file" className="sr-only" multiple accept={ACCEPT.join(",")} onChange={(e) => e.target.files && addFiles(e.target.files)} tabIndex={-1} />
          </div>
          {errs.length ? (
            <div role="alert" className="rounded-md border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-500">
              {errs.map((e) => (
                <p key={e}>{e}</p>
              ))}
            </div>
          ) : null}
          {files.length ? (
            <ul className="space-y-1.5">
              {files.map((f, i) => (
                <li key={i} className="flex items-center justify-between rounded-md border px-3 py-2 text-sm">
                  <span className="truncate">
                    {f.name} <span className="text-xs text-muted-foreground">({fmtBytes(f.size)})</span>
                  </span>
                  <Button variant="ghost" size="icon-sm" onClick={() => setFiles((p) => p.filter((_, j) => j !== i))} aria-label={`Remove ${f.name}`}>
                    <X />
                  </Button>
                </li>
              ))}
            </ul>
          ) : null}
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <div className="flex-1 space-y-1.5">
              <Label htmlFor="desc">Description (optional)</Label>
              <Input id="desc" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="e.g. Q3 HubSpot deals export" />
            </div>
            <Button onClick={upload} loading={uploading} disabled={!files.length}>
              <UploadCloud /> Upload {files.length ? `${files.length} file${files.length > 1 ? "s" : ""}` : ""}
            </Button>
          </div>
        </CardContent>
      </Card>

      <section aria-labelledby="docs-h" className="space-y-3">
        <h2 id="docs-h" className="text-sm font-semibold">
          Documents
        </h2>
        {docs.error ? <ErrorBanner error={docs.error} onRetry={() => docs.mutate()} /> : null}
        {docs.isLoading ? (
          <ListSkeleton rows={2} />
        ) : !docs.data?.length ? (
          <EmptyState
            icon={FileSpreadsheet}
            title="No documents uploaded"
            description="Without internal data, section 5 of the brief stays empty. Upload a CRM export or call notes to get started."
            action={
              <Button onClick={() => inputRef.current?.click()}>
                <UploadCloud /> Choose files
              </Button>
            }
          />
        ) : (
          <div className="grid gap-4 xl:grid-cols-2">
            {docs.data.map((d) => (
              <DocumentCard key={d.id} doc={d} companyId={id} onDeleted={() => Promise.all([docs.mutate(), signals.mutate()])} />
            ))}
          </div>
        )}
      </section>

      <section aria-labelledby="isig-h" className="space-y-3">
        <h2 id="isig-h" className="text-sm font-semibold">
          Internal signals {signals.data ? <span className="text-muted-foreground">({signals.data.total})</span> : null}
        </h2>
        {signals.error ? <ErrorBanner error={signals.error} onRetry={() => signals.mutate()} /> : null}
        {signals.data && signals.data.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">No internal signals yet — they’re created automatically when a document is processed.</p>
        ) : (
          <div className="space-y-3">
            {(signals.data?.items ?? []).map((s) => (
              <SignalCard key={s.id} signal={s} companyId={id} onChanged={() => signals.mutate()} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
