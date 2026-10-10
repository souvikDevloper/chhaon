// Speak a question: microphone → Amazon Transcribe streaming (hi-IN / en-IN) over a WebSocket.
// The server only signs the URL (POST /api/listen); audio goes straight from the phone to AWS.
// Transcribe's WebSocket speaks the AWS event-stream binary format, encoded here by hand.

const enc = new TextEncoder();
const dec = new TextDecoder();

let CRC_TABLE = null;
function crc32(bytes) {
  if (!CRC_TABLE) {
    CRC_TABLE = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      CRC_TABLE[n] = c >>> 0;
    }
  }
  let crc = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) crc = CRC_TABLE[(crc ^ bytes[i]) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

function encodeHeaders(headers) {
  const parts = [];
  for (const [name, value] of Object.entries(headers)) {
    const n = enc.encode(name), v = enc.encode(value);
    const b = new Uint8Array(1 + n.length + 1 + 2 + v.length);
    const dv = new DataView(b.buffer);
    b[0] = n.length; b.set(n, 1);
    b[1 + n.length] = 7; // string
    dv.setUint16(2 + n.length, v.length);
    b.set(v, 4 + n.length);
    parts.push(b);
  }
  const out = new Uint8Array(parts.reduce((a, p) => a + p.length, 0));
  let o = 0;
  for (const p of parts) { out.set(p, o); o += p.length; }
  return out;
}

export function encodeEvent(payload) {
  const headers = encodeHeaders({ ":content-type": "application/octet-stream", ":event-type": "AudioEvent", ":message-type": "event" });
  const total = 12 + headers.length + payload.length + 4;
  const msg = new Uint8Array(total);
  const dv = new DataView(msg.buffer);
  dv.setUint32(0, total);
  dv.setUint32(4, headers.length);
  dv.setUint32(8, crc32(msg.subarray(0, 8)));
  msg.set(headers, 12);
  msg.set(payload, 12 + headers.length);
  dv.setUint32(total - 4, crc32(msg.subarray(0, total - 4)));
  return msg;
}

export function decodeEvent(buf) {
  const msg = new Uint8Array(buf);
  const dv = new DataView(msg.buffer, msg.byteOffset, msg.byteLength);
  const total = dv.getUint32(0), hlen = dv.getUint32(4);
  const headers = {};
  let o = 12;
  while (o < 12 + hlen) {
    const nlen = msg[o]; const name = dec.decode(msg.subarray(o + 1, o + 1 + nlen)); o += 1 + nlen;
    const type = msg[o]; o += 1;
    if (type === 7) { const vlen = dv.getUint16(o); headers[name] = dec.decode(msg.subarray(o + 2, o + 2 + vlen)); o += 2 + vlen; }
    else break;
  }
  const body = dec.decode(msg.subarray(12 + hlen, total - 4));
  return { headers, body };
}

function toPcm16(float32, fromRate, toRate) {
  const ratio = fromRate / toRate;
  const n = Math.floor(float32.length / ratio);
  const out = new DataView(new ArrayBuffer(n * 2));
  for (let i = 0; i < n; i++) {
    const s = Math.max(-1, Math.min(1, float32[Math.floor(i * ratio)]));
    out.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Uint8Array(out.buffer);
}

// Starts listening. Returns { stop() }. onText(text, final) is called as words arrive.
export async function listen(signed, onText, onEnd) {
  const media = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  const src = ctx.createMediaStreamSource(media);
  const proc = ctx.createScriptProcessor(4096, 1, 1);
  const ws = new WebSocket(signed.url);
  ws.binaryType = "arraybuffer";
  let finals = "", partial = "", closed = false, lastVoice = Date.now();

  const finish = () => {
    if (closed) return;
    closed = true;
    try { proc.disconnect(); src.disconnect(); } catch {}
    media.getTracks().forEach((tr) => tr.stop());
    ctx.close().catch(() => {});
    if (ws.readyState === WebSocket.OPEN) { try { ws.send(encodeEvent(new Uint8Array(0))); } catch {} setTimeout(() => ws.close(), 1500); }
    onEnd?.((finals + " " + partial).trim());
  };

  proc.onaudioprocess = (e) => {
    if (closed || ws.readyState !== WebSocket.OPEN) return;
    const data = e.inputBuffer.getChannelData(0);
    let peak = 0;
    for (let i = 0; i < data.length; i += 16) peak = Math.max(peak, Math.abs(data[i]));
    if (peak > 0.04) lastVoice = Date.now();
    ws.send(encodeEvent(toPcm16(data, ctx.sampleRate, signed.sample_rate)));
    // stop after 2 s of quiet once something was said, or after 15 s in all
    if ((finals || partial) && Date.now() - lastVoice > 2000) finish();
  };
  ws.onopen = () => { src.connect(proc); proc.connect(ctx.destination); };
  ws.onmessage = (m) => {
    const { headers, body } = decodeEvent(m.data);
    if (headers[":message-type"] !== "event") { console.warn("transcribe", body); finish(); return; }
    const results = JSON.parse(body).Transcript?.Results || [];
    for (const r of results) {
      const text = r.Alternatives?.[0]?.Transcript || "";
      if (r.IsPartial) partial = text; else { finals = (finals + " " + text).trim(); partial = ""; }
    }
    onText((finals + " " + partial).trim(), false);
  };
  ws.onerror = () => finish();
  ws.onclose = () => finish();
  setTimeout(finish, 15000);
  return { stop: finish };
}
