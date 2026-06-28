import React, { useEffect, useState } from "react";
import { api, setCode } from "./api.js";

const STATUS_LABEL = {
  pending: "Pending",
  going: "Going",
  not_going: "Not going",
};

function Gate({ onAuthed }) {
  const [code, setVal] = useState("");
  const [err, setErr] = useState("");
  async function submit(e) {
    e.preventDefault();
    setCode(code);
    try {
      await api.login();
      onAuthed();
    } catch {
      setErr("Wrong code");
    }
  }
  return (
    <form className="gate" onSubmit={submit}>
      <h1>💍 Wedding RSVP</h1>
      <input
        type="password"
        placeholder="Access code"
        value={code}
        onChange={(e) => setVal(e.target.value)}
      />
      <button type="submit">Enter</button>
      {err && <p className="err">{err}</p>}
    </form>
  );
}

function parseList(text) {
  // One guest per line: "Name, +972..."  (comma, tab, or last-token phone)
  return text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)
    .map((line) => {
      const parts = line.split(/[,\t]/).map((p) => p.trim());
      if (parts.length >= 2) return { name: parts[0], phone: parts[1] };
      const m = line.match(/^(.*?)\s+(\+?[\d\-\s()]+)$/);
      return m ? { name: m[1], phone: m[2] } : { name: line, phone: "" };
    });
}

function Dashboard() {
  const [guests, setGuests] = useState([]);
  const [stats, setStats] = useState({});
  const [config, setConfig] = useState({ sms_template: "", has_recording: false });
  const [raw, setRaw] = useState("");
  const [msg, setMsg] = useState("");

  async function refresh() {
    setGuests(await api.guests());
    setStats(await api.stats());
  }

  useEffect(() => {
    refresh();
    api.getConfig().then(setConfig);
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, []);

  async function doImport() {
    const parsed = parseList(raw);
    const r = await api.importGuests(parsed);
    setMsg(`Added ${r.added}, skipped ${r.skipped}` + (r.errors.length ? `, ${r.errors.length} errors` : ""));
    setRaw("");
    refresh();
  }

  async function action(fn, confirmText) {
    if (!window.confirm(confirmText)) return;
    const r = await fn();
    setMsg(`Queued ${r.queued} guest(s)`);
    refresh();
  }

  return (
    <div className="dash">
      <header>
        <h1>💍 Wedding RSVP</h1>
        <div className="stats">
          <span className="going">Going {stats.going || 0}</span>
          <span className="not_going">Not going {stats.not_going || 0}</span>
          <span className="pending">Pending {stats.pending || 0}</span>
          <span>Total {stats.total || 0}</span>
        </div>
      </header>

      {msg && <div className="banner">{msg}</div>}

      <section>
        <h2>Setup</h2>
        <label>SMS message (use {"{name}"} for the guest's name)</label>
        <textarea
          rows={3}
          value={config.sms_template || ""}
          onChange={(e) => setConfig({ ...config, sms_template: e.target.value })}
        />
        <div className="row">
          <button onClick={() => api.setSmsTemplate(config.sms_template).then(() => setMsg("Message saved"))}>
            Save message
          </button>
          <label className="upload">
            {config.has_recording ? "Replace voice recording" : "Upload voice recording"}
            <input
              type="file"
              accept="audio/*"
              onChange={async (e) => {
                if (e.target.files[0]) {
                  await api.uploadRecording(e.target.files[0]);
                  setConfig(await api.getConfig());
                  setMsg("Recording uploaded");
                }
              }}
            />
          </label>
          {config.has_recording && <span className="ok">✓ recording set</span>}
        </div>
      </section>

      <section>
        <h2>Add guests</h2>
        <p className="hint">One per line: <code>Name, phone</code></p>
        <textarea rows={5} value={raw} onChange={(e) => setRaw(e.target.value)}
          placeholder={"Dana Cohen, 054-123-4567\nYossi Levi, +972521112233"} />
        <button onClick={doImport} disabled={!raw.trim()}>Import</button>
      </section>

      <section>
        <h2>Outreach</h2>
        <div className="row">
          <button className="primary" onClick={() => action(api.sendSms, "Send the SMS to all pending guests?")}>
            📱 Send SMS to pending
          </button>
          <button className="warn" onClick={() => action(api.callNonResponders, "Call everyone who hasn't responded?")}>
            📞 Call non-responders
          </button>
        </div>
      </section>

      <section>
        <h2>Guests</h2>
        <table>
          <thead>
            <tr><th>Name</th><th>Phone</th><th>RSVP</th><th>SMS</th><th>Call</th><th></th></tr>
          </thead>
          <tbody>
            {guests.map((g) => (
              <tr key={g.id} className={g.rsvp_status}>
                <td>{g.name}</td>
                <td>{g.phone}</td>
                <td>
                  <select value={g.rsvp_status} onChange={(e) => api.setStatus(g.id, e.target.value).then(refresh)}>
                    <option value="pending">Pending</option>
                    <option value="going">Going</option>
                    <option value="not_going">Not going</option>
                  </select>
                </td>
                <td>{g.sms_status}</td>
                <td>{g.call_status}</td>
                <td><button className="link" onClick={() => api.deleteGuest(g.id).then(refresh)}>✕</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

export default function App() {
  const [authed, setAuthed] = useState(!!sessionStorage.getItem("rsvp_code"));
  return authed ? <Dashboard /> : <Gate onAuthed={() => setAuthed(true)} />;
}
