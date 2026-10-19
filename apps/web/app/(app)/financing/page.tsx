"use client";

import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { useState } from "react";
import { apiGet } from "@/lib/api";
import { Business } from "@/lib/schemas";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Select } from "@/components/ui/Select";
import { Skeleton, EmptyState, ErrorState } from "@/components/ui/States";
import { FinancingPanel } from "@/components/FinancingPanel";
import { useWorkspace } from "@/components/WorkspaceContext";

export default function FinancingPage() {
  const { businessId, setBusinessId } = useWorkspace();
  const [selectedId, setSelectedId] = useState<string | null>(businessId);

  const businesses = useQuery({
    queryKey: ["businesses"],
    queryFn: () => apiGet("/api/businesses", z.array(Business)),
  });

  const effectiveId = selectedId ?? businesses.data?.[0]?.id ?? null;

  if (businesses.isLoading) {
    return (
      <Page>
        <Skeleton className="h-8 w-1/3" />
        <Skeleton className="mt-4 h-32" />
      </Page>
    );
  }
  if (businesses.isError) {
    return (
      <Page>
        <ErrorState
          title="Could not load businesses"
          description={String(businesses.error)}
        />
      </Page>
    );
  }
  if (!businesses.data || businesses.data.length === 0) {
    return (
      <Page>
        <Card>
          <CardHeader title="Financing options" />
          <CardBody>
            <EmptyState
              title="No business yet"
              description="Create a business to see financing matches."
            />
          </CardBody>
        </Card>
      </Page>
    );
  }

  return (
    <Page
      headerRight={
        <Select
          aria-label="Select business"
          value={effectiveId ?? ""}
          onChange={(e) => {
            setSelectedId(e.target.value);
            setBusinessId(e.target.value);
          }}
        >
          {businesses.data.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name} — {b.industry}
            </option>
          ))}
        </Select>
      }
    >
      <FinancingPanel />
    </Page>
  );
}

function Page({ children, headerRight }: { children: React.ReactNode; headerRight?: React.ReactNode }) {
  return (
    <div className="px-6 py-6">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold tracking-tight">Financing options</h1>
        <div>{headerRight}</div>
      </div>
      {children}
    </div>
  );
}
