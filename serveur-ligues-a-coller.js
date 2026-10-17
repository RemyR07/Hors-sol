// Fichier à coller tel quel dans le Worker Cloudflare (généré par build.py, ne pas modifier à la main).
// ============================================================
//  LIGUES · noyau commun (serveur Cloudflare + maquette de test)
//  Calcule les classements à partir des membres et des scores.
// ============================================================
const LG_GAMES = ["fourchette","trio","rangement","drop","intrus","rayon"];
const LG_MAX_MEMBERS = 30;   // joueurs par ligue
const LG_MAX_LEAGUES = 10;   // ligues par joueur
const LG_KEEP_DAYS = 28;     // détail jour par jour conservé 4 semaines

function lgAddDays(iso, n){ return new Date(Date.parse(iso + "T12:00:00Z") + n*864e5).toISOString().slice(0,10); }
function lgWeekStart(iso){ const wd = (new Date(iso + "T12:00:00Z").getUTCDay() + 6) % 7; return lgAddDays(iso, -wd); }

// Deux « Marie » dans la même ligue : la deuxième arrivée s'affiche « Marie 2 ».
function lgDisplayNames(members){
  const seen = {};
  return members.map(m=>{ const k = m.name.trim().toLowerCase(); seen[k] = (seen[k]||0) + 1; return seen[k] > 1 ? m.name + " " + seen[k] : m.name; });
}

// Ordre de la semaine : le plus de points (bonus compris), puis le moins de jours joués (meilleure moyenne).
function lgCmp(a, b){ return b.total - a.total || a.played - b.played; }
function lgSetRanks(list, key, same){
  list.forEach((r, i)=>{ r[key] = (i > 0 && same(list[i-1], r)) ? list[i-1][key] : i + 1; });
}

// Champion(s) d'une semaine terminée (ex aequo possibles).
function lgChampions(members, scores, ws){
  const we = lgAddDays(ws, 6), tot = {};
  scores.forEach(s=>{ if (s.day >= ws && s.day <= we){ const t = tot[s.pid] || (tot[s.pid] = {total:0, played:0}); t.total += s.base + s.bonus; t.played++; } });
  const list = members.filter(m=>tot[m.pid]).map(m=>({pid:m.pid, name:m.name, total:tot[m.pid].total, played:tot[m.pid].played}));
  if (!list.length) return [];
  list.sort(lgCmp);
  return list.filter(x=>x.total === list[0].total && x.played === list[0].played);
}

// Vue d'une ligue pour un joueur donné (me = son identifiant).
// Les scores du jour des autres restent cachés tant que ce joueur n'a pas joué sa partie du jour.
// Les tickets détaillés ne sont visibles que pour les jours que ce joueur a lui-même joués.
function lgView(o){
  const ws = lgWeekStart(o.today), days = [0,1,2,3,4,5,6].map(k=>lgAddDays(ws, k));
  const names = lgDisplayNames(o.members);
  const by = {};
  o.scores.forEach(s=>{ (by[s.pid] = by[s.pid] || {})[s.day] = s; });
  const mineDays = by[o.me] || {};
  const hideToday = !mineDays[o.today];
  const visible = d => d < o.today || (d === o.today && !hideToday);
  const best = {};
  days.forEach(d=>{ if (!visible(d)) return; o.members.forEach(m=>{ const s = (by[m.pid]||{})[d]; if (s) best[d] = Math.max(best[d] ?? -1, s.base + s.bonus); }); });
  const rows = o.members.map((m, i)=>{
    const dd = {}; let total = 0, played = 0, crowns = 0;
    days.forEach(d=>{
      const s = (by[m.pid]||{})[d]; if (!s || d > o.today) return;
      if (!visible(d)){ dd[d] = {hidden:true}; return; }
      const t = s.base + s.bonus, win = best[d] === t;
      total += t; played++; if (win) crowns++;
      dd[d] = {g:s.game, t, b:s.base, x:s.bonus, win, tk: (mineDays[d] || m.pid === o.me) ? (s.ticket || "") : null};
    });
    const td = dd[o.today];
    return {name:names[i], me:m.pid === o.me, total, played, crowns, days:dd, today: td && !td.hidden ? td.t : null, playedToday: !!td};
  });
  const week = rows.slice().sort(lgCmp);
  lgSetRanks(week, "rank", (a,b)=>a.total === b.total && a.played === b.played);
  const tday = rows.filter(r=>r.today !== null).sort((a,b)=>b.today - a.today);
  lgSetRanks(tday, "trank", (a,b)=>a.today === b.today);
  const pal = {};
  (o.titles||[]).forEach(t=>{ const k = t.pid; pal[k] = pal[k] || {name: t.name, n:0, pid:t.pid}; pal[k].n++; });
  o.members.forEach((m,i)=>{ if (pal[m.pid]) pal[m.pid].name = names[i]; });
  return {
    id:o.league.id, name:o.league.name, count:o.members.length, ws, days, today:o.today, hideToday,
    rows: week.map(r=>({name:r.name, me:r.me, total:r.total, played:r.played, crowns:r.crowns, days:r.days, today:r.today, playedToday:r.playedToday, rank:r.rank, trank:r.trank ?? null})),
    champion: (o.champions && o.champions.length) ? {names:o.champions.map(c=>{ const i = o.members.findIndex(m=>m.pid===c.pid); return i >= 0 ? names[i] : c.name; }), total:o.champions[0].total, played:o.champions[0].played} : null,
    palmares: Object.values(pal).sort((a,b)=>b.n - a.n).map(p=>({name:p.name, n:p.n})),
  };
}

