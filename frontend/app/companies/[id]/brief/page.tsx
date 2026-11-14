"use client";

import { BriefPage } from "@/components/brief-page";
import { useCompanyId } from "@/hooks/use-company-id";

export default function LatestBriefPage() {
  const id = useCompanyId();
  return <BriefPage companyId={id} />;
}
