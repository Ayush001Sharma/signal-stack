"use client";

import { useParams } from "next/navigation";

/** Numeric company id from the /companies/[id]/... route. */
export function useCompanyId(): number {
  const params = useParams<{ id: string }>();
  return Number(params?.id);
}