// ============================================================
//  LIGUES · serveur (Cloudflare Worker + base D1 nommée « DB »)
//  Stocke uniquement : un prénom, les ligues et les scores du jour.
//  Pas d'email, pas d'adresse IP. Détail des scores effacé après 4 semaines.
// ============================================================
const ORIGINS = ["https://es-tu-hors-sol.fr", "https://www.es-tu-hors-sol.fr"];
const SCHEMA = [
  "CREATE TABLE IF NOT EXISTS players (pid TEXT PRIMARY KEY, key_hash TEXT NOT NULL, name TEXT NOT NULL, created TEXT)",
  "CREATE TABLE IF NOT EXISTS leagues (id TEXT PRIMARY KEY, name TEXT NOT NULL, created TEXT, owner TEXT)",
  "CREATE TABLE IF NOT EXISTS members (league TEXT NOT NULL, pid TEXT NOT NULL, joined TEXT, PRIMARY KEY (league, pid))",
  "CREATE INDEX IF NOT EXISTS members_pid ON members (pid)",
  "CREATE TABLE IF NOT EXISTS scores (pid TEXT NOT NULL, day TEXT NOT NULL, game TEXT, base INTEGER, bonus INTEGER, ticket TEXT, PRIMARY KEY (pid, day))",
  "CREATE INDEX IF NOT EXISTS scores_day ON scores (day)",
  "CREATE TABLE IF NOT EXISTS titles (league TEXT NOT NULL, week TEXT NOT NULL, pid TEXT NOT NULL, name TEXT, total INTEGER, played INTEGER, PRIMARY KEY (league, week, pid))",
  "CREATE TABLE IF NOT EXISTS weeks_done (league TEXT NOT NULL, week TEXT NOT NULL, PRIMARY KEY (league, week))",
];
let schemaReady = false;

function parisDate(d = new Date()){
  return new Intl.DateTimeFormat("en-CA", {timeZone:"Europe/Paris", year:"numeric", month:"2-digit", day:"2-digit"}).format(d);
}
async function sha(s){
  const b = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(b)].map(x=>x.toString(16).padStart(2, "0")).join("");
}
function newId(n){
  const a = "abcdefghjkmnpqrstuvwxyz23456789";
  return [...crypto.getRandomValues(new Uint8Array(n))].map(x=>a[x % a.length]).join("");
}
const clean = (s, max) => String(s ?? "").replace(/[\u0000-\u001f<>]/g, "").replace(/\s+/g, " ").trim().slice(0, max);
const ID_RE = /^[a-z0-9]{6,40}$/;
class Oops extends Error { constructor(code, status = 400){ super(code); this.code = code; this.status = status; } }

