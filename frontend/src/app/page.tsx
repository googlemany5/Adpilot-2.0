"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import PerformanceChart from "./components/PerformanceChart";
import FeatureWorkspace from "./components/FeatureWorkspace";

type Campaign = {
  id: number;
  name: string;
  monthly_budget: number;
  discovery_budget: number;
  country?: string | null;
  status: string;
};

type CampaignAnalytics = {
  campaign_id: number;
  experiment_count: number;
  experiment_spend: number;
  experiment_revenue: number;
  experiment_roas: number | null;
  clicks: number;
  conversions: number;
  conversion_rate: number | null;
  data_note: string;
};

type User = {
  id: number;
  email: string;
  first_name?: string | null;
  last_name?: string | null;
  is_admin: boolean;
};

const API = "/backend-api";

function money(value: number) {
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  });
}

export default function Home() {
  const [token, setToken] = useState("");
  const [user, setUser] = useState<User | null>(null);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [analyticsByCampaign, setAnalyticsByCampaign] =
    useState<Record<number, CampaignAnalytics>>({});
  const [page, setPage] = useState("Overview");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [monthlyBudget, setMonthlyBudget] = useState("1000");
  const [discoveryBudget, setDiscoveryBudget] = useState("100");
  const [country, setCountry] = useState("United States");

  const loadDashboard = useCallback(async (authToken: string) => {
    setLoading(true);
    setError("");

    try {
      const headers = { Authorization: `Bearer ${authToken}` };

      const [userResponse, campaignResponse] = await Promise.all([
        fetch(`${API}/auth/me`, { headers }),
        fetch(`${API}/campaigns`, { headers }),
      ]);

      if (userResponse.status === 401 || campaignResponse.status === 401) {
        localStorage.removeItem("adpilot_token");
        setToken("");
        setUser(null);
        setCampaigns([]);
        setAnalyticsByCampaign({});
        setError("Your session expired. Please sign in again.");
        return;
      }

      if (!userResponse.ok || !campaignResponse.ok) {
        throw new Error("Couldn't load your account. Check that the backend is running.");
      }

      const userData: User = await userResponse.json();
      const campaignData: Campaign[] = await campaignResponse.json();

      const analyticsResults = await Promise.all(
        campaignData.map(async (campaign) => {
          try {
            const response = await fetch(
              `${API}/campaigns/${campaign.id}/analytics`,
              { headers }
            );
            if (!response.ok) return null;
            return (await response.json()) as CampaignAnalytics;
          } catch {
            return null;
          }
        })
      );

      const analyticsMap: Record<number, CampaignAnalytics> = {};
      for (const result of analyticsResults) {
        if (result) analyticsMap[result.campaign_id] = result;
      }

      setUser(userData);
      setCampaigns(campaignData);
      setAnalyticsByCampaign(analyticsMap);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const savedToken = localStorage.getItem("adpilot_token");

    if (savedToken) {
      // Restore the saved session from localStorage on initial page load.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setToken(savedToken);
      void loadDashboard(savedToken);
    } else {
      setLoading(false);
    }
  }, [loadDashboard]);

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");

    try {
      const body = new URLSearchParams();
      body.set("username", email.trim());
      body.set("password", password);

      const response = await fetch(`${API}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body,
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          typeof data.detail === "string" ? data.detail : "Sign-in failed."
        );
      }

      localStorage.setItem("adpilot_token", data.access_token);
      setToken(data.access_token);
      setPassword("");
      await loadDashboard(data.access_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed.");
      setLoading(false);
    }
  }

  async function createCampaign(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const monthly = Number(monthlyBudget);
    const discovery = Number(discoveryBudget);

    if (!name.trim() || !Number.isFinite(monthly) || monthly <= 0 ||
        !Number.isFinite(discovery) || discovery < 0) {
      setError("Enter a campaign name and valid budgets.");
      return;
    }

    setSaving(true);
    setError("");

    try {
      const response = await fetch(`${API}/campaigns`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: name.trim(),
          monthly_budget: monthly,
          discovery_budget: discovery,
          country: country.trim() || null,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          typeof data.detail === "string" ? data.detail : "Couldn't create campaign."
        );
      }

      setCampaigns((previous) => [...previous, data]);
      setName("");
      setMonthlyBudget("1000");
      setDiscoveryBudget("100");
      setShowForm(false);
      setPage("Campaigns");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't create campaign.");
    } finally {
      setSaving(false);
    }
  }

  function signOut() {
    localStorage.removeItem("adpilot_token");
    setToken("");
    setUser(null);
    setCampaigns([]);
    setAnalyticsByCampaign({});
    setError("");
  }

  const totalMonthlyBudget = campaigns.reduce(
    (sum, campaign) => sum + campaign.monthly_budget, 0
  );
  const totalDiscoveryBudget = campaigns.reduce(
    (sum, campaign) => sum + campaign.discovery_budget, 0
  );
  const analytics = Object.values(analyticsByCampaign);
  const experimentCount = analytics.reduce(
    (sum, item) => sum + item.experiment_count, 0
  );
  const experimentSpend = analytics.reduce(
    (sum, item) => sum + item.experiment_spend, 0
  );
  const experimentRevenue = analytics.reduce(
    (sum, item) => sum + item.experiment_revenue, 0
  );
  const experimentClicks = analytics.reduce(
    (sum, item) => sum + item.clicks, 0
  );
  const experimentConversions = analytics.reduce(
    (sum, item) => sum + item.conversions, 0
  );
  const experimentRoas = experimentSpend > 0
    ? experimentRevenue / experimentSpend
    : null;

  const performanceItems = campaigns.map((campaign) => {
    const item = analyticsByCampaign[campaign.id];
    return {
      campaign_id: campaign.id,
      name: campaign.name,
      spend: item?.experiment_spend ?? 0,
      revenue: item?.experiment_revenue ?? 0,
    };
  });

  const activeCount = campaigns.filter(
    (campaign) => campaign.status.toLowerCase() === "active"
  ).length;
  const draftCount = campaigns.filter(
    (campaign) => campaign.status.toLowerCase() === "draft"
  ).length;

  if (loading && !user) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#080d18] text-slate-200">
        Loading AdPilot...
      </main>
    );
  }

  if (!token || !user) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#080d18] px-4 text-slate-100">
        <form onSubmit={signIn} className="w-full max-w-md rounded-2xl border border-white/10 bg-[#0d1424] p-8">
          <h1 className="text-3xl font-bold"><span className="text-blue-400">A</span>dPilot</h1>
          <p className="mb-7 mt-2 text-sm text-slate-400">Sign in to your advertising workspace.</p>



        {error && <p role="alert" className="mb-4 rounded-lg bg-red-500/10 p-3 text-sm text-red-300">{error}</p>}

          <label className="mb-2 block text-sm">Email</label>
          <input
            required type="email" autoComplete="email" value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="mb-4 w-full rounded-lg border border-white/10 bg-[#080d18] p-3 outline-none focus:border-blue-400"
          />

          <label className="mb-2 block text-sm">Password</label>
          <input
            required type="password" autoComplete="current-password" value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="mb-6 w-full rounded-lg border border-white/10 bg-[#080d18] p-3 outline-none focus:border-blue-400"
          />

          <button disabled={loading} className="w-full rounded-xl bg-blue-500 p-3 font-semibold hover:bg-blue-400 disabled:opacity-50">
            {loading ? "Signing in..." : "Sign in"}
          </button>
          <p className="mt-4 text-xs leading-5 text-slate-500">
            Use an existing AdPilot account. This page does not create accounts.
          </p>
        </form>
      </main>
    );
  }

  const nav = ["Overview", "Campaigns", "Experiments", "AI Optimizer", "Connections", "Settings", ...(user?.is_admin ? ["Admin"] : [])];

  return (
    <main className="min-h-screen bg-[#080d18] text-slate-100 md:flex">
      <aside className="border-b border-white/10 bg-gradient-to-b from-[#101b30] to-[#0b1120] p-5 md:min-h-screen md:w-64 md:shrink-0 md:border-b-0 md:border-r md:border-white/10">
        <h1 className="mb-1 text-2xl font-bold"><span className="text-blue-400">A</span>dPilot</h1>
        <p className="mb-6 text-xs tracking-widest text-slate-500">AI ADVERTISING</p>
        <nav className="flex gap-2 overflow-x-auto md:flex-col">
          {nav.map((item) => (
            <button key={item} onClick={() => setPage(item)}
              className={`whitespace-nowrap rounded-xl border px-4 py-3 text-left text-sm transition duration-200 ${page === item ? "border-blue-400/20 bg-gradient-to-r from-blue-500/20 to-blue-500/5 font-semibold text-blue-200 shadow-sm shadow-blue-950/20" : "border-transparent text-slate-400 hover:border-white/5 hover:bg-white/[0.04] hover:text-slate-100"}` }>
              {item}
            </button>
          ))}
        </nav>
        <div className="mt-8 rounded-xl border border-white/10 p-4">
          <p className="text-sm font-semibold">Signed in</p>
          <p className="mt-1 break-all text-xs text-slate-400">{user.email}</p>
          <button onClick={signOut} className="mt-4 text-sm text-slate-400 hover:text-white">Sign out</button>
        </div>
      </aside>

      <section className="min-w-0 flex-1 bg-[radial-gradient(ellipse_at_top,rgba(37,99,235,0.08),transparent_55%)] p-5 sm:p-8 lg:p-10">
        <header className="mb-8 flex flex-wrap items-center justify-between gap-4 border-b border-white/[0.07] pb-6">
          <div>
            <p className="text-sm text-slate-500">Workspace / {page}</p>
            <h2 className="mt-1 text-3xl font-bold">{page}</h2>
          </div>
          <button onClick={() => { setError(""); setShowForm(true); }}
            className="rounded-xl bg-blue-500 px-5 py-3 text-sm font-semibold hover:bg-blue-400">
            + New campaign
          </button>
        </header>

{page === "Overview" && (
          <section className="relative mb-8 overflow-hidden rounded-3xl border border-blue-400/20 bg-gradient-to-br from-[#172b4b] via-[#101c32] to-[#0c1322] p-6 shadow-2xl shadow-blue-950/20 sm:p-8">
            <div className="pointer-events-none absolute -right-16 -top-24 h-64 w-64 rounded-full bg-blue-500/10 blur-3xl" />
            <div className="pointer-events-none absolute -bottom-20 right-1/3 h-40 w-40 rounded-full bg-indigo-500/10 blur-3xl" />
            <div className="relative">
              <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-blue-300/20 bg-blue-400/10 px-3 py-1.5 text-xs font-medium tracking-wide text-blue-200">
                <span className="h-2 w-2 rounded-full bg-blue-400" />
                ADPILOT WORKSPACE
              </div>
              <h3 className="max-w-2xl text-2xl font-bold tracking-tight text-white sm:text-3xl">
                {user.first_name ? `Welcome back, ${user.first_name}` : "Your advertising command center"}
              </h3>
              <p className="mt-3 max-w-xl text-sm leading-6 text-slate-300 sm:text-base">
                Keep your campaigns organized, understand your planned budgets, and review recorded experiment results from one place.
              </p>
              <div className="mt-7 flex flex-wrap gap-3">
                <button onClick={() => { setError(""); setShowForm(true); }} className="rounded-xl bg-blue-500 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-blue-950/30 transition hover:bg-blue-400">
                  + Create campaign
                </button>
                <button onClick={() => setPage("Campaigns")} className="rounded-xl border border-white/15 bg-white/[0.04] px-5 py-3 text-sm font-medium text-slate-200 transition hover:bg-white/[0.08]">
                  View campaigns <span aria-hidden="true">→</span>
                </button>
              </div>
              <div className="mt-8 grid max-w-3xl gap-3 border-t border-white/10 pt-5 sm:grid-cols-3">
                <div>
                  <p className="text-xs uppercase tracking-wider text-slate-400">Total campaigns</p>
                  <p className="mt-1 text-2xl font-semibold text-white">{campaigns.length}</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wider text-slate-400">Active campaigns</p>
                  <p className="mt-1 text-2xl font-semibold text-emerald-300">{activeCount}</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wider text-slate-400">Planned monthly budget</p>
                  <p className="mt-1 text-2xl font-semibold text-white">{money(totalMonthlyBudget)}</p>
                </div>
              </div>
            </div>
          </section>
        )}

        {error && <p role="alert" className="mb-5 rounded-xl border border-red-400/20 bg-red-400/10 p-4 text-sm text-red-200">{error}</p>}

        <div className="mb-6 rounded-xl border border-emerald-400/20 bg-emerald-400/[0.06] p-4 text-sm leading-6 text-emerald-200 shadow-sm shadow-emerald-950/10">
          Connected to your AdPilot backend. Campaign figures below come from your account database. Live ad execution is not enabled.
        </div>

        {page === "Overview" || page === "Campaigns" ? (
          <>
            <div className="mb-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
              {[
                ["Monthly budget", money(totalMonthlyBudget)],
                ["Discovery budget", money(totalDiscoveryBudget)],
                ["Total campaigns", String(campaigns.length)],
                ["Active campaigns", String(activeCount)],
                ["Draft campaigns", String(draftCount)],
              ].map(([label, value]) => (
                <div key={label} className="group rounded-2xl border border-blue-400/15 bg-gradient-to-br from-[#14223b] via-[#101a2d] to-[#0d1424] p-5 shadow-lg shadow-black/20 transition duration-200 hover:-translate-y-1 hover:border-blue-400/40 hover:shadow-blue-950/30">
                  <p className="text-sm text-slate-400">{label}</p>
                  <p className="mt-3 text-3xl font-bold">{value}</p>
                  <p className="mt-2 text-xs text-slate-500">From your account</p>
                </div>
              ))}
            </div>

            <div className="mb-6 rounded-2xl border border-white/[0.09] bg-gradient-to-br from-[#111b2e] to-[#0d1424] p-5 shadow-xl shadow-black/10 sm:p-6">
              <h3 className="mb-1 text-lg font-semibold">Planned monthly budget allocation</h3>
              <p className="mb-5 text-sm text-slate-400">
                Each campaign&apos;s share of your combined planned monthly budgets. This is not actual ad spend.
              </p>
              {campaigns.length === 0 ? (
                <p className="text-sm text-slate-500">Create a campaign to see its budget allocation.</p>
              ) : (
                <div className="space-y-5">
                  {campaigns.map((campaign) => {
                    const share = totalMonthlyBudget > 0
                      ? Math.max(0, (campaign.monthly_budget / totalMonthlyBudget) * 100)
                      : 0;

                    return (
                      <div key={campaign.id}>
                        <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-sm">
                          <span className="font-medium">{campaign.name}</span>
                          <span className="text-slate-400">
                            {money(campaign.monthly_budget)} · {share.toFixed(1)}%
                          </span>
                        </div>
                        <div
                          className="h-2 overflow-hidden rounded-full bg-white/10"
                          role="progressbar"
                          aria-label={`${campaign.name} share of planned monthly budget`}
                          aria-valuemin={0}
                          aria-valuemax={100}
                          aria-valuenow={Number(share.toFixed(1))}
                        >
                          <div
                            className="h-full rounded-full bg-blue-400"
                            style={{ width: `${Math.min(100, share)}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {page === "Overview" && (
              <section className="mb-6 rounded-2xl border border-white/[0.09] bg-gradient-to-br from-[#111b2e] to-[#0d1424] p-5 shadow-xl shadow-black/10 sm:p-6">
                <h3 className="text-lg font-semibold">Experiment analytics</h3>
                <p className="mb-4 mt-1 text-sm text-slate-400">
                  Totals from saved experiment records, not independently verified
                  platform-wide advertising results.
                </p>

                  <PerformanceChart items={performanceItems} />

                {experimentCount === 0 ? (
                  <p className="rounded-lg bg-white/5 p-4 text-sm text-slate-400">
                    No saved experiment results are available yet. Analytics will
                    appear here after your experiments have recorded results.
                  </p>
                ) : (
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                    <div className="rounded-xl bg-white/5 p-4">
                      <p className="text-sm text-slate-400">Experiment spend</p>
                      <p className="mt-2 text-2xl font-semibold">
                        {money(experimentSpend)}
                      </p>
                    </div>
                    <div className="rounded-xl bg-white/5 p-4">
                      <p className="text-sm text-slate-400">Recorded revenue</p>
                      <p className="mt-2 text-2xl font-semibold">
                        {money(experimentRevenue)}
                      </p>
                    </div>
                    <div className="rounded-xl bg-white/5 p-4">
                      <p className="text-sm text-slate-400">Experiment ROAS</p>
                      <p className="mt-2 text-2xl font-semibold">
                        {experimentRoas === null
                          ? "—"
                          : `${experimentRoas.toFixed(2)}x`}
                      </p>
                    </div>
                    <div className="rounded-xl bg-white/5 p-4">
                      <p className="text-sm text-slate-400">Conversions / clicks</p>
                      <p className="mt-2 text-2xl font-semibold">
                        {experimentConversions.toLocaleString()} /{" "}
                        {experimentClicks.toLocaleString()}
                      </p>
                    </div>
                  </div>
                )}
              </section>
            )}

            <div className="mb-6 rounded-2xl border border-white/[0.09] bg-gradient-to-br from-[#111b2e] to-[#0d1424] p-5 shadow-xl shadow-black/10 sm:p-6">
              <h3 className="mb-1 text-lg font-semibold">Your campaigns</h3>
              <p className="mb-5 text-sm text-slate-400">Saved campaigns and their planned budgets.</p>
              {campaigns.length === 0 ? (
                <div className="rounded-xl border border-dashed border-white/15 p-8 text-center">
                  <p className="font-medium">No campaigns yet</p>
                  <p className="mt-2 text-sm text-slate-400">Create your first campaign to get started.</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="border-b border-white/10 bg-white/[0.02] text-xs uppercase tracking-wider text-slate-400">
                      <tr>
                        <th className="p-3">Campaign</th>
                        <th className="p-3">Country</th>
                        <th className="p-3">Monthly budget</th>
                        <th className="p-3">Discovery budget</th>
                        <th className="p-3">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {campaigns.map((campaign) => (
                        <tr key={campaign.id} className="border-b border-white/5 transition-colors hover:bg-white/[0.025]">
                          <td className="p-3 font-medium">{campaign.name}</td>
                          <td className="p-3 text-slate-400">{campaign.country || "Not set"}</td>
                          <td className="p-3">{money(campaign.monthly_budget)}</td>
                          <td className="p-3">{money(campaign.discovery_budget)}</td>
                          <td className="p-3">
                            <span
                              className={`rounded-full px-2 py-1 text-xs ${
                                campaign.status.toLowerCase() === "active"
                                  ? "bg-emerald-400/15 text-emerald-300"
                                  : campaign.status.toLowerCase() === "draft"
                                    ? "bg-amber-400/15 text-amber-300"
                                    : "bg-slate-500/20 text-slate-300"
                              }`}
                            >
                              {campaign.status || "Unknown"}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <button onClick={() => void loadDashboard(token)} className="mt-4 rounded-lg border border-white/10 px-4 py-2 text-sm hover:bg-white/5">
                Refresh campaigns
              </button>
            </div>
          </>
        ) : (
          <FeatureWorkspace
            page={page}
            campaigns={campaigns}
            isAdmin={Boolean(user?.is_admin)}
          />
        )}
      </section>

      {showForm && (
        <div className="fixed inset-0 z-10 flex items-center justify-center overflow-y-auto bg-black/70 p-4">
          <form onSubmit={createCampaign} className="my-6 w-full max-w-md rounded-2xl border border-white/10 bg-[#111827] p-6">
            <h2 className="mb-5 text-xl font-bold">Create campaign</h2>

            <label className="mb-2 block text-sm text-slate-300">Campaign name</label>
            <input required value={name} onChange={(event) => setName(event.target.value)}
              placeholder="e.g. Fall promotion"
              className="mb-4 w-full rounded-lg border border-white/10 bg-[#080d18] p-3 outline-none focus:border-blue-400" />

            <label className="mb-2 block text-sm text-slate-300">Monthly budget ($)</label>
            <input required type="number" min="0.01" step="0.01" value={monthlyBudget}
              onChange={(event) => setMonthlyBudget(event.target.value)}
              className="mb-4 w-full rounded-lg border border-white/10 bg-[#080d18] p-3" />

            <label className="mb-2 block text-sm text-slate-300">Discovery budget ($)</label>
            <input required type="number" min="0" step="0.01" value={discoveryBudget}
              onChange={(event) => setDiscoveryBudget(event.target.value)}
              className="mb-4 w-full rounded-lg border border-white/10 bg-[#080d18] p-3" />

            <label className="mb-2 block text-sm text-slate-300">Target country</label>
            <input value={country} onChange={(event) => setCountry(event.target.value)}
              placeholder="e.g. United States"
              className="mb-5 w-full rounded-lg border border-white/10 bg-[#080d18] p-3" />

            <p className="mb-4 text-xs leading-5 text-slate-500">
              New campaigns start as drafts. Creating one does not launch ads or spend money.
            </p>

            <div className="flex gap-3">
              <button type="button" onClick={() => setShowForm(false)}
                className="flex-1 rounded-lg border border-white/10 p-3 text-sm">Cancel</button>
              <button type="submit" disabled={saving}
                className="flex-1 rounded-lg bg-blue-500 p-3 text-sm font-semibold hover:bg-blue-400 disabled:opacity-50">
                {saving ? "Saving..." : "Create draft"}
              </button>
            </div>
          </form>
        </div>
      )}
    </main>
  );
}
