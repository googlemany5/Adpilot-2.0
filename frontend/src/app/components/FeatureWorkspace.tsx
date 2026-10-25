"use client";

import { useEffect, useState } from "react";

type Campaign = {
  id: number;
  name: string;
  monthly_budget: number;
  discovery_budget: number;
  status: string;
};

type Props = {
  page: string;
  campaigns: Campaign[];
  isAdmin: boolean;
};

const API = "/backend-api";

const details: Record<string, string> = {
  Experiments: "Saved experiments for your campaigns.",
  "AI Optimizer": "Optimization recommendations from the AdPilot backend.",
  Connections: "Advertising platform connection records and platform status.",
  Settings: "Your current subscription information.",
  Admin: "Administrative information for authorized administrators.",
};

export default function FeatureWorkspace({ page, campaigns, isAdmin }: Props) {
  const [data, setData] = useState<unknown>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError("");
      setData(null);

      const token = localStorage.getItem("adpilot_token");
      if (!token) {
        setError("Your session is missing. Please sign in again.");
        setLoading(false);
        return;
      }

      async function get(path: string) {
        const response = await fetch(`${API}${path}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const body = await response.text();
        let result: unknown;
        try {
          result = body ? JSON.parse(body) : null;
        } catch {
          result = body;
        }
        if (!response.ok) {
          const detail =
            typeof result === "object" && result !== null && "detail" in result
              ? String((result as { detail: unknown }).detail)
              : `Request failed (${response.status})`;
          throw new Error(detail);
        }
        return result;
      }

      try {
        let result: unknown;

        if (page === "Experiments") {
          result = await Promise.all(campaigns.map(async (campaign) => ({
            campaign: campaign.name,
            experiments: await get(`/campaigns/${campaign.id}/experiments`),
          })));
        } else if (page === "AI Optimizer") {
          result = await Promise.all(campaigns.map(async (campaign) => {
            try {
              return {
                campaign: campaign.name,
                optimization: await get(`/campaigns/${campaign.id}/optimization`),
              };
            } catch (e) {
              return {
                campaign: campaign.name,
                error: e instanceof Error ? e.message : "Could not load recommendations.",
              };
            }
          }));
        } else if (page === "Connections") {
          const values = await Promise.allSettled([
            get("/platform-connections"),
            get("/platforms/status"),
          ]);
          result = {
            connections: values[0].status === "fulfilled" ? values[0].value : "Unavailable or access denied",
            platform_status: values[1].status === "fulfilled" ? values[1].value : "Unavailable or access denied",
          };
        } else if (page === "Settings") {
          result = await get("/subscription");
        } else if (page === "Admin") {
          if (!isAdmin) throw new Error("Administrator access is required.");
          const values = await Promise.allSettled([
            get("/admin/overview"),
            get("/admin/users"),
            get("/admin/discounts"),
          ]);
          result = {
            overview: values[0].status === "fulfilled" ? values[0].value : "Unavailable or access denied",
            users: values[1].status === "fulfilled" ? values[1].value : "Unavailable or access denied",
            discounts: values[2].status === "fulfilled" ? values[2].value : "Unavailable or access denied",
          };
        }

        if (!cancelled) setData(result ?? { message: "No data returned." });
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not load this page.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => { cancelled = true; };
  }, [page, campaigns, isAdmin, refresh]);

  return (
    <section className="space-y-6">
      <div className="rounded-2xl border border-white/[0.09] bg-gradient-to-br from-[#111b2e] to-[#0d1424] p-6 shadow-xl shadow-black/10">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-blue-300">ADPILOT WORKSPACE</p>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold text-white">{page}</h2>
            <p className="mt-2 text-sm leading-6 text-slate-400">{details[page] ?? "Account workspace"}</p>
          </div>
          <button type="button" onClick={() => setRefresh((v) => v + 1)}
            className="rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm hover:bg-white/10">
            Refresh data
          </button>
        </div>
      </div>

      {page === "AI Optimizer" && (
        <div className="rounded-xl border border-amber-400/20 bg-amber-400/[0.06] p-4 text-sm leading-6 text-amber-100">
          Recommendations are for review. Viewing this page does not launch ads or authorize spending.
        </div>
      )}

      {loading && <div className="rounded-xl border border-white/10 bg-[#0d1424] p-5 text-sm text-slate-400">Loading account data…</div>}

      {!loading && error && (
        <div role="alert" className="rounded-xl border border-rose-400/20 bg-rose-400/[0.06] p-5">
          <h3 className="font-semibold text-rose-200">Unable to load this section</h3>
          <p className="mt-2 break-words text-sm text-slate-300">{error}</p>
          <p className="mt-2 text-xs text-slate-500">Check that the backend is running and your account has permission.</p>
        </div>
      )}

      {!loading && !error && (
        <div className="rounded-2xl border border-white/[0.09] bg-gradient-to-br from-[#111b2e] to-[#0d1424] p-5 sm:p-6">
          <h3 className="mb-4 font-semibold text-white">Backend data</h3>
          <pre className="max-h-[560px] overflow-auto whitespace-pre-wrap break-words rounded-xl border border-white/[0.06] bg-[#080d18] p-4 text-xs leading-6 text-slate-300">
            {JSON.stringify(data, null, 2)}
          </pre>
        </div>
      )}
    </section>
  );
}
