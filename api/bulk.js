// api/bulk.js - fan-out ke /api/gen?slot (dynamics dihapus, limit 12 fungsi)
export default async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  const q = req.query || {};
  const total = Math.min(parseInt(q.count || "5") || 5, 20);
  const base = "https://" + req.headers.host;
  const jobs = [];
  for (let i = 1; i <= total; i++) {
    jobs.push(fetch(base + "/api/gen?name=" + encodeURIComponent(q.name || "Sam") + "&count=1&region=" + (q.region || "ID") + "&slot=" + i)
      .then((r) => r.json()).catch(() => ({ accounts: [] })));
  }
  const all = await Promise.all(jobs);
  const accounts = all.flatMap((x) => x.accounts || []);
  res.status(200).json({ success: accounts.length > 0, mode: "live",
    total_requested: total, total_created: accounts.length, accounts });
}
