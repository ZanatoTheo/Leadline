// Loaded into `next start` by scripts/smoke_app.py (NODE_OPTIONS=--require ...).
// Blocks every outbound TCP connection and DNS lookup that is not for this machine, and writes
// one line per blocked attempt to $SMOKE_OUTBOUND_LOG, so the smoke run can
// prove the app made no network calls (no Cala, no Context.dev, no model).
const dns = require("dns");
const fs = require("fs");
const net = require("net");

const log = process.env.SMOKE_OUTBOUND_LOG;
const LOCAL = new Set(["127.0.0.1", "localhost", "::1", "::ffff:127.0.0.1"]);

function note(line) {
  if (log) fs.appendFileSync(log, `${line}\n`);
}

function hostOf(args) {
  const first = args[0];
  if (Array.isArray(first)) return hostOf(first); // internal normalized form: [options, cb]
  if (first && typeof first === "object") return first.path ? null : first.host ?? "localhost";
  if (typeof first === "number" || /^\d+$/.test(String(first))) return typeof args[1] === "string" ? args[1] : "localhost";
  return null; // a unix socket path
}

const connect = net.Socket.prototype.connect;
net.Socket.prototype.connect = function guardedConnect(...args) {
  const host = hostOf(args);
  if (host !== null && !LOCAL.has(host)) {
    note(`blocked ${host}`);
    const err = new Error(`smoke guard: outbound connection to ${host} blocked`);
    process.nextTick(() => this.destroy(err));
    return this;
  }
  return connect.apply(this, args);
};

// DNS: a lookup of any other name fails at once (before any packet is sent).
for (const target of [dns, dns.promises]) {
  const lookup = target.lookup;
  target.lookup = function guardedLookup(host, ...rest) {
    if (typeof host === "string" && !LOCAL.has(host)) {
      note(`blocked ${host} (dns)`);
      const err = Object.assign(new Error(`smoke guard: DNS lookup of ${host} blocked`), { code: "ENOTFOUND" });
      if (target === dns.promises) return Promise.reject(err);
      const cb = rest.at(-1);
      if (typeof cb === "function") process.nextTick(() => cb(err));
      return;
    }
    return lookup.call(this, host, ...rest);
  };
}
