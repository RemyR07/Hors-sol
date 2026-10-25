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
  "CREATE TABLE IF NOT EXISTS push_subs (pid TEXT PRIMARY KEY, endpoint TEXT NOT NULL, p256dh TEXT, auth TEXT, streak INTEGER DEFAULT 0, created TEXT, last_sent TEXT)",
  "CREATE TABLE IF NOT EXISTS settings (k TEXT PRIMARY KEY, v TEXT NOT NULL)",
  // « Je ne connais pas ce produit » : une ligne par joueur, par jour et par produit vu (unknown = 1 s'il l'a signalé)
  "CREATE TABLE IF NOT EXISTS avis (day TEXT NOT NULL, pid TEXT NOT NULL, code TEXT NOT NULL, unknown INTEGER DEFAULT 0, PRIMARY KEY (day, pid, code))",
  "CREATE INDEX IF NOT EXISTS avis_code ON avis (code)",
];
const AVIS_KEEP_DAYS = 180;   // les avis servent au bilan de chaque produit sur 6 mois

// ============================================================
//  RAPPEL DE 18 H (notifications Web Push, sans contenu chiffré :
//  le téléphone vient chercher le texte du jour sur /rappel)
// ============================================================
const JEUX = {fourchette:"la Fourchette", trio:"le Trio au kilo", rangement:"le Rangement", drop:"le Caddie Drop", intrus:"l'Intrus", rayon:"la Mise en rayon"};
const ICO = {fourchette:"🎯", trio:"⚖️", rangement:"🛒", drop:"💰", intrus:"🔎", rayon:"🏷️"};
const RAPPELS = [
  "{i} Plus que 6 h pour {j}. Après minuit, on vous nomme ministre.",
  "{i} {J} vous attend. Le gouvernement, lui, a déjà oublié le prix du pain.",
  "🥖 Le prix de la baguette n'attend pas. {J} non plus : plus que 6 h !",
  "📉 Un ministre vient de battre votre score. Ah non, vous n'avez pas encore joué.",
  "🧾 Votre ticket du jour est vide. Même une note de frais est mieux remplie.",
  "🛒 Vos courses ne vont pas se deviner toutes seules : {j} ferme à minuit.",
  "🎩 Un conseiller ministériel a répondu à votre place : « 10 centimes ». Corrigez ça avant minuit.",
  "⏳ Il reste 6 h. C'est plus que le temps d'un débat à l'Assemblée sur le prix du lait.",
  "📢 Communiqué officiel : {j} du jour n'a toujours pas été joué. Une commission d'enquête est envisagée.",
  "🚗 Le chauffeur du ministre est en route. Vous, vous pouvez encore jouer à {j} sans lui.",
  "🤔 Le Nutella a encore augmenté ? Vérifiez-le dans {j} avant minuit.",
  "🏃 Dernière ligne droite : {j} vous attend, la caisse ferme à minuit.",
];
const RAPPELS_JEU = {
  drop: ["💰 Le Caddie Drop vous attend. Même le ministre a misé ses jetons, lui.", "💰 100 jetons dorment dans votre caddie. Les trappes ferment à minuit !"],
  trio: ["⚖️ Il vous reste 6 h pour le Trio au kilo. Le prix au kilo, ce n'est pas qu'au marché !"],
  intrus: ["🔎 Un faux prix se cache dans les rayons. Démasquez l'Intrus avant minuit !"],
  rayon: ["🏷️ Les étiquettes traînent par terre. Le chef de rayon, c'est vous : plus que 6 h !"],
  rangement: ["🛒 Trois caddies en vrac vous attendent. Rangez-les avant la fermeture !"],
  fourchette: ["🎯 La Fourchette est servie. Ne la laissez pas refroidir jusqu'à minuit !"],
};
const RAPPELS_LOI = ["🏛️ Le 49.3 a décidé du jeu du jour : {j}. Vous, vous n'avez pas encore décidé de jouer ?"];
const RAPPELS_SERIE = ["🔥 Votre série de {s} jours va s'éteindre ! Le gouvernement compte sur votre oubli.",
                       "🔥 {s} jours d'affilée… Ce serait dommage de tout perdre pour un oubli. Plus que 6 h !"];

function rappelTexte(today, streak){
  const g = lgGameForDay(today), loi = new Date(today + "T12:00:00Z").getUTCDay() === 0;
  let pool = RAPPELS.concat(RAPPELS_JEU[g] || []);
  if (loi) pool = pool.concat(RAPPELS_LOI, RAPPELS_LOI);
  if (streak >= 3) pool = pool.concat(RAPPELS_SERIE, RAPPELS_SERIE);
  const r = lgRng(Date.parse(today) / 864e5 + streak * 31);
  const j = JEUX[g] || "le défi du jour";
  const body = pool[Math.floor(r() * pool.length)]
    .replace("{i}", ICO[g] || "🛒").replace("{J}", j.charAt(0).toUpperCase() + j.slice(1)).replace(/\{j\}/g, j).replace("{s}", streak);
  return {title: "Hors-Sol · plus que 6 h !", body, url: "/?src=rappel"};
}

