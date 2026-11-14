"use client";

import { useParams } from "next/navigation";
import { BriefPage } from "@/components/brief-page";
import { useCompanyId } from "@/hooks/use-company-id";

export default function BriefDetailPage() {
  const id = useCompanyId();
  const { briefId } = useParams<{ briefId: string }>();
  return <BriefPage companyId={id} briefId={Number(briefId)} />;
}