async function leagueView(db, league, pid, today){
  const ws = lgWeekStart(today), lw = lgAddDays(ws, -7);
  const members = (await db.prepare("SELECT m.pid, p.name, m.joined FROM members m JOIN players p ON p.pid = m.pid WHERE m.league = ? ORDER BY m.joined, m.rowid").bind(league.id).all()).results;
  const scores = (await db.prepare("SELECT pid, day, game, base, bonus, ticket FROM scores WHERE day >= ? AND day <= ? AND pid IN (SELECT pid FROM members WHERE league = ?)").bind(lw, today, league.id).all()).results;
  // Champion de la semaine dernière : calculé une seule fois, au premier passage de la semaine.
  const done = await db.prepare("SELECT 1 FROM weeks_done WHERE league = ? AND week = ?").bind(league.id, lw).first();
  if (!done){
    const stmts = [db.prepare("INSERT OR IGNORE INTO weeks_done (league, week) VALUES (?, ?)").bind(league.id, lw)];
    if ((league.created || "") <= lgAddDays(lw, 6)){
      lgChampions(members, scores, lw).forEach(c=>stmts.push(
        db.prepare("INSERT OR IGNORE INTO titles (league, week, pid, name, total, played) VALUES (?, ?, ?, ?, ?, ?)").bind(league.id, lw, c.pid, c.name, c.total, c.played)));
    }
    await db.batch(stmts);
  }
  const champions = (await db.prepare("SELECT pid, name, total, played FROM titles WHERE league = ? AND week = ?").bind(league.id, lw).all()).results;
  const titles = (await db.prepare("SELECT pid, name FROM titles WHERE league = ?").bind(league.id).all()).results;
  return lgView({league, members, scores: scores.filter(s=>s.day >= ws), titles, champions, me: pid, today});
}

