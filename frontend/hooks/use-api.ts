"use client";

import useSWR, { type SWRConfiguration } from "swr";
import { swrFetcher } from "@/lib/api";

/** Typed SWR hook for GET endpoints. Pass `null` to skip fetching. */
export function useApi<T>(path: string | null, config?: SWRConfiguration<T>) {
  return useSWR<T>(path, swrFetcher<T>, { revalidateOnFocus: true, ...config });
}
