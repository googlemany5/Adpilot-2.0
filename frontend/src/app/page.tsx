"use client";

import { useState, type FormEvent } from "react";

type Campaign = {
  name: string;
  platform: string;
  budget: number;
  status: string;
};

export default function Home() {
  const [page, setPage] = useState("Overview");
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [platform, setPlatform] = useState("Meta Ads");
  const [budget, setBudget] = useState("1000");
  const [campaigns, setCampaigns] = useState<Campaign[]>([
    { name: "Summer Collection", platform: "Meta Ads", budget: 2500, status: "Active" },
    { name: "Search Growth", platform: "Google Ads", budget: 1800, status: "Active" },
    { name: "New Customer Testing", platform: "Meta Ads", budget: 750, status: "Draft" },
    { name: "Brand Awareness", platform: "Google Ads", budget: 1200, status: "Active" },
  ]);

  const totalBudget = campaigns.reduce((sum, c) => sum + c.budget, 0);
  const money = (n: number) =>
    n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

  function createCampaign(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const amount = Number(budget);
    if (!name.trim() || !Number.isFinite(amount) || amount <= 0) return;

    setCampaigns((old) => [
      ...old,
      { name: name.trim(), platform, budget: amount, status: "Draft" },
    ]);
    setName("");
    setBudget("1000");
    setShowForm(false);
    setPage("Campaigns");
  }

  const nav = ["Overview", "Campaigns", "Experiments", "AI Optimizer", "Connections", "Settings"];

  return (
    <main className="min-h-screen bg-[#080d18] text-slate-100 md:flex">
      <aside className="border-b border-white/10 bg-[#0b1120] p-5 md:min-h-screen md:w-64 md:border-b-0 md:border-r">
        <h1 className="mb-1 text-2xl font-bold">
          <span className="text-blue-400">A</span>dPilot
        </h1>
        <p className="mb-6 text-xs tracking-widest text-slate-500">AI ADVERTISING</p>
        <nav className="flex gap-2 overflow-x-auto md:flex-col">
          {nav.map((item) => (
            <button
              key={item}
              onClick={() => setPage(item)}
              className={`whitespace-nowrap rounded-xl px-4 py-3 text-left text-sm ${
                page === item
                  ? "bg-blue-500/15 text-blue-300"
                  : "text-slate-400 hover:bg-white/5"
              }`}
            >
              {item}
            </button>
          ))}
        </nav>
        <div className="mt-8 rounded-xl border border-blue-400/20 p-4">
          <p className="font-semibold">AI Optimizer</p>
          <p className="mt-2 text-sm text-slate-400">
            Optimization recommendations will appear here as the backend is connected.
          </p>
        </div>
      </aside>

      <section className="min-w-0 flex-1 p-5 sm:p-8">
        <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-sm text-slate-500">Workspace / {page}</p>
            <h2 className="mt-1 text-3xl font-bold">{page}</h2>
          </div>
          <button
            onClick={() => setShowForm(true)}
            className="rounded-xl bg-blue-500 px-5 py-3 text-sm font-semibold hover:bg-blue-400"
          >
            + New campaign
          </button>
        </header>

        <div className="mb-6 rounded-xl border border-amber-400/20 bg-amber-400/5 p-3 text-sm text-amber-200">
          Demo mode — displayed performance figures are examples, not live ad account data.
        </div>

        <div className="mb-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[
            ["Campaign budget", money(totalBudget)],
            ["Demo spend", "$2,840"],
            ["Demo revenue", "$8,520"],
            ["Demo ROAS", "3.0x"],
          ].map(([label, value]) => (
            <div key={label} className="rounded-2xl border border-white/10 bg-[#0d1424] p-5">
              <p className="text-sm text-slate-400">{label}</p>
              <p className="mt-3 text-3xl font-bold">{value}</p>
              <p className="mt-2 text-xs text-slate-500">
                {label === "Campaign budget" ? "Combined campaign budgets" : "Illustrative data"}
              </p>
            </div>
          ))}
        </div>

        <div className="mb-6 rounded-2xl border border-white/10 bg-[#0d1424] p-5">
          <h3 className="mb-1 text-lg font-semibold">Campaigns</h3>
          <p className="mb-5 text-sm text-slate-400">
            Manage your advertising campaigns and planned budgets.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-white/10 text-slate-500">
                <tr>
                  <th className="p-3">Campaign</th>
                  <th className="p-3">Platform</th>
                  <th className="p-3">Budget</th>
                  <th className="p-3">Status</th>
                </tr>
              </thead>
              <tbody>
                {campaigns.map((c, i) => (
                  <tr key={`${c.name}-${i}`} className="border-b border-white/5">
                    <td className="p-3 font-medium">{c.name}</td>
                    <td className="p-3 text-slate-400">{c.platform}</td>
                    <td className="p-3">{money(c.budget)}</td>
                    <td className="p-3">
                      <span className={`rounded-full px-2 py-1 text-xs ${
                        c.status === "Active"
                          ? "bg-emerald-400/10 text-emerald-300"
                          : "bg-slate-500/20 text-slate-300"
                      }`}>
                        {c.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="rounded-2xl border border-blue-400/20 bg-blue-500/5 p-5">
          <h3 className="font-semibold">Your next optimization step</h3>
          <p className="mt-2 text-sm leading-6 text-slate-400">
            Connect your advertising accounts and collect campaign results before making
            AI-driven budget recommendations. No real ad spend is triggered by this dashboard.
          </p>
        </div>
      </section>

      {showForm && (
        <div className="fixed inset-0 z-10 flex items-center justify-center bg-black/70 p-4">
          <form
            onSubmit={createCampaign}
            className="w-full max-w-md rounded-2xl border border-white/10 bg-[#111827] p-6"
          >
            <h2 className="mb-5 text-xl font-bold">Create campaign</h2>
            <label className="mb-2 block text-sm text-slate-300">Campaign name</label>
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Fall promotion"
              className="mb-4 w-full rounded-lg border border-white/10 bg-[#080d18] p-3 outline-none focus:border-blue-400"
            />
            <label className="mb-2 block text-sm text-slate-300">Advertising platform</label>
            <select
              value={platform}
              onChange={(e) => setPlatform(e.target.value)}
              className="mb-4 w-full rounded-lg border border-white/10 bg-[#080d18] p-3"
            >
              <option>Meta Ads</option>
              <option>Google Ads</option>
            </select>
            <label className="mb-2 block text-sm text-slate-300">Planned budget ($)</label>
            <input
              required
              type="number"
              min="1"
              step="0.01"
              value={budget}
              onChange={(e) => setBudget(e.target.value)}
              className="mb-6 w-full rounded-lg border border-white/10 bg-[#080d18] p-3"
            />
            <p className="mb-4 text-xs text-slate-500">
              New campaigns start as drafts. This form does not spend money or create a live ad.
            </p>
            <div className="flex gap-3">
              <button type="button" onClick={() => setShowForm(false)}
                className="flex-1 rounded-lg border border-white/10 p-3 text-sm">
                Cancel
              </button>
              <button type="submit"
                className="flex-1 rounded-lg bg-blue-500 p-3 text-sm font-semibold hover:bg-blue-400">
                Create draft
              </button>
            </div>
          </form>
        </div>
      )}
    </main>
  );
}
