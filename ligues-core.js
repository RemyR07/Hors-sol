// ============================================================
//  LIGUES · noyau commun (serveur Cloudflare + maquette de test)
//  Calcule les classements à partir des membres et des scores.
// ============================================================
const LG_GAMES = ["fourchette","trio","rangement","drop","intrus","rayon"];
const LG_MAX_MEMBERS = 30;   // joueurs par ligue
const LG_MAX_LEAGUES = 10;   // ligues par joueur
const LG_KEEP_DAYS = 28;     // détail jour par jour conservé 4 semaines

// Calendrier des jeux (identique au jeu) : sert au serveur pour personnaliser le rappel de 18 h.
const LG_LAUNCH = "2026-10-16";
const LG_WEEK = {1:"trio", 2:"fourchette", 3:"rangement", 4:"drop", 5:"intrus", 6:"rayon", 0:"loi"};
function lgRng(seed){return function(){seed|=0;seed=seed+0x6D2B79F5|0;let t=Math.imul(seed^seed>>>15,1|seed);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}
function lgGameForDay(iso){
  const g = LG_WEEK[new Date(iso + "T12:00:00Z").getUTCDay()];
  if (g !== "loi") return g;
  const d = Math.round((Date.parse(iso) - Date.parse(LG_LAUNCH)) / 864e5);
  const r = lgRng(4930 + d * 7919); r();
  return LG_GAMES[Math.floor(r() * LG_GAMES.length)];
}

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
