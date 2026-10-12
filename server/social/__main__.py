"""HTTP front of the friends service:   python -m server.social --dir social --port 8791

Players: one endpoint, JSON in and out:  POST /  {"op": "...", "id": "...", "secret": "...", ...}  ->  {"ok": true, ...} or
{"ok": false, "error": "..."}.  GET /health answers "ok". Messages are end-to-end encrypted by the apps; this service
only stores envelopes it cannot read (see server/social/e2e.py and docs/FRIENDS_SECURITY.md).

Moderation console: https://<address>/admin shows a login form and nothing else until someone signs in with an account
name, password and a code from their authenticator app (server/social/admin_auth.py). Make the first (owner) account on
the computer that runs the service:
    python -m server.social --dir social --create-admin <name>
or, when Legacy Player runs the service, in the app: Friends > Your service > Set up the moderation console. Owners
invite moderators from the console with a one-time code.

The moderator key (<dir>/moderator.key, made on first start) is only for Legacy Player on the computer that runs the
service: it is accepted from this computer (loopback) and refused from anywhere else unless --allow-remote-key is given.

HTTPS: --tls-cert/--tls-key serve it directly (Legacy Player uses its self-signed certificate and friends' apps check its
fingerprint, which travels in the friends link); or put a reverse proxy or a tunnel in front. No request log is kept:
who talked to whom is deliberately not recorded, and no address is ever written to disk."""
from __future__ import annotations

import argparse
import base64
import hmac
import json
import os
import ssl
import sys
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from server.http_guard import AddressWindow, BoundedHTTPServer

from . import SocialError, SocialService
from .admin_auth import AdminStore, AuthError, Sessions, write_private

MAX_BODY = 64 * 1024                 # a group message sealed for ten people is a few kilobytes
HELLO_PER_HOUR = 10                  # new identities per address per hour (this computer itself is not limited)
LOGIN_PER_10_MIN = 20                # console logins and invite set-ups per address (plus a lockout per account name)
COOKIE = "lp_admin"
OPS = {"hello", "heartbeat", "request", "decide", "remove", "invite", "dismiss_invite", "message", "thread", "goodbye",
       "block", "unblock", "clear_thread", "read_all", "report", "group_create", "group_add", "group_remove",
       "group_rename", "group_leave", "group_message", "group_thread", "group_clear"}
LOOPBACK = ("127.0.0.1", "::1", "::ffff:127.0.0.1")
FORWARD_HEADERS = ("X-Forwarded-For", "Forwarded", "X-Real-IP", "X-Forwarded-Host")


def dispatch(service: SocialService, body: dict) -> dict:
    op = str(body.get("op") or "")
    if op not in OPS:
        raise SocialError("unknown operation")
    pid, secret = body.get("id"), body.get("secret")
    legacy = not body.get("e2e")                     # apps from before encryption do not say e2e
    if op == "hello":
        return service.hello(body.get("name"), body.get("pub"))
    if op == "heartbeat":
        return service.heartbeat(pid, secret, body.get("name"), body.get("status", ""), body.get("room"), body.get("requests_open"),
                                 body.get("pub"))
    if op == "report":
        return service.report(pid, secret, body.get("player"), body.get("category"), body.get("details", ""), body.get("message", ""),
                              bool(body.get("block")), body.get("keys"), str(body.get("group") or ""))
    if op == "request":
        return service.request(pid, secret, body.get("code"))
    if op == "decide":
        return service.decide(pid, secret, body.get("from"), bool(body.get("accept")))
    if op == "remove":
        return service.remove(pid, secret, body.get("friend"))
    if op == "invite":
        return service.invite(pid, secret, body.get("to"), body.get("invite_code"), body.get("game"), body.get("server_code", ""),
                             body.get("sealed"))
    if op == "dismiss_invite":
        return service.dismiss_invite(pid, secret, body.get("from"))
    if op == "message":
        return service.message(pid, secret, body.get("to"), body.get("envelope"))
    if op == "thread":
        return service.thread(pid, secret, body.get("friend"), legacy)
    if op == "block":
        return service.block(pid, secret, body.get("player"))
    if op == "unblock":
        return service.unblock(pid, secret, body.get("player"))
    if op == "clear_thread":
        return service.clear_thread(pid, secret, body.get("friend"))
    if op == "read_all":
        return service.read_all(pid, secret)
    if op == "group_create":
        return service.group_create(pid, secret, body.get("name"), body.get("members"))
    if op == "group_add":
        return service.group_add(pid, secret, body.get("group"), body.get("member"))
    if op == "group_remove":
        return service.group_remove(pid, secret, body.get("group"), body.get("member"))
    if op == "group_rename":
        return service.group_rename(pid, secret, body.get("group"), body.get("name"))
    if op == "group_leave":
        return service.group_leave(pid, secret, body.get("group"))
    if op == "group_message":
        return service.group_message(pid, secret, body.get("group"), body.get("envelope"))
    if op == "group_thread":
        return service.group_thread(pid, secret, body.get("group"))
    if op == "group_clear":
        return service.group_clear(pid, secret, body.get("group"))
    return service.goodbye(pid, secret)


