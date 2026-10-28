// Usage: node make_patterns.js <hemoscan root>
// Writes docs/fingerprint_patterns/*.png (synthetic ridge patterns) and dataset/*.png (real samples per blood group).
const fs = require('fs'), path = require('path'), zlib = require('zlib')
const ROOT = process.argv[2]
const OUT = path.join(ROOT, 'docs', 'fingerprint_patterns')
fs.mkdirSync(path.join(OUT, 'dataset'), { recursive: true })

const CRC = new Int32Array(256).map((_, n) => { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; return c })
const crc32 = (b) => { let c = -1; for (const x of b) c = CRC[(c ^ x) & 255] ^ (c >>> 8); return (c ^ -1) >>> 0 }
function chunk(type, data) {
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length)
  const td = Buffer.concat([Buffer.from(type), data]); const c = Buffer.alloc(4); c.writeUInt32BE(crc32(td))
  return Buffer.concat([len, td, c])
}
function png(file, w, h, gray) { // gray: Uint8Array w*h
  const raw = Buffer.alloc((w + 1) * h)
  for (let y = 0; y < h; y++) { raw[y * (w + 1)] = 0; Buffer.from(gray.buffer, y * w, w).copy(raw, y * (w + 1) + 1) }
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 0
  fs.writeFileSync(file, Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]))
}

// ---------- synthetic patterns (SFinGe-style) ----------
// 1. orientation field from singular points (Sherlock-Monro): theta = 1/2 * (sum arg(z-core) - sum arg(z-delta))
// 2. start from random noise and repeatedly apply a Gabor filter tuned to the local orientation -> ridges grow
const W = 320, H = 400, FREQ = 1 / 9, Q = 36, R = 7, SIG = 3.6
const arg = (x, y, p) => Math.atan2(y - p[1], x - p[0])
const sm = (cores, deltas) => (x, y) => 0.5 * (cores.reduce((s, c) => s + arg(x, y, c), 0) - deltas.reduce((s, d) => s + arg(x, y, d), 0))
const PATTERNS = {
  arch: (x, y) => Math.atan(-2.6 * ((x - W / 2) / 85) * Math.exp(-(((x - W / 2) / 85) ** 2)) * Math.max(0.1, 1 - y / (H * 0.9))),
  tented_arch: sm([[160, 170]], [[160, 235]]),
  right_loop: sm([[175, 165]], [[95, 285]]), // NIST convention: opens to the right, delta on the left
  left_loop: sm([[145, 165]], [[225, 285]]),
  whorl: sm([[150, 170], [172, 205]], [[70, 300], [255, 300]]),
}
const KER = Array.from({ length: Q }, (_, q) => { // kernels for Q quantised ridge directions
  const t = (q / Q) * Math.PI, k = []
  for (let dy = -R; dy <= R; dy++) for (let dx = -R; dx <= R; dx++) {
    const n = -dx * Math.sin(t) + dy * Math.cos(t) // distance across the ridges
    k.push(Math.exp(-(dx * dx + dy * dy) / (2 * SIG * SIG)) * Math.cos(2 * Math.PI * FREQ * n))
  }
  return k
})
let seed = 7
const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647)
for (const [name, theta] of Object.entries(PATTERNS)) {
  const qi = new Uint8Array(W * H)
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    let t = theta(x, y) % Math.PI; if (t < 0) t += Math.PI
    qi[y * W + x] = Math.round((t / Math.PI) * Q) % Q
  }
  let img = Float32Array.from({ length: W * H }, () => rnd() * 2 - 1)
  for (let it = 0; it < 14; it++) {
    const nxt = new Float32Array(W * H)
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      const k = KER[qi[y * W + x]]; let s = 0, i = 0
      for (let dy = -R; dy <= R; dy++) {
        const yy = Math.min(H - 1, Math.max(0, y + dy)) * W
        for (let dx = -R; dx <= R; dx++, i++) s += k[i] * img[yy + Math.min(W - 1, Math.max(0, x + dx))]
      }
      nxt[y * W + x] = Math.tanh(2 * s)
    }
    img = nxt
  }
  const g = new Uint8Array(W * H)
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const ex = (x - W / 2) / (W * 0.46), ey = (y - H * 0.53) / (H * 0.47) // fingertip outline
    const r = ex * ex + (ey < 0 ? ey * ey : ey * ey * 0.55)
    const mask = Math.min(Math.max((1 - r) / 0.08, 0), 1)
    g[y * W + x] = Math.round(255 - mask * (0.5 + 0.5 * img[y * W + x]) * 225)
  }
  png(path.join(OUT, name + '.png'), W, H, g)
  console.log('pattern', name)
}

// ---------- real samples: BMP (32 bpp bitfields or 24/8 bpp) -> PNG, 2x nearest upscale ----------
function readBmp(file) {
  const b = fs.readFileSync(file), off = b.readInt32LE(10), w = b.readInt32LE(18), hh = b.readInt32LE(22), bpp = b.readInt16LE(28)
  const h = Math.abs(hh), stride = Math.ceil((w * bpp) / 32) * 4, g = new Uint8Array(w * h)
  for (let y = 0; y < h; y++) {
    const row = off + (hh > 0 ? h - 1 - y : y) * stride
    for (let x = 0; x < w; x++) {
      if (bpp === 8) { const i = b[row + x], p = 54 + i * 4; g[y * w + x] = Math.round((b[p] + b[p + 1] + b[p + 2]) / 3) }
      else { const p = row + x * (bpp / 8); g[y * w + x] = Math.round((b[p] + b[p + 1] + b[p + 2]) / 3) }
    }
  }
  return { w, h, g }
}
const NAMES = { 'A+': 'A_pos', 'A-': 'A_neg', 'AB+': 'AB_pos', 'AB-': 'AB_neg', 'B+': 'B_pos', 'B-': 'B_neg', 'O+': 'O_pos', 'O-': 'O_neg' }
for (const [cls, safe] of Object.entries(NAMES)) {
  const dir = path.join(ROOT, 'ml', 'data', 'dataset_blood_group', cls)
  if (!fs.existsSync(dir)) continue
  const files = fs.readdirSync(dir).filter((f) => /\.bmp$/i.test(f)).sort()
  ;[0, Math.floor(files.length / 2), files.length - 1].forEach((fi, n) => {
    const { w, h, g } = readBmp(path.join(dir, files[fi]))
    const S = 2, out = new Uint8Array(w * S * h * S)
    for (let y = 0; y < h * S; y++) for (let x = 0; x < w * S; x++) out[y * w * S + x] = g[((y / S) | 0) * w + ((x / S) | 0)]
    png(path.join(OUT, 'dataset', `${safe}_${n + 1}.png`), w * S, h * S, out)
  })
}
console.log('done', fs.readdirSync(OUT).length, fs.readdirSync(path.join(OUT, 'dataset')).length)
