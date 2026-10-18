"use client";

import { QueryClient } from "@tanstack/react-query";

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: (failureCount, error) => {
          // Never retry 4xx — those are user-fixable.
          const status = (error as { status?: number } | undefined)?.status;
          if (typeof status === "number" && status >= 400 && status < 500) return false;
          return failureCount < 2;
        },
        refetchOnWindowFocus: false,
      },
    },
  });
}
