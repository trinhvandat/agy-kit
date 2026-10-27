// Cầu nối foliate-js ↔ Kotlin cho Sepia (SPIKE-1, docs/02 §6, ADR-001/008, Mốc 3a).
//
// Kotlin → JS: window.sepia.open(url, cfi?) / goTo(cfi) / goToFraction(f) / next() / prev()
//              / applyStyle(css) / reAnchor(fullQuery, snippetQuery, targetFraction) / clearSelection()
// JS → Kotlin (qua window.kmpJsBridge.callNative của compose-webview-multiplatform):
//              ready{} · relocated{cfi,fraction,snippet,prefix,suffix} · error{where,message}
//              · reanchorResult{token, cfis:[...]}
//              · tap{zone:'left'|'center'|'right'}            (chạm đơn, không link/không đang chọn)
//              · selection{cfi,text,prefix,suffix,rect:{x,y,w,h}} · selectionCleared{}
//
// Cử chỉ (Mốc 3a): VUỐT lật trang do paginator.js tự xử lý (touch* trên doc trong iframe) —
// KHÔNG lặp lại ở đây. TAP đơn được quy về khung nhìn TRANG CHỦ (iframe rộng hơn màn hình theo
// số cột) rồi báo zone 30/40/30; Kotlin quyết hành động (trái=prev, giữa=toggle thanh, phải=next).
// Vùng chọn do WebView/paginator theo dõi (tự cuộn sang trang khi chọn vắt trang); ta chỉ đọc +
// báo CFI (view.getCFI) + neo prefix/suffix (NFC + gộp khoảng trắng, docs/04 §3.1).

import './foliate/view.js' // định nghĩa <foliate-view>

const SNIPPET_LEN = 64
const CTX_LEN = 32
// Vùng tap theo bề ngang TRANG CHỦ: [0,30%)=trái, [30%,70%)=giữa, [70%,100%]=phải.
const TAP_LEFT_FRACTION = 0.3
const TAP_RIGHT_FRACTION = 0.7
const SELECTION_DEBOUNCE_MS = 250
const SELECTION_CTX_LEN = 32 // độ dài prefix/suffix của vùng chọn (ký tự, sau chuẩn hoá)
// Cú chạm xoá vùng chọn thường tới SAU khi WebView đã tự huỷ selection → 'click' thấy selection rỗng.
// Nuốt tap trong khoảng này sau khi selection vừa bị xoá để tránh lật trang ngoài ý muốn (ca f).
const TAP_AFTER_CLEAR_GUARD_MS = 400

let view = null
let styleCss = '' // CSS theme hiện hành (Sepia…) do Kotlin đẩy xuống
let selectionActive = false // đang có vùng chọn không rỗng (đã báo lên Kotlin)?
let selectionClearedAt = 0 // mốc thời gian (ms) selection chuyển không-rỗng → rỗng
let selectionTimer = null // debounce post 'selection'

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

// Chuẩn hoá NFC + gộp khoảng trắng + cắt đầu/cuối — khớp AnchorText.normalize phía Kotlin (docs/04 §3.1).
function normalize(s) {
  return (s || '').normalize('NFC').replace(/\s+/g, ' ').trim()
}

// Lấy phần tử iframe (trong khung TRANG CHỦ) chứa một document của section.
// sandbox 'allow-same-origin' + cùng origin https → frameElement truy cập được.
function frameOf(doc) {
  try { return doc && doc.defaultView && doc.defaultView.frameElement } catch (_) { return null }
}

// Quy một điểm trong iframe-doc về toạ độ TRANG CHỦ. getBoundingClientRect của iframe đã phản ánh
// dịch/cuộn của paginator (kể cả trang ≥10) → cộng thẳng là ra (tránh bẫy toạ độ iframe, ca a).
function toHostX(doc, clientX) {
  const fe = frameOf(doc)
  return fe ? fe.getBoundingClientRect().left + clientX : clientX
}

function toHostRect(doc, rect) {
  const fe = frameOf(doc)
  const off = fe ? fe.getBoundingClientRect() : { left: 0, top: 0 }
  return { x: off.left + rect.left, y: off.top + rect.top, w: rect.width, h: rect.height }
}

function zoneForHostX(hostX) {
  const w = window.innerWidth || document.documentElement.clientWidth || 1
  const f = hostX / w
  if (f < TAP_LEFT_FRACTION) return 'left'
  if (f >= TAP_RIGHT_FRACTION) return 'right'
  return 'center'
}

function selectionOf(doc) {
  try { return doc.getSelection ? doc.getSelection() : doc.defaultView.getSelection() } catch (_) { return null }
}

function isNonEmpty(sel) {
  return !!(sel && sel.rangeCount > 0 && !sel.isCollapsed && String(sel).trim().length > 0)
}

