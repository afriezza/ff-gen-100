// api/gen.js - honest-fast: 1x Garena guest-grant 2.5s, NO mock. blocked -> success:false
import crypto from "crypto";
async function gw(path, body, ms) {
  const c = new AbortController();
  const t = setTimeout(() => c.abort(), ms);
  try {
    const r = await fetch("https://100067.connect.garena.com" + path, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded", "User-Agent": "GarenaMSDK/4.0.19 (Android 12; SM-A515F)" },
      body: new URLSearchParams(body).toString(), signal: c.signal });
    const j = await r.json().catch(() => ({}));
    return { ok: r.status === 200, j };
  } catch (e) { return { ok: false, j: {} }; } finally { clearTimeout(t); }
}
export default async function handler(req, res) {
  const t0 = Date.now();
  res.setHeader("Access-Control-Allow-Origin", "*");
  const q = req.query || {};
  const dev = crypto.randomBytes(8).toString("hex");
  const g = await gw("/oauth/guest/token/grant", { client_id: "100067", grant_type: "guest", device_id: dev }, 2500);
  const tok = g.j && (g.j.access_token || g.j.token);
  if (g.ok && tok) {
    res.status(200).json({ success: true, slot: (q.slot || null), mode: "live", ms: Date.now() - t0,
      accounts: [{ uid: String(g.j.open_id || dev), token: tok }] });
  } else {
    res.status(200).json({ success: false, slot: (q.slot || null), mode: "live", ms: Date.now() - t0,
      reason: "garena-blocked", accounts: [] });
  }
}