const b64u = buf => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
// Clés VAPID créées une seule fois par le serveur lui-même et rangées dans la base (rien à configurer à la main).
async function vapidKeys(db){
  const row = await db.prepare("SELECT v FROM settings WHERE k = 'vapid'").first();
  if (row) return JSON.parse(row.v);
  const kp = await crypto.subtle.generateKey({name:"ECDSA", namedCurve:"P-256"}, true, ["sign", "verify"]);
  const priv = await crypto.subtle.exportKey("jwk", kp.privateKey);
  const pub = b64u(await crypto.subtle.exportKey("raw", kp.publicKey));
  const keys = {priv, pub};
  await db.prepare("INSERT OR IGNORE INTO settings (k, v) VALUES ('vapid', ?)").bind(JSON.stringify(keys)).run();
  return JSON.parse((await db.prepare("SELECT v FROM settings WHERE k = 'vapid'").first()).v);
}
async function vapidHeader(endpoint, keys){
  const enc = o => b64u(new TextEncoder().encode(JSON.stringify(o)));
  const unsigned = enc({typ:"JWT", alg:"ES256"}) + "." + enc({aud: new URL(endpoint).origin, exp: Math.floor(Date.now()/1000) + 12*3600, sub: "https://es-tu-hors-sol.fr"});
  const key = await crypto.subtle.importKey("jwk", keys.priv, {name:"ECDSA", namedCurve:"P-256"}, false, ["sign"]);
  const sig = await crypto.subtle.sign({name:"ECDSA", hash:"SHA-256"}, key, new TextEncoder().encode(unsigned));
  return `vapid t=${unsigned}.${b64u(sig)}, k=${keys.pub}`;
}
// Appelé toutes les 10 minutes entre 16 h et 17 h 50 UTC : n'agit que pendant l'heure de 18 h à Paris (été comme hiver).
async function runReminders(env, today, force){
  const hour = +new Intl.DateTimeFormat("en-GB", {timeZone:"Europe/Paris", hour:"2-digit", hour12:false}).format(new Date());
  if (hour !== 18 && !force) return {skipped:"hour", hour};
  const db = env.DB, keys = await vapidKeys(db);
  // Rappel seulement si : pas encore joué aujourd'hui, ET au moins une partie dans les 7 derniers jours
  // (un joueur qui a décroché ou désinstallé ne reçoit pas plus de 7 rappels, puis plus rien).
  const subs = (await db.prepare(`SELECT pid, endpoint FROM push_subs
      WHERE (last_sent IS NULL OR last_sent < ?)
        AND pid NOT IN (SELECT pid FROM scores WHERE day = ?)
        AND pid IN (SELECT pid FROM scores WHERE day >= ? AND day < ?)
      LIMIT 40`).bind(today, today, lgAddDays(today, -7), today).all()).results;
  if (!subs.length) return {sent:0};
  await db.batch(subs.map(s=>db.prepare("UPDATE push_subs SET last_sent = ? WHERE pid = ?").bind(today, s.pid)));
  let sent = 0, gone = [];
  for (const s of subs){
    try{
      const r = await fetch(s.endpoint, {method:"POST", headers:{"Authorization": await vapidHeader(s.endpoint, keys), "TTL":"21600", "Urgency":"normal", "Content-Length":"0"}});
      if (r.status === 404 || r.status === 410) gone.push(s.pid); else if (r.ok) sent++;
    }catch(e){}
  }
  if (gone.length) await db.batch(gone.map(pid=>db.prepare("DELETE FROM push_subs WHERE pid = ?").bind(pid)));
  return {sent, gone: gone.length, batch: subs.length};
}
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
  const prevScores = (league.created || "") <= lgAddDays(lw, 6) ? scores.filter(s=>s.day < ws) : null;   // ligue déjà ouverte la semaine dernière
  return lgView({league, members, scores: scores.filter(s=>s.day >= ws), prevScores, titles, champions, me: pid, today});
}

