"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AuditView } from "@/components/audit-view";
import { ErrorBanner, ListSkeleton, PageHeader } from "@/components/shared/states";
import { useApi } from "@/hooks/use-api";
import { useCompanyId } from "@/hooks/use-company-id";
import { paths } from "@/lib/api";
import type { Audit } from "@/lib/types";

export default function AuditDetailPage() {
  const id = useCompanyId();
  const { auditId } = useParams<{ auditId: string }>();
  const { data, error, isLoading, mutate } = useApi<Audit>(paths.audit(id, auditId));
  return (
    <div>
      <PageHeader
        eyebrow="Monthly Signal Stack audit"
        title={`Audit #${auditId}`}
        actions={
          <Button variant="ghost" asChild>
            <Link href={`/companies/${id}/history`}>
              <ArrowLeft /> Back to history
            </Link>
          </Button>
        }
      />
      {error ? <ErrorBanner error={error} onRetry={() => mutate()} /> : null}
      {isLoading ? <ListSkeleton rows={3} /> : data ? <AuditView audit={data} companyId={id} /> : null}
    </div>
  );
}
