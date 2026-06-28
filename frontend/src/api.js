// Thin fetch wrapper that attaches the shared access code on every request.
let accessCode = sessionStorage.getItem("rsvp_code") || "";

export function setCode(code) {
  accessCode = code;
  sessionStorage.setItem("rsvp_code", code);
}

async function req(method, path, body, isForm = false) {
  const headers = { "X-Access-Code": accessCode };
  let payload = body;
  if (body && !isForm) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(path, { method, headers, body: payload });
  if (res.status === 401) throw new Error("unauthorized");
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res.text();
}

export const api = {
  login: () => req("GET", "/api/login"),
  guests: () => req("GET", "/api/guests"),
  stats: () => req("GET", "/api/stats"),
  importGuests: (guests) => req("POST", "/api/guests/import", { guests }),
  deleteGuest: (id) => req("DELETE", `/api/guests/${id}`),
  setStatus: (id, rsvp_status) =>
    req("POST", `/api/guests/${id}/status`, { rsvp_status }),
  getConfig: () => req("GET", "/api/config"),
  setSmsTemplate: (sms_template) => req("PUT", "/api/config", { sms_template }),
  uploadRecording: (file) => {
    const fd = new FormData();
    fd.append("file", file);
    return req("POST", "/api/config/recording", fd, true);
  },
  sendSms: () => req("POST", "/api/actions/send-sms"),
  callNonResponders: () => req("POST", "/api/actions/call-nonresponders"),
};
