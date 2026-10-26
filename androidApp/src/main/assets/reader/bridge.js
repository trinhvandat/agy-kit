// Cầu nối foliate-js ↔ Kotlin cho Sepia (SPIKE-1, docs/02 §6, ADR-001/008).
//
// Kotlin → JS: window.sepia.open(url, cfi?) / goTo(cfi) / goToFraction(f) / next() / prev()
//              / applyStyle(css) / reAnchor(fullQuery, snippetQuery, targetFraction)
// JS → Kotlin (qua window.kmpJsBridge.callNative của compose-webview-multiplatform):
//              ready{} · relocated{cfi,fraction,snippet,prefix,suffix} · error{where,message}
//              · reanchorResult{token, cfis:[...]}
//
// Cử chỉ lật trang KHÔNG xử lý ở đây — reader Compose phủ vùng chạm trái/phải/giữa (docs/02 §8).

import './foliate/view.js' // định nghĩa <foliate-view>

const SNIPPET_LEN = 64
const CTX_LEN = 32

let view = null
let styleCss = '' // CSS theme hiện hành (Sepia…) do Kotlin đẩy xuống

function post(method, payload) {
  try {
    window.kmpJsBridge.callNative(method, JSON.stringify(payload || {}), null)
  } catch (e) {
    // bridge chưa sẵn sàng — bỏ qua an toàn
  }
}

function reportError(where, e) {
  post('error', { where, message: String((e && e.message) || e) })
}

function applyStyleNow() {
  try {
    if (view && view.renderer && typeof view.renderer.setStyles === 'function' && styleCss) {
      view.renderer.setStyles(styleCss)
    }
  } catch (e) { reportError('applyStyle', e) }
}

// Trích neo (snippet/prefix/suffix) quanh đầu trang hiển thị — trong phạm vi một text node.
// Giới hạn đã biết (SPIKE-1): chưa vắt qua nhiều node; đủ cho re-anchor vị trí đọc Mốc 2.
function extractAnchor(range) {
  try {
    if (!range) return { snippet: '', prefix: '', suffix: '' }
    let node = range.startContainer
    let offset = range.startOffset || 0
    while (node && node.nodeType !== 3) { node = node.firstChild; offset = 0 }
    if (!node) return { snippet: '', prefix: '', suffix: '' }
    const text = node.textContent || ''
    const start = Math.max(0, Math.min(offset, text.length))
    return {
      snippet: text.slice(start, start + SNIPPET_LEN),
      prefix: text.slice(Math.max(0, start - CTX_LEN), start),
      suffix: text.slice(start + SNIPPET_LEN, start + SNIPPET_LEN + CTX_LEN),
    }
  } catch (e) {
    return { snippet: '', prefix: '', suffix: '' }
  }
}

function onRelocate(e) {
  try {
    const loc = e.detail || {}
    const anchor = extractAnchor(loc.range)
    post('relocated', {
      cfi: loc.cfi || '',
      fraction: typeof loc.fraction === 'number' ? loc.fraction : 0,
      snippet: anchor.snippet,
      prefix: anchor.prefix,
      suffix: anchor.suffix,
    })
  } catch (err) { reportError('relocate', err) }
}

async function open(url, cfi) {
  try {
    if (view) { view.remove(); view = null }
    view = document.createElement('foliate-view')
    ;(document.body || document.documentElement).appendChild(view)
    view.addEventListener('relocate', onRelocate)
    await view.open(url)
    try { view.renderer.setAttribute('flow', 'paginated') } catch (_) {}
    applyStyleNow()
    await view.init({ lastLocation: cfi || null, showTextStart: !cfi })
    post('ready', { restoredCfi: cfi || '' })
  } catch (e) { reportError('open', e) }
}

async function goTo(cfi) { try { if (view) await view.goTo(cfi) } catch (e) { reportError('goTo', e) } }
async function goToFraction(f) { try { if (view) await view.goToFraction(Number(f) || 0) } catch (e) { reportError('goToFraction', e) } }
async function next() { try { if (view) await view.next() } catch (e) { reportError('next', e) } }
async function prev() { try { if (view) await view.prev() } catch (e) { reportError('prev', e) } }

function applyStyle(css) { styleCss = css || ''; applyStyleNow() }

// Re-anchor (ADR-008): tìm chuỗi bằng foliate search. Trả danh sách CFI khớp để Kotlin chọn
// (ReAnchorSelector). Thử fullQuery trước; nếu rỗng, thử snippetQuery (dự phòng R-01).
async function reAnchor(token, fullQuery, snippetQuery, _targetFraction) {
  const cfis = []
  try {
    if (view) {
      for (const q of [fullQuery, snippetQuery]) {
        if (!q) continue
        for await (const res of view.search({ query: q })) {
          if (res && res.subitems) {
            for (const s of res.subitems) if (s.cfi) cfis.push(s.cfi)
          } else if (res && res.cfi) {
            cfis.push(res.cfi)
          }
        }
        try { view.clearSearch() } catch (_) {}
        if (cfis.length) break // đã có kết quả ở fullQuery thì không cần snippetQuery
      }
    }
  } catch (e) { reportError('reAnchor', e) }
  post('reanchorResult', { token, cfis })
}

// Báo bridgeReady NHƯNG chờ tới khi window.kmpJsBridge được chèn (compose-webview-multiplatform
// chèn sau khi module này có thể đã chạy → tránh mất tín hiệu). Poll ngắn, tối đa ~5s.
function sendReady(attempt) {
  attempt = attempt || 0
  if (window.kmpJsBridge && typeof window.kmpJsBridge.callNative === 'function') {
    post('bridgeReady', {})
  } else if (attempt < 100) {
    setTimeout(function () { sendReady(attempt + 1) }, 50)
  }
}

// ping(): Kotlin gọi sau onPageFinished để yêu cầu gửi lại bridgeReady (phòng khi tín hiệu đầu mất).
window.sepia = { open, goTo, goToFraction, next, prev, applyStyle, reAnchor, ping: function () { sendReady(0) } }

sendReady(0)
