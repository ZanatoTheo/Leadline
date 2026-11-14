"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Button } from "@/components/ui/button";
import { ErrorBox, PoweredByCala, postJson } from "@/components/leadline/shared";
import { useSession } from "@/components/leadline/session";
import { ThesisView } from "@/components/leadline/thesis";
import type { InvestorThesis } from "@/lib/leadline/match-types";

export default function InvestorThesisPage() {
  const { investorName: investor } = useSession();
  const router = useRouter();
  const [thesis, setThesis] = useState<InvestorThesis | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!investor) {
      router.replace("/investor/setup");
      return;
    }
    postJson<InvestorThesis>("/api/thesis", { investor }).then(setThesis).catch((e) => setError(e.message));
  }, [investor, router]);

  return (
    <AppLayout>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Your thesis, from Cala</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            What founders are matched against. It updates as your new rounds appear in Cala.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <PoweredByCala mode={thesis?.mode} />
          <Link href="/investor/setup">
            <Button variant="outline" size="sm">Switch fund</Button>
          </Link>
        </div>
      </div>
      {error && <ErrorBox message={error} />}
      {!thesis && !error && (
        <div className="flex items-center gap-2 py-16 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Reading your rounds in Cala…
        </div>
      )}
      {thesis && <ThesisView thesis={thesis} />}
    </AppLayout>
  );
}