async function handle(body, env, today){
  const db = env.DB;
  const pid = String(body.pid || ""), key = String(body.key || "");
  if (!ID_RE.test(pid) || key.length < 16) throw new Oops("auth", 403);
  const player = await db.prepare("SELECT pid, key_hash, name FROM players WHERE pid = ?").bind(pid).first();
  const hash = await sha(key);
  const name = clean(body.name, 15);
  if (!player){
    if (!name) throw new Oops("name");
    await db.prepare("INSERT INTO players (pid, key_hash, name, created) VALUES (?, ?, ?, ?)").bind(pid, hash, name, today).run();
  } else {
    if (player.key_hash !== hash) throw new Oops("auth", 403);
    if (name && name !== player.name) await db.prepare("UPDATE players SET name = ? WHERE pid = ?").bind(name, pid).run();
  }

  // Scores de la semaine en cours envoyés par le téléphone (une seule partie par jour, la première reçue compte).
  const ws = lgWeekStart(today);
  const ins = [];
  for (const s of (Array.isArray(body.scores) ? body.scores.slice(0, 7) : [])){
    const day = String(s.day || ""), game = String(s.game || "");
    const base = Math.round(+s.base), bonus = Math.round(+s.bonus);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day) || day < ws || day > today || !LG_GAMES.includes(game)) continue;
    if (!(base >= 0 && base <= 500 && bonus >= 0 && bonus <= 500)) continue;
    ins.push(db.prepare("INSERT OR IGNORE INTO scores (pid, day, game, base, bonus, ticket) VALUES (?, ?, ?, ?, ?, ?)").bind(pid, day, game, base, bonus, String(s.ticket || "").slice(0, 4000)));
  }
  if (ins.length) await db.batch(ins);

  const myCount = async () => (await db.prepare("SELECT COUNT(*) AS n FROM members WHERE pid = ?").bind(pid).first()).n;
  if (body.action === "create"){
    const lname = clean(body.league_name, 30);
    if (!lname) throw new Oops("league_name");
    if (await myCount() >= LG_MAX_LEAGUES) throw new Oops("toomany");
    const id = newId(8);
    await db.batch([
      db.prepare("INSERT INTO leagues (id, name, created, owner) VALUES (?, ?, ?, ?)").bind(id, lname, today, pid),
      db.prepare("INSERT INTO members (league, pid, joined) VALUES (?, ?, ?)").bind(id, pid, new Date().toISOString()),
    ]);
    body.focus = id;
  } else if (body.action === "join"){
    const id = String(body.league || "");
    const lg = ID_RE.test(id) && await db.prepare("SELECT id FROM leagues WHERE id = ?").bind(id).first();
    if (!lg) throw new Oops("notfound", 404);
    const already = await db.prepare("SELECT 1 FROM members WHERE league = ? AND pid = ?").bind(id, pid).first();
    if (!already){
      if (await myCount() >= LG_MAX_LEAGUES) throw new Oops("toomany");
      const n = (await db.prepare("SELECT COUNT(*) AS n FROM members WHERE league = ?").bind(id).first()).n;
      if (n >= LG_MAX_MEMBERS) throw new Oops("full");
      await db.prepare("INSERT INTO members (league, pid, joined) VALUES (?, ?, ?)").bind(id, pid, new Date().toISOString()).run();
    }
  } else if (body.action === "leave"){
    await db.prepare("DELETE FROM members WHERE league = ? AND pid = ?").bind(String(body.league || ""), pid).run();
  }

  // Ménage de temps en temps : le détail des scores n'est gardé que 4 semaines (le palmarès reste).
  if (Math.random() < 0.02){
    await db.prepare("DELETE FROM scores WHERE day < ?").bind(lgAddDays(today, -LG_KEEP_DAYS)).run();
  }

  const leagues = (await db.prepare("SELECT l.id, l.name, l.created FROM members m JOIN leagues l ON l.id = m.league WHERE m.pid = ? ORDER BY m.joined").bind(pid).all()).results;
  const views = [];
  for (const lg of leagues) views.push(await leagueView(db, lg, pid, today));
  const me = await db.prepare("SELECT name FROM players WHERE pid = ?").bind(pid).first();
  return {ok:true, today, me:{name: me.name}, leagues: views, focus: body.focus || null};
}

export default {
  async fetch(req, env){
    const origin = req.headers.get("Origin") || "";
    const allowed = ORIGINS.includes(origin) || /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin);
    const cors = {"Access-Control-Allow-Origin": allowed ? origin : ORIGINS[0], "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                  "Access-Control-Allow-Headers": "Content-Type, X-Day", "Access-Control-Max-Age": "86400", "Vary": "Origin"};
    const json = (o, status = 200) => new Response(JSON.stringify(o), {status, headers: {...cors, "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"}});
    if (req.method === "OPTIONS") return new Response(null, {headers: cors});
    try {
      if (!schemaReady){ await env.DB.batch(SCHEMA.map(s=>env.DB.prepare(s))); schemaReady = true; }
      const url = new URL(req.url);
      // En test local uniquement (variable TEST=1), le jeu peut imposer la date du jour.
      const today = (env.TEST === "1" && /^\d{4}-\d{2}-\d{2}$/.test(req.headers.get("X-Day") || "")) ? req.headers.get("X-Day") : parisDate();
      if (req.method === "GET" && url.pathname === "/league"){
        const id = url.searchParams.get("id") || "";
        const lg = ID_RE.test(id) && await env.DB.prepare("SELECT id, name, (SELECT COUNT(*) FROM members WHERE league = leagues.id) AS count FROM leagues WHERE id = ?").bind(id).first();
        return lg ? json({ok:true, id:lg.id, name:lg.name, count:lg.count}) : json({error:"notfound"}, 404);
      }
      if (req.method === "POST" && url.pathname === "/api"){
        const body = await req.json();
        return json(await handle(body, env, today));
      }
      return new Response("Hors-Sol · serveur des ligues : OK", {headers: {...cors, "Content-Type": "text/plain; charset=utf-8"}});
    } catch (e){
      if (e instanceof Oops) return json({error: e.code}, e.status);
      return json({error: "server"}, 500);
    }
  },
};