// Ngữ cảnh prefix/suffix quanh vùng chọn — XUYÊN nhiều text node (dùng Range.toString qua ranh giới
// <b>/<i>/đoạn), khác extractAnchor (chỉ trong một node). Chuẩn hoá rồi cắt về SELECTION_CTX_LEN.
function contextBefore(doc, range) {
  try {
    const r = doc.createRange()
    r.selectNodeContents(doc.body || doc.documentElement)
    r.setEnd(range.startContainer, range.startOffset)
    return normalize(r.toString()).slice(-SELECTION_CTX_LEN)
  } catch (_) { return '' }
}

function contextAfter(doc, range) {
  try {
    const r = doc.createRange()
    r.selectNodeContents(doc.body || doc.documentElement)
    r.setStart(range.endContainer, range.endOffset)
    return normalize(r.toString()).slice(0, SELECTION_CTX_LEN)
  } catch (_) { return '' }
}

function postSelection(doc, index) {
  try {
    const sel = selectionOf(doc)
    if (!isNonEmpty(sel)) return
    const range = sel.getRangeAt(0)
    const text = normalize(String(sel))
    if (!text) return
    const cfi = view ? view.getCFI(index, range) : ''
    post('selection', {
      cfi: cfi || '',
      text,
      prefix: contextBefore(doc, range),
      suffix: contextAfter(doc, range),
      rect: toHostRect(doc, range.getBoundingClientRect()),
    })
  } catch (e) { reportError('selection', e) }
}

function onSelectionChange(doc, index) {
  const sel = selectionOf(doc)
  if (isNonEmpty(sel)) {
    selectionActive = true
    if (selectionTimer) clearTimeout(selectionTimer)
    selectionTimer = setTimeout(function () { postSelection(doc, index) }, SELECTION_DEBOUNCE_MS)
  } else if (selectionActive) {
    // chỉ báo khi CHUYỂN không-rỗng → rỗng (selectionchange nổ rất nhiều lần khi rỗng)
    selectionActive = false
    selectionClearedAt = Date.now()
    if (selectionTimer) { clearTimeout(selectionTimer); selectionTimer = null }
    post('selectionCleared', {})
  }
}

function onDocClick(doc, e) {
  try {
    // Link/chú thích: để foliate xử lý (view.js đã preventDefault cho <a[href]>).
    if (e.target && e.target.closest && e.target.closest('a[href]')) return
    const sel = selectionOf(doc)
    if (isNonEmpty(sel)) {
      // Còn selection lúc click → bỏ chọn, KHÔNG lật (ca f). removeAllRanges kéo selectionchange.
      sel.removeAllRanges()
      return
    }
    // Cú chạm vừa xoá vùng chọn: WebView thu gọn selection ĐỒNG BỘ trước 'click', nhưng
    // 'selectionchange' lại chạy BẤT ĐỒNG BỘ (sau click) → selectionClearedAt có thể chưa kịp cập nhật.
    // Vì vậy phải xét cả cờ selectionActive (code còn coi là đang chọn) để nuốt đúng cú chạm này (ca f).
    if (selectionActive || Date.now() - selectionClearedAt < TAP_AFTER_CLEAR_GUARD_MS) {
      selectionActive = false
      selectionClearedAt = Date.now()
      if (selectionTimer) { clearTimeout(selectionTimer); selectionTimer = null }
      post('selectionCleared', {})
      return
    }
    post('tap', { zone: zoneForHostX(toHostX(doc, e.clientX)) })
  } catch (err) { reportError('tap', err) }
}

// Mỗi section ('load') nạp vào iframe một doc mới → gắn listener tap + selection cho doc đó.
function onLoad(e) {
  try {
    const detail = e.detail || {}
    const doc = detail.doc
    const index = detail.index
    if (!doc) return
    doc.addEventListener('click', function (ev) { onDocClick(doc, ev) })
    doc.addEventListener('selectionchange', function () { onSelectionChange(doc, index) })
  } catch (err) { reportError('load', err) }
}

async function open(url, cfi) {
  try {
    if (view) { view.remove(); view = null }
    selectionActive = false
    selectionClearedAt = 0
    if (selectionTimer) { clearTimeout(selectionTimer); selectionTimer = null }
    view = document.createElement('foliate-view')
    ;(document.body || document.documentElement).appendChild(view)
    view.addEventListener('relocate', onRelocate)
    view.addEventListener('load', onLoad)
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

// Xoá vùng chọn hiện hành (Kotlin gọi khi đóng thanh chọn chữ ở 3b). Quét mọi doc đang hiển thị.
function clearSelection() {
  try {
    const contents = (view && view.renderer && view.renderer.getContents) ? view.renderer.getContents() : []
    for (const c of contents) {
      const sel = c && c.doc ? selectionOf(c.doc) : null
      if (sel) sel.removeAllRanges()
    }
  } catch (e) { reportError('clearSelection', e) }
}

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
window.sepia = {
  open, goTo, goToFraction, next, prev, applyStyle, reAnchor, clearSelection,
  ping: function () { sendReady(0) },
}

sendReady(0)