async function handle(body, env, today){
  const db = env.DB;
  const pid = String(body.pid || ""), key = String(body.key || "");
  if (!ID_RE.test(pid) || key.length < 16) throw new Oops("auth", 403);
  const player = await db.prepare("SELECT pid, key_hash, name FROM players WHERE pid = ?").bind(pid).first();
  const hash = await sha(key);
  const name = clean(body.name, 15);
  const needsName = body.action === "create" || body.action === "join";
  if (!player){
    if (!name && needsName) throw new Oops("name");
    await db.prepare("INSERT INTO players (pid, key_hash, name, created) VALUES (?, ?, ?, ?)").bind(pid, hash, name, today).run();
  } else {
    if (player.key_hash !== hash) throw new Oops("auth", 403);
    if (name && name !== player.name) await db.prepare("UPDATE players SET name = ? WHERE pid = ?").bind(name, pid).run();
    if (!name && !player.name && needsName) throw new Oops("name");
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
  } else if (body.action === "remind_on"){
    const sub = body.sub || {}, ep = String(sub.endpoint || "");
    const okUrl = env.TEST === "1" ? /^https?:\/\/[^\s]{6,900}$/ : /^https:\/\/[^\s]{10,900}$/;   // en test local : faux service de notification
    if (!okUrl.test(ep)) throw new Oops("sub");
    await db.prepare("INSERT INTO push_subs (pid, endpoint, p256dh, auth, streak, created) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(pid) DO UPDATE SET endpoint = excluded.endpoint, p256dh = excluded.p256dh, auth = excluded.auth")
      .bind(pid, ep, String((sub.keys||{}).p256dh || "").slice(0, 200), String((sub.keys||{}).auth || "").slice(0, 100), Math.max(0, Math.round(+body.streak || 0)), today).run();
  } else if (body.action === "remind_off"){
    await db.prepare("DELETE FROM push_subs WHERE pid = ?").bind(pid).run();
  } else if (body.action === "leave"){
    await db.prepare("DELETE FROM members WHERE league = ? AND pid = ?").bind(String(body.league || ""), pid).run();
  }

  if (Number.isFinite(+body.streak)) await db.prepare("UPDATE push_subs SET streak = ? WHERE pid = ?").bind(Math.max(0, Math.round(+body.streak)), pid).run();

  // Ménage de temps en temps : le détail des scores n'est gardé que 4 semaines (le palmarès reste).
  if (Math.random() < 0.02){
    await db.prepare("DELETE FROM scores WHERE day < ?").bind(lgAddDays(today, -LG_KEEP_DAYS)).run();
  }

  const leagues = (await db.prepare("SELECT l.id, l.name, l.created FROM members m JOIN leagues l ON l.id = m.league WHERE m.pid = ? ORDER BY m.joined").bind(pid).all()).results;
  const views = [];
  for (const lg of leagues) views.push(await leagueView(db, lg, pid, today));
  const me = await db.prepare("SELECT name FROM players WHERE pid = ?").bind(pid).first();
  const remind = !!(await db.prepare("SELECT 1 FROM push_subs WHERE pid = ?").bind(pid).first());
  return {ok:true, today, me:{name: me.name}, leagues: views, focus: body.focus || null, remind};
}

export default {
  async scheduled(event, env, ctx){
    ctx.waitUntil((async ()=>{
      if (!schemaReady){ await env.DB.batch(SCHEMA.map(s=>env.DB.prepare(s))); schemaReady = true; }
      await runReminders(env, parisDate(), false);
    })());
  },
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
      if (req.method === "GET" && url.pathname === "/vapid"){
        return json({ok:true, key: (await vapidKeys(env.DB)).pub});
      }
      if (req.method === "GET" && url.pathname === "/rappel"){
        const pid = url.searchParams.get("pid") || "";
        const row = ID_RE.test(pid) && await env.DB.prepare("SELECT streak FROM push_subs WHERE pid = ?").bind(pid).first();
        // la série n'est « en jeu » que si le joueur a joué hier
        const hier = row && await env.DB.prepare("SELECT 1 FROM scores WHERE pid = ? AND day = ?").bind(pid, lgAddDays(today, -1)).first();
        return json(rappelTexte(today, hier ? row.streak || 0 : 0));
      }
      if (env.TEST === "1" && url.pathname === "/__rappels"){
        return json(await runReminders(env, today, true));
      }
      // « Je ne connais pas ce produit » : le téléphone envoie les produits vus et ceux qu'il ne connaissait pas.
      if (req.method === "POST" && url.pathname === "/avis"){
        const b = await req.json();
        const pid = String(b.pid || ""), day = String(b.day || "");
        if (!ID_RE.test(pid) || (day !== today && day !== lgAddDays(today, -1))) return json({error:"avis"}, 400);
        const CODE = /^[A-Za-z0-9-]{3,40}$/;
        const unk = new Set((Array.isArray(b.unknown) ? b.unknown : []).map(String));
        const seen = (Array.isArray(b.seen) ? b.seen.slice(0, 30) : []).map(String).filter(c=>CODE.test(c));
        if (seen.length) await env.DB.batch(seen.map(c=>env.DB.prepare(
          "INSERT INTO avis (day, pid, code, unknown) VALUES (?, ?, ?, ?) ON CONFLICT(day, pid, code) DO UPDATE SET unknown = excluded.unknown")
          .bind(day, pid, c, unk.has(c) ? 1 : 0)));
        if (Math.random() < 0.02) await env.DB.prepare("DELETE FROM avis WHERE day < ?").bind(lgAddDays(today, -AVIS_KEEP_DAYS)).run();
        return json({ok:true});
      }
      // Bilan par produit (lu chaque nuit par le script des prix) : nombre de joueurs qui l'ont vu, et qui ne le connaissaient pas.
      if (req.method === "GET" && url.pathname === "/inconnus"){
        const rows = (await env.DB.prepare("SELECT code, COUNT(*) AS seen, SUM(unknown) AS unknown FROM avis GROUP BY code HAVING SUM(unknown) > 0").all()).results;
        return json({ok:true, today, items: rows});
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