def qr_data_uri(text: str) -> str:
    """The set-up link as a scannable picture (data: URI of an SVG), or "" if it can't be drawn (the text still works)."""
    try:
        from . import qr
        return "data:image/svg+xml;base64," + base64.b64encode(qr.svg(text, scale=5).encode()).decode()
    except Exception:
        return ""


ADMIN_PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Friends moderation</title>
<style>
:root{color-scheme:dark;--bg:#0b1020;--panel:#141a33;--line:#2a3155;--text:#eef1ff;--mute:#aab3d6;--accent:#4f8cff;--good:#3be0a8;--warn:#ffb454;--bad:#ff8c98}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 "Segoe UI Variable","Segoe UI",system-ui,sans-serif;background:var(--bg);color:var(--text)}
header{display:flex;align-items:center;gap:14px;padding:14px 22px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg);z-index:2;flex-wrap:wrap}
h1{font-size:1.1rem;margin:0}.grow{flex:1}main{max-width:1240px;margin:0 auto;padding:18px 22px}
.tabs button.on{background:var(--accent);color:#fff;border-color:transparent}
select,input,textarea,button{font:inherit;color:inherit;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:7px 12px}
button{cursor:pointer}button.primary{background:var(--accent);border-color:transparent;color:#fff;font-weight:600}button.bad{border-color:var(--bad);color:var(--bad)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px 16px;margin-bottom:12px}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.muted{color:var(--mute)}.small{font-size:.85rem}.err{color:var(--bad)}
.pill{display:inline-block;font-size:.74rem;padding:2px 9px;border-radius:999px;border:1px solid var(--line);color:var(--mute)}
.pill.open{color:var(--warn);border-color:var(--warn)}.pill.resolved{color:var(--good);border-color:var(--good)}.pill.banned{color:var(--bad);border-color:var(--bad)}.pill.muted{color:var(--warn);border-color:var(--warn)}
.quote{border-left:3px solid var(--bad);padding:6px 12px;margin:8px 0;background:#0b1020;border-radius:8px}
.ctx{font-size:.84rem;color:var(--mute);margin:2px 0}.ctx b{color:var(--text);font-weight:600}
table{width:100%;border-collapse:collapse}td,th{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left}th{color:var(--mute);font-size:.82rem}
.stat{display:inline-flex;gap:6px;padding:6px 12px;border:1px solid var(--line);border-radius:10px}
.login{max-width:420px;margin:40px auto}.login label{display:block;margin:10px 0 4px;font-size:.88rem;color:var(--mute)}.login input{width:100%}
code{word-break:break-all}.qr{background:#fff;padding:8px;border-radius:10px;display:inline-block}[hidden]{display:none!important}
</style></head><body>
<header><h1>Friends service &middot; moderation</h1><span id="stats" class="row"></span><span class="grow"></span>
 <span class="row tabs" id="tabs" hidden><button data-t="reports" class="on">Reports</button><button data-t="players">Players</button><button data-t="filter">Word filter</button><button data-t="log">Log</button><button data-t="accounts" id="acctab" hidden>Accounts</button></span>
 <button id="refresh" hidden>Refresh</button><span id="who" class="small muted"></span><button id="logout" hidden>Log out</button></header>
<main id="main"></main>
<script>
const $=s=>document.querySelector(s);let tab="reports",D=null,status="open",ME=null;
async function api(path,body){const h={};if(body){h["Content-Type"]="application/json";if(ME)h["X-CSRF-Token"]=ME.csrf}
 const r=await fetch(path,body?{method:"POST",headers:h,body:JSON.stringify(body),credentials:"same-origin"}:{headers:h,credentials:"same-origin"});
 const j=await r.json().catch(()=>({}));if(r.status===401&&!/\/(login|me)$/.test(path)){ME=null;showLogin("Your session ended. Log in again.");throw new Error("login needed")}if(!r.ok||j.ok===false)throw new Error(j.error||("HTTP "+r.status));return j}
const esc=t=>String(t==null?"":t).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const when=t=>t?new Date(t*1000).toLocaleString():"";
const state=p=>!p?"":p.banned?'<span class="pill banned">banned</span>':p.muted?'<span class="pill muted">timed out until '+esc(when(p.muted.until))+'</span>':"";
const actions=(pid,rid)=>`<div class="row" style="margin-top:8px"><input placeholder="Reason (the player sees it)" data-reason style="min-width:240px">
 <select data-len><option value="1h">1 hour</option><option value="24h">24 hours</option><option value="7d">7 days</option><option value="30d">30 days</option></select>
 <button data-act="timeout" data-p="${esc(pid)}" data-r="${esc(rid||"")}">Time out</button><button data-act="untimeout" data-p="${esc(pid)}">End time-out</button>
 <button class="bad" data-act="ban" data-p="${esc(pid)}" data-r="${esc(rid||"")}">Ban</button><button data-act="unban" data-p="${esc(pid)}">Unban</button>
 ${rid?`<button data-act="resolve" data-r="${esc(rid)}">Mark handled</button><button data-act="dismiss" data-r="${esc(rid)}">Dismiss</button>`:""}</div>`;
function wire(){document.querySelectorAll("[data-act]").forEach(b=>b.onclick=async()=>{const box=b.closest(".card,tr");const reason=(box.querySelector("[data-reason]")||{}).value||"",len=(box.querySelector("[data-len]")||{}).value||"";
 if(b.dataset.act==="ban"&&!confirm("Ban this player from the friends service?"))return;
 try{await api("/admin/act",{action:b.dataset.act,player:b.dataset.p||"",report:b.dataset.r||"",length:len,reason});load()}catch(e){alert(e.message)}})}
function ctxLine(r,c){const who=c.from==="reported"?r.target.name:c.from==="reporter"?r.reporter.name:c.from;return `<div class="ctx"><b>${esc(who)}:</b> ${c.verified===false?'<i>'+esc(c.text)+'</i>':esc(c.text)}</div>`}
function draw(){const m=$("#main");if(!D){m.innerHTML='<p class="muted">Loading…</p>';return}
 $("#stats").innerHTML=`<span class="stat">${D.open} open reports</span><span class="stat">${D.players} players</span><span class="stat">${D.muted} timed out</span><span class="stat">${D.banned} banned</span><span class="stat">filter ${D.filter.on?"on":"off"}</span>`;
 if(tab==="reports"){const list=D.reports.filter(r=>!status||r.status===status);
  m.innerHTML=`<p class="small muted">Messages are end-to-end encrypted. A reported message is shown only because the reporter shared its key; the service opened its own stored copy with it, so the words are exactly what was sent.</p><div class="row" style="margin-bottom:12px"><select id="st"><option value="open">Open</option><option value="resolved">Handled</option><option value="dismissed">Dismissed</option><option value="">All</option></select></div>`+
   (list.map(r=>`<div class="card"><div class="row"><b>${esc(r.target.name)}</b><span class="muted small">${esc(r.target.code)}</span>${state(r.target_state)}<span class="pill ${esc(r.status)}">${esc(r.status)}</span><span class="pill">${esc(r.category)}</span>${r.group?`<span class="pill">group: ${esc(r.group)}</span>`:""}<span class="grow"></span><span class="muted small">${esc(when(r.at))} · reported by ${esc(r.reporter.name)} · ${r.target_state.reports} report(s) about them</span></div>
    ${r.details?`<p style="margin:8px 0 0">${esc(r.details)}</p>`:""}
    ${r.context&&r.context.length?'<div style="margin-top:8px">'+r.context.map(c=>ctxLine(r,c)).join("")+"</div>":""}
    ${r.message?`<div class="quote"><b>${esc(r.target.name)}:</b> ${esc(r.message.text)} <span class="muted small">(${esc(when(r.message.at))}${r.message.verified?" · verified":""})</span></div>`:""}
    ${actions(r.target.id,r.id)}</div>`).join("")||'<p class="muted">Nothing here.</p>');
  $("#st").value=status;$("#st").onchange=e=>{status=e.target.value;draw()}}
 else if(tab==="players"){m.innerHTML=`<div class="row" style="margin-bottom:12px"><input id="q" placeholder="Name, friend code or id" style="min-width:280px"><button id="go" class="primary">Search</button></div><div id="pl"></div>`;
  const run=async()=>{const d=await api("/admin/players?q="+encodeURIComponent($("#q").value));$("#pl").innerHTML=d.players.map(p=>`<div class="card"><div class="row"><b>${esc(p.name)}</b><span class="muted small">${esc(p.code)} · ${esc(p.id)}</span>${state(p)}<span class="grow"></span><span class="muted small">${p.friends} friends · ${p.reports} report(s) · seen ${esc(when(p.seen))}</span></div>${actions(p.id,"")}</div>`).join("")||'<p class="muted">No one found.</p>';wire()};
  $("#go").onclick=run;$("#q").onkeydown=e=>{if(e.key==="Enter")run()};run();return}
 else if(tab==="filter"){m.innerHTML=`<div class="card"><h3 style="margin-top:0">Service-wide word filter</h3><p class="muted small">When on, player names, statuses, group names and invites with these words are refused by the service. Messages are end-to-end encrypted, so the service can't filter them: each player's own app hides filtered words in what they read. The built-in list covers common profanity; add your own words below, one per line or separated by commas.</p>
  <label class="row"><input type="checkbox" id="fon" ${D.filter.on?"checked":""}> Refuse names and invites with filtered words</label>
  <p class="small muted" style="margin:10px 0 4px">Your words (${D.filter.words.length})</p><textarea id="fw" rows="8" style="width:100%">${esc(D.filter.words.join("\n"))}</textarea>
  <div class="row" style="margin-top:8px"><button class="primary" id="fsave">Save</button></div></div>`;
  $("#fsave").onclick=async()=>{await api("/admin/filter",{on:$("#fon").checked,words:$("#fw").value});load()}}
 else if(tab==="accounts"){accounts();return}
 else{m.innerHTML='<table><thead><tr><th>When</th><th>Action</th><th>Player</th><th>By</th><th>Length</th><th>Reason</th></tr></thead><tbody>'+D.log.map(l=>`<tr><td class="small">${esc(when(l.at))}</td><td>${esc(l.action)}</td><td>${esc(l.name)} <span class="muted small">${esc(l.player)}</span></td><td>${esc(l.by||"")}</td><td>${esc(l.length)}</td><td>${esc(l.reason)}</td></tr>`).join("")+"</tbody></table>"}
 wire()}
async function accounts(){const m=$("#main");const a=await api("/admin/accounts");
 m.innerHTML=`<div class="card"><h3 style="margin-top:0">Console accounts</h3><table><thead><tr><th>Name</th><th>Role</th><th>Last login</th><th></th></tr></thead><tbody>${a.accounts.map(x=>`<tr><td>${esc(x.name)}</td><td>${esc(x.role)}</td><td class="small">${esc(when(x.last_login))}</td><td>${x.name!==ME.name?`<button class="bad" data-rm="${esc(x.name)}">Remove</button>`:""}</td></tr>`).join("")}</tbody></table>
 <div class="row" style="margin-top:12px"><button class="primary" id="inv">Invite a moderator</button><span id="invout" class="small"></span></div><p class="small muted">The invite is a one-time code, good for 48 hours. Give it to the person yourself; they open this page, choose "I have an invite", and pick their own password and authenticator.</p></div>
 <div class="card"><h3 style="margin-top:0">Sign-in log</h3><table><tbody>${a.audit.map(x=>`<tr><td class="small">${esc(when(x.at))}</td><td>${esc(x.event)}</td><td>${esc(x.user)}</td><td class="small muted">${esc(x.detail)}</td></tr>`).join("")}</tbody></table></div>`;
 $("#inv").onclick=async()=>{try{const r=await api("/admin/invite/create",{role:"moderator"});$("#invout").innerHTML='Invite code: <code>'+esc(r.code)+'</code>'}catch(e){alert(e.message)}};
 document.querySelectorAll("[data-rm]").forEach(b=>b.onclick=async()=>{if(!confirm("Remove the account "+b.dataset.rm+"?"))return;try{await api("/admin/accounts/remove",{name:b.dataset.rm});accounts()}catch(e){alert(e.message)}})}
document.querySelectorAll(".tabs button").forEach(b=>b.onclick=()=>{tab=b.dataset.t;document.querySelectorAll(".tabs button").forEach(x=>x.classList.toggle("on",x===b));draw()});
$("#refresh").onclick=()=>load();
$("#logout").onclick=async()=>{try{await api("/admin/logout",{})}catch(e){}ME=null;D=null;showLogin("You are logged out.")};
function chrome(on){["#tabs","#refresh","#logout"].forEach(s=>$(s).hidden=!on);$("#acctab").hidden=!(on&&ME&&ME.role==="owner");$("#who").textContent=on&&ME?ME.name+" ("+ME.role+")":"";if(!on)$("#stats").innerHTML=""}
function showLogin(why){chrome(false);$("#main").innerHTML=`<form class="card login" id="lf" autocomplete="on"><h2 style="margin-top:0">Log in</h2>
 <p class="small muted">${esc(why||"Only the people who run this friends service can sign in.")}</p>
 <label for="u">Name</label><input id="u" autocomplete="username" required>
 <label for="p">Password</label><input id="p" type="password" autocomplete="current-password" required>
 <label for="c">Code from your authenticator app</label><input id="c" inputmode="numeric" autocomplete="one-time-code" maxlength="8" required>
 <div class="row" style="margin-top:14px"><button class="primary" id="go">Log in</button><span class="grow"></span><a href="#" id="hasinv" class="small muted">I have an invite</a></div><p id="lerr" class="err small"></p></form>`;
 $("#lf").onsubmit=async e=>{e.preventDefault();$("#lerr").textContent="";try{ME=await api("/admin/login",{name:$("#u").value,password:$("#p").value,code:$("#c").value});load()}catch(x){$("#lerr").textContent=x.message;$("#c").value=""}};
 $("#hasinv").onclick=e=>{e.preventDefault();showInvite()}}
function showInvite(){$("#main").innerHTML=`<form class="card login" id="if"><h2 style="margin-top:0">Join as a moderator</h2><p class="small muted">Use the one-time invite code the owner gave you, then pick your own name and password (at least 10 characters).</p>
 <label>Invite code</label><input id="ic" required><label>Name</label><input id="iu" autocomplete="username" required><label>Password</label><input id="ip" type="password" autocomplete="new-password" required>
 <div class="row" style="margin-top:14px"><button class="primary">Next</button><a href="#" id="back" class="small muted">Back to log in</a></div><p id="ierr" class="err small"></p></form>`;
 $("#back").onclick=e=>{e.preventDefault();showLogin()};
 $("#if").onsubmit=async e=>{e.preventDefault();try{const r=await api("/admin/invite/begin",{invite:$("#ic").value,name:$("#iu").value,password:$("#ip").value});showTotp(r)}catch(x){$("#ierr").textContent=x.message}}}
function showTotp(r){$("#main").innerHTML=`<form class="card login" id="tf"><h2 style="margin-top:0">Set up your authenticator</h2><p class="small">Add this account to an authenticator app (scan the code, or type the secret), then type the 6-digit code it shows.</p>
 ${r.qr?`<div class="qr"><img alt="QR code for the authenticator" src="${esc(r.qr)}" width="220" height="220"></div>`:""}
 <p class="small muted">Secret: <code>${esc(r.secret)}</code></p><p class="small muted">Link: <code>${esc(r.uri)}</code></p>
 <label>Code</label><input id="tc" inputmode="numeric" maxlength="8" required><div class="row" style="margin-top:14px"><button class="primary">Turn it on</button></div><p id="terr" class="err small"></p></form>`;
 $("#tf").onsubmit=async e=>{e.preventDefault();try{await api("/admin/invite/finish",{name:r.name,code:$("#tc").value});showLogin("Your account is ready. Log in with it.")}catch(x){$("#terr").textContent=x.message}}}
async function load(){try{if(!ME){ME=await api("/admin/me")}chrome(true);D=await api("/admin/reports");draw()}catch(e){if(!ME)showLogin();else $("#main").innerHTML='<p>Could not load: '+esc(e.message)+'</p>'}}
load();
</script></body></html>"""


class FriendsHTTPServer(BoundedHTTPServer):
    """At most MAX_CONCURRENT requests at once, each with a total deadline, and no client address in the log."""
    label = "friends service"


def make_handler(service: SocialService, admin_token: str | None = None, hello_limit: AddressWindow | None = None,
                 admins: AdminStore | None = None, sessions: Sessions | None = None, allow_remote_key: bool = False,
                 login_limit: AddressWindow | None = None):
    # New identities per address (an IPv6 /64 counts as one): the address is used only here, in memory, never stored.
    hello_limit = hello_limit if hello_limit is not None else AddressWindow(HELLO_PER_HOUR, 3600.0)
    login_limit = login_limit if login_limit is not None else AddressWindow(LOGIN_PER_10_MIN, 600.0)
    sessions = sessions if sessions is not None else Sessions()

    class Handler(BaseHTTPRequestHandler):
        server_version = "LegacyPlayerFriends"
        timeout = 10

        def log_message(self, *args) -> None:
            pass

        def _headers_common(self, kind: str) -> None:
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")

        def _json(self, code: int, payload: dict, cookie: str | None = None) -> None:
            body = json.dumps(payload).encode()
            self.send_response(code)
            self._headers_common("application/json")
            if cookie is not None:
                self.send_header("Set-Cookie", cookie)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _page(self, html: str) -> None:
            body = html.encode()
            self.send_response(200)
            self._headers_common("text/html; charset=utf-8")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                                                        "img-src data:; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        # --- who is asking -------------------------------------------------------------------------------------------
        def _local(self) -> bool:
            """This computer, and not a reverse proxy passing someone else's request along."""
            return self.client_address[0] in LOOPBACK and not any(self.headers.get(h) for h in FORWARD_HEADERS)

        def _https(self) -> bool:
            return isinstance(self.connection, ssl.SSLSocket) or (self.headers.get("X-Forwarded-Proto") or "").lower() == "https"

        def _cookie(self, sid: str, max_age: int) -> str:
            return (f"{COOKIE}={sid}; Path=/admin; HttpOnly; SameSite=Strict; Max-Age={max_age}"
                    + ("; Secure" if self._https() else ""))

        def _sid(self) -> str:
            try:
                jar = SimpleCookie(self.headers.get("Cookie") or "")
            except Exception:
                return ""
            return jar[COOKIE].value if COOKIE in jar else ""

        def _who(self, write: bool) -> tuple[dict | None, int, str]:
            """(principal, 0, '') or (None, status, error). The key: this computer only (unless --allow-remote-key).
            A session: from its cookie, and every change carries its CSRF token."""
            key = self.headers.get("X-Admin-Token")
            if key is not None:
                if not admin_token or not hmac.compare_digest(key.encode("utf-8", "replace"), admin_token.encode("utf-8")):
                    return None, 401, "admin token needed"
                if not (self._local() or allow_remote_key):
                    return None, 403, "The moderator key only works on the computer that runs this service. Log in with your account instead."
                return {"name": "this computer", "role": "owner", "via": "key"}, 0, ""
            s = sessions.get(self._sid())
            if s is None:
                return None, 401, "login needed"
            if write:
                token = self.headers.get("X-CSRF-Token") or ""
                origin = self.headers.get("Origin")
                host = self.headers.get("Host") or ""
                if not hmac.compare_digest(token.encode("utf-8", "replace"), s["csrf"].encode()):
                    return None, 403, "This request did not come from the console page (missing or wrong CSRF token)."
                if origin and origin.split("://", 1)[-1] != host:
                    return None, 403, "This request came from another site."
            return {"name": s["name"], "role": s["role"], "via": "session", "sid": s["id"], "csrf": s["csrf"]}, 0, ""

        def _console_on(self) -> bool:
            return bool(admin_token) or admins is not None

        def _read_json(self) -> dict | None:
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                length = -1
            if not 0 <= length <= MAX_BODY:
                return None
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, RecursionError):
                return None
            return body if isinstance(body, dict) else None

        # --- GET -------------------------------------------------------------------------------------------------
        def do_GET(self) -> None:
            from urllib.parse import parse_qs, urlsplit
            u = urlsplit(self.path)
            if u.path in ("/", "/health"):
                return self._json(200, {"ok": True, "service": "legacy-player-friends", "e2e": 1})
            if not u.path.startswith("/admin"):
                return self._json(404, {"ok": False, "error": "not found"})
            if not self._console_on():
                return self._json(401, {"ok": False, "error": "no console here"})
            if u.path in ("/admin", "/admin/"):
                return self._page(ADMIN_PAGE)              # a login form: nothing about players until someone signs in
            who, status, error = self._who(write=False)
            if who is None:
                return self._json(status, {"ok": False, "error": error})
            q = parse_qs(u.query)
            if u.path == "/admin/me":
                return self._json(200, {"ok": True, **{k: who[k] for k in ("name", "role", "via")}, "csrf": who.get("csrf", "")})
            if u.path == "/admin/reports":
                return self._json(200, {"ok": True, **service.admin_reports(q.get("status", [""])[0])})
            if u.path == "/admin/players":
                return self._json(200, {"ok": True, **service.admin_players(q.get("q", [""])[0])})
            if u.path == "/admin/accounts":
                if who["role"] != "owner" or admins is None:
                    return self._json(403, {"ok": False, "error": "only owners manage accounts"})
                return self._json(200, {"ok": True, "accounts": admins.accounts(), "audit": admins.audit_tail(200)})
            self._json(404, {"ok": False, "error": "not found"})

        # --- POST ------------------------------------------------------------------------------------------------
        def do_POST(self) -> None:
            from urllib.parse import urlsplit
            path = urlsplit(self.path).path
            if path.startswith("/admin"):
                return self._admin_post(path)
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                length = -1
            if not 0 < length <= MAX_BODY:
                return self._json(413, {"ok": False, "error": "bad request size"})
            try:
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError
            except (ValueError, RecursionError):
                return self._json(400, {"ok": False, "error": "invalid JSON"})
            if body.get("op") == "hello" and not hello_limit.allow(self.client_address[0]):
                return self._json(429, {"ok": False, "error": "Too many new identities from this address; try again in an hour."})
            try:
                out = dispatch(service, body)
            except SocialError as exc:
                return self._json(400, {"ok": False, "error": str(exc)})
            except Exception as exc:                       # never a traceback to a stranger
                return self._json(500, {"ok": False, "error": f"something went wrong ({type(exc).__name__})"})
            self._json(200, {"ok": True, **out})

        def _admin_post(self, path: str) -> None:
            if not self._console_on():
                return self._json(401, {"ok": False, "error": "no console here"})
            body = self._read_json()
            if body is None:
                return self._json(400, {"ok": False, "error": "bad request"})
            try:
                # --- no session yet: logging in, and joining with an invite ---------------------------------------
                if path in ("/admin/login", "/admin/invite/begin", "/admin/invite/finish"):
                    if admins is None:
                        return self._json(404, {"ok": False, "error": "accounts are not set up on this service"})
                    if not login_limit.allow(self.client_address[0]):
                        return self._json(429, {"ok": False, "error": "Too many tries from your network. Wait ten minutes."})
                    if path == "/admin/login":
                        user = admins.login(str(body.get("name") or ""), str(body.get("password") or ""), str(body.get("code") or ""))
                        s = sessions.create(user["name"], user["role"])
                        return self._json(200, {"ok": True, "name": s["name"], "role": s["role"], "via": "session", "csrf": s["csrf"]},
                                          cookie=self._cookie(s["id"], int(sessions.lifetime)))
                    if path == "/admin/invite/begin":
                        out = admins.begin_from_invite(str(body.get("invite") or ""), str(body.get("name") or ""), str(body.get("password") or ""))
                        return self._json(200, {"ok": True, **out, "qr": qr_data_uri(out["uri"])})
                    out = admins.finish(str(body.get("name") or ""), str(body.get("code") or ""))
                    return self._json(200, {"ok": True, **out})
                # --- this computer only, with the key: first set-up from Legacy Player, and stopping -----------------
                if path in ("/admin/setup/begin", "/admin/setup/finish", "/admin/stop"):
                    who, status, error = self._who(write=True)
                    if who is None or who["via"] != "key" or not self._local():
                        return self._json(403 if who else status, {"ok": False, "error": "only from this computer"})
                    if path == "/admin/stop":
                        threading.Thread(target=self.server.shutdown, daemon=True).start()
                        return self._json(200, {"ok": True, "stopping": True})
                    if admins is None:
                        return self._json(404, {"ok": False, "error": "accounts are not set up on this service"})
                    if path == "/admin/setup/begin":
                        out = admins.begin(str(body.get("name") or ""), str(body.get("password") or ""), "owner")
                        return self._json(200, {"ok": True, **out, "qr": qr_data_uri(out["uri"])})
                    return self._json(200, {"ok": True, **admins.finish(str(body.get("name") or ""), str(body.get("code") or ""))})
                who, status, error = self._who(write=True)
                if who is None:
                    return self._json(status, {"ok": False, "error": error})
                if path == "/admin/logout":
                    if who["via"] == "session":
                        sessions.end(who["sid"])
                        if admins is not None:
                            admins.audit("logout", who["name"])
                    return self._json(200, {"ok": True}, cookie=self._cookie("", 0))
                if path == "/admin/act":
                    out = service.admin_act(str(body.get("action", "")), str(body.get("player", "")), str(body.get("report", "")),
                                            str(body.get("length", "")), str(body.get("reason", "")), by=who["name"])
                    if admins is not None:
                        admins.audit("action", who["name"], f"{body.get('action', '')} {body.get('player', '') or body.get('report', '')}")
                    return self._json(200, {"ok": True, **out})
                if path == "/admin/filter":
                    out = service.admin_filter(body.get("on"), body.get("words"))
                    if admins is not None:
                        admins.audit("filter", who["name"], "on" if out["filter"]["on"] else "off")
                    return self._json(200, {"ok": True, **out})
                if path in ("/admin/invite/create", "/admin/accounts/remove"):
                    if who["role"] != "owner" or admins is None:
                        return self._json(403, {"ok": False, "error": "only owners manage accounts"})
                    if path == "/admin/invite/create":
                        return self._json(200, {"ok": True, **admins.create_invite(who["name"], str(body.get("role") or "moderator"))})
                    name = str(body.get("name") or "")
                    admins.remove(name, who["name"])
                    sessions.end_user(name)
                    return self._json(200, {"ok": True})
                return self._json(404, {"ok": False, "error": "not found"})
            except AuthError as exc:
                return self._json(400 if "Too many" not in str(exc) else 429, {"ok": False, "error": str(exc)})
            except SocialError as exc:
                return self._json(400, {"ok": False, "error": str(exc)})
            except (ValueError, TypeError, RecursionError, AttributeError):
                return self._json(400, {"ok": False, "error": "bad request"})
    return Handler


def moderator_key(folder: Path) -> str:
    """The key Legacy Player on this computer uses to moderate the service it runs, made once and kept next to the
    service's data (owner-only permissions). It is accepted from this computer only."""
    import secrets
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "moderator.key"
    try:
        key = path.read_text(encoding="utf-8").strip()
        if len(key) >= 16:
            return key
    except OSError:
        pass
    key = "LPM-" + secrets.token_urlsafe(24)
    write_private(path, (key + "\n").encode("utf-8"))
    return key


def create_admin(folder: Path, name: str, role: str = "owner", ask=None, read_code=None, out=print) -> bool:
    """`--create-admin`: a password typed twice (never echoed), then the authenticator secret, then one code to confirm."""
    import getpass
    ask = ask or getpass.getpass
    read_code = read_code or input
    store = AdminStore(folder)
    password = ask(f"Password for {name} (at least 10 characters): ")
    if password != ask("The same password again: "):
        out("The two passwords are different. Nothing was changed.")
        return False
    try:
        started = store.begin(name, password, role)
    except AuthError as exc:
        out(str(exc))
        return False
    out("Add this account to your authenticator app (Google Authenticator, Microsoft Authenticator, Aegis, 1Password...).")
    out(f"  Secret: {started['secret']}")
    out(f"  Or this link: {started['uri']}")
    out("Keep the secret private: it is the second half of your login.")
    for _ in range(3):
        try:
            store.finish(name, read_code("Type the 6-digit code your app shows now: "))
            out(f"Done. {name} can now log in at https://<this service's address>/admin")
            return True
        except AuthError as exc:
            out(str(exc))
    out("Not turned on. Run --create-admin again to start over.")
    return False


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dir", default=os.environ.get("LP_SOCIAL_DIR") or "social")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8791)
    parser.add_argument("--admin-token", default=os.environ.get("LP_SOCIAL_ADMIN_TOKEN") or None,
                        help="choose the local moderator key yourself (otherwise one is made and kept in <dir>/moderator.key)")
    parser.add_argument("--allow-remote-key", action="store_true",
                        help="also accept the moderator key from other computers (off: remote moderators log in with an account)")
    parser.add_argument("--create-admin", metavar="NAME", help="make a console owner account (asks for a password, shows the authenticator secret) and exit")
    parser.add_argument("--invite-moderator", action="store_true", help="print a one-time moderator invite code and exit")
    parser.add_argument("--tls-cert", help="serve HTTPS directly with this certificate (PEM)")
    parser.add_argument("--tls-key", help="the certificate's private key (PEM)")
    args = parser.parse_args(argv)
    folder = Path(args.dir)
    if args.create_admin:
        sys.exit(0 if create_admin(folder, args.create_admin) else 1)
    if args.invite_moderator:
        inv = AdminStore(folder).create_invite("command line")
        print(f"Moderator invite code (one use, 48 hours): {inv['code']}\nThey open https://<address>/admin and choose 'I have an invite'.")
        return
    key = args.admin_token or moderator_key(folder)
    service = SocialService(folder)
    admins = AdminStore(folder)
    httpd = FriendsHTTPServer((args.host, args.port), make_handler(service, key, admins=admins, allow_remote_key=args.allow_remote_key))
    scheme = "http"
    if args.tls_cert:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(args.tls_cert, args.tls_key)
        # the handshake happens in each request thread, so a stranger who never finishes it cannot hold up the others
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True, do_handshake_on_connect=False)
        scheme = "https"

    def tidy() -> None:
        while True:
            time.sleep(600)
            try:
                with service.lock:
                    service._tidy()
                    service._changed()
            except Exception as exc:                       # one bad pass must not end tidying for good
                print(f"friends service: tidy failed ({type(exc).__name__})", flush=True)
    threading.Thread(target=tidy, daemon=True).start()
    print(f"Friends service on {scheme}://{args.host}:{httpd.server_address[1]}/ keeping its players in {folder}"
          + ("" if scheme == "https" else "  (put HTTPS in front of it)"), flush=True)
    print(f"Moderation console: {scheme}://<this address>/admin  "
          + ("(log in with your account)" if admins.has_accounts()
             else f"(no accounts yet: run  python -m server.social --dir {folder} --create-admin <name>)"), flush=True)
    try:
        import signal
        signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=httpd.shutdown, daemon=True).start())
    except (AttributeError, ValueError, OSError):
        pass                                               # stopped some other way: /admin/stop or Ctrl+C still save
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        service.flush()


if __name__ == "__main__":
    main()
