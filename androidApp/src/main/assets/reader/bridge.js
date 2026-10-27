// Cầu nối foliate-js ↔ Kotlin cho Sepia (SPIKE-1, docs/02 §6, ADR-001/008, Mốc 3a).
//
// Kotlin → JS: window.sepia.open(url, cfi?) / goTo(cfi) / goToFraction(f) / next() / prev()
//              / applyStyle(css) / reAnchor(fullQuery, snippetQuery, targetFraction) / clearSelection()
//              / setHighlights([{id,cfi,color}]) (thay toàn bộ tập) / removeHighlight(id)
// JS → Kotlin (qua window.kmpJsBridge.callNative của compose-webview-multiplatform):
//              ready{} · relocated{cfi,fraction,snippet,prefix,suffix} · error{where,message}
//              · reanchorResult{token, candidates:[{cfi,progress,text,exact}]}
//              · tap{zone:'left'|'center'|'right'}            (chạm đơn, không link/không đang chọn/không trúng highlight)
//              · selection{cfi,text,prefix,suffix,fraction,rect:{x,y,w,h}} · selectionCleared{}
//              · highlightTap{id, rect:{x,y,w,h}}             (chạm trúng một highlight)
//
// Cử chỉ (Mốc 3a): VUỐT lật trang do paginator.js tự xử lý (touch* trên doc trong iframe) —
// KHÔNG lặp lại ở đây. TAP đơn được quy về khung nhìn TRANG CHỦ (iframe rộng hơn màn hình theo
// số cột) rồi báo zone 30/40/30; Kotlin quyết hành động (trái=prev, giữa=toggle thanh, phải=next).
// Vùng chọn do WebView/paginator theo dõi (tự cuộn sang trang khi chọn vắt trang); ta chỉ đọc +
// báo CFI (view.getCFI) + neo prefix/suffix (NFC + gộp khoảng trắng, docs/04 §3.1).

import './foliate/view.js' // định nghĩa <foliate-view>
import { Overlayer } from './foliate/overlayer.js' // vẽ highlight (Overlayer.highlight)
import { computeAnchor } from './anchor.js' // logic neo thuần, test bằng node

const SNIPPET_LEN = 64
const CTX_LEN = 32
// Vùng tap theo bề ngang TRANG CHỦ: [0,30%)=trái, [30%,70%)=giữa, [70%,100%]=phải.
const TAP_LEFT_FRACTION = 0.3
const TAP_RIGHT_FRACTION = 0.7
const SELECTION_DEBOUNCE_MS = 250
const SELECTION_CTX_RAW = 500 // số ký tự THÔ lấy quanh vùng chọn trước khi tính neo (giới hạn chi phí)
// Cú chạm xoá vùng chọn thường tới SAU khi WebView đã tự huỷ selection → 'click' thấy selection rỗng.
// Nuốt tap trong khoảng này sau khi selection vừa bị xoá để tránh lật trang ngoài ý muốn (ca f).
const TAP_AFTER_CLEAR_GUARD_MS = 400

let view = null
let styleCss = '' // CSS theme hiện hành (Sepia…) do Kotlin đẩy xuống
let selectionActive = false // đang có vùng chọn không rỗng (đã báo lên Kotlin)?
let selectionClearedAt = 0 // mốc thời gian (ms) selection chuyển không-rỗng → rỗng
let selectionTimer = null // debounce post 'selection'
// Highlight (Mốc 3b): foliate addAnnotation dùng CFI làm value → map hai chiều id↔cfi để biết màu + báo tap.
const DEFAULT_HL_CSS = '#F2C94C' // màu dự phòng nếu thiếu
const hlById = new Map() // id -> {cfi, color}
const hlByCfi = new Map() // cfi -> id

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
      // Number.isFinite loại cả NaN (typeof NaN === 'number' nên check 'number' KHÔNG đủ; NaN →
      // JSON.stringify ra null → Kotlin parse lỗi). foliate có thể trả NaN lúc mở ở đầu sách.
      fraction: Number.isFinite(loc.fraction) ? loc.fraction : 0,
      snippet: anchor.snippet,
      prefix: anchor.prefix,
      suffix: anchor.suffix,
    })
  } catch (err) { reportError('relocate', err) }
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

// Văn bản THÔ ngay trước/sau vùng chọn — XUYÊN nhiều text node (Range.toString qua ranh giới
// <b>/<i>/đoạn). Lấy tối đa SELECTION_CTX_RAW ký tự để giới hạn chi phí; computeAnchor sẽ chuẩn hoá & cắt.
function rawBefore(doc, range) {
  try {
    const r = doc.createRange()
    r.selectNodeContents(doc.body || doc.documentElement)
    r.setEnd(range.startContainer, range.startOffset)
    return r.toString().slice(-SELECTION_CTX_RAW)
  } catch (_) { return '' }
}

function rawAfter(doc, range) {
  try {
    const r = doc.createRange()
    r.selectNodeContents(doc.body || doc.documentElement)
    r.setStart(range.endContainer, range.endOffset)
    return r.toString().slice(0, SELECTION_CTX_RAW)
  } catch (_) { return '' }
}

function currentFraction() {
  const f = view && view.lastLocation ? view.lastLocation.fraction : undefined
  return typeof f === 'number' ? f : 0
}

function postSelection(doc, index) {
  try {
    const sel = selectionOf(doc)
    if (!isNonEmpty(sel)) return
    const range = sel.getRangeAt(0)
    // Tính neo: giữ space ranh giới ở prefix/suffix (sửa lỗi review 3a) — logic thuần ở anchor.js.
    const a = computeAnchor(rawBefore(doc, range), String(sel), rawAfter(doc, range))
    if (!a.text) return
    const cfi = view ? view.getCFI(index, range) : ''
    post('selection', {
      cfi: cfi || '',
      text: a.text,
      prefix: a.prefix,
      suffix: a.suffix,
      fraction: currentFraction(),
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
    // Chạm trúng highlight → view.js tự phát 'show-annotation' (→ 'highlightTap'); KHÔNG lật/toggle.
    if (hitHighlight(doc, e)) return
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
    // Highlight: màu khi vẽ; vẽ lại khi section mới nạp; báo khi chạm.
    view.addEventListener('draw-annotation', onDrawAnnotation)
    view.addEventListener('create-overlay', redrawHighlights)
    view.addEventListener('show-annotation', onShowAnnotation)
    hlById.clear()
    hlByCfi.clear()
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

// --- Highlight (Mốc 3b) -----------------------------------------------------------------------
// foliate addAnnotation({value: cfi}) → khi đến section chứa cfi, phát 'draw-annotation' để ta vẽ
// bằng Overlayer.highlight với màu. 'create-overlay' (section vừa nạp) → vẽ lại toàn bộ. Chạm overlay
// → view.js phát 'show-annotation' {value, range} → ta báo 'highlightTap'{id, rect}.

function onDrawAnnotation(e) {
  try {
    const { draw, annotation } = e.detail || {}
    const id = hlByCfi.get(annotation && annotation.value)
    const color = (id && hlById.get(id)) ? hlById.get(id).color : DEFAULT_HL_CSS
    draw(Overlayer.highlight, { color: color || DEFAULT_HL_CSS })
  } catch (err) { reportError('drawAnnotation', err) }
}

function redrawHighlights() {
  if (!view) return
  for (const h of hlById.values()) {
    try { view.addAnnotation({ value: h.cfi }) } catch (_) { /* section khác chưa nạp → bỏ qua */ }
  }
}

function onShowAnnotation(e) {
  try {
    const { value, range } = e.detail || {}
    const id = hlByCfi.get(value)
    if (!id) return
    const doc = range && range.startContainer ? range.startContainer.ownerDocument : null
    const rect = (doc && range) ? toHostRect(doc, range.getBoundingClientRect()) : { x: 0, y: 0, w: 0, h: 0 }
    post('highlightTap', { id, rect })
  } catch (err) { reportError('showAnnotation', err) }
}

// Có chạm trúng highlight không? Dùng overlayer.hitTest của chính section đang chạm.
function hitHighlight(doc, e) {
  try {
    if (!view || !view.renderer || !view.renderer.getContents) return false
    const entry = view.renderer.getContents().find(function (c) { return c.doc === doc })
    if (!entry || !entry.overlayer) return false
    const hit = entry.overlayer.hitTest(e)
    const value = hit && hit[0]
    return !!(value && hlByCfi.has(value))
  } catch (_) { return false }
}

// Thay TOÀN BỘ tập highlight (Kotlin đẩy xuống mỗi khi danh sách đổi). list: [{id, cfi, color}].
function setHighlights(list) {
  try {
    // bỏ cái cũ không còn trong tập mới
    const next = new Map()
    for (const item of (list || [])) if (item && item.id && item.cfi) next.set(item.id, item)
    for (const [id, h] of hlById) {
      if (!next.has(id)) { try { if (view) view.deleteAnnotation({ value: h.cfi }) } catch (_) {} }
    }
    hlById.clear()
    hlByCfi.clear()
    for (const item of next.values()) {
      hlById.set(item.id, { cfi: item.cfi, color: item.color })
      hlByCfi.set(item.cfi, item.id)
    }
    redrawHighlights()
  } catch (e) { reportError('setHighlights', e) }
}

function removeHighlight(id) {
  try {
    const h = hlById.get(id)
    if (!h) return
    try { if (view) view.deleteAnnotation({ value: h.cfi }) } catch (_) {}
    hlById.delete(id)
    hlByCfi.delete(h.cfi)
  } catch (e) { reportError('removeHighlight', e) }
}

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

// Re-anchor (ADR-008, docs/04 §3): tìm chuỗi bằng foliate search, trả **ứng viên** {cfi, progress,
// text, exact} để Kotlin CHỌN (ReAnchorSelector.chooseBest) — gần `progress` cũ nhất, không phải cứ
// lấy khớp ĐẦU TIÊN (foliate search bỏ dấu + bỏ hoa/thường → snippet ngắn khớp nhiều chỗ; lấy chỗ
// đầu = nhảy về đầu sách — lỗi hồi quy Mốc 2).
//
// Hai lượt: (1) fullQuery = prefix+snippet+suffix (ngữ cảnh dài → tin cậy, đánh dấu exact); nếu rỗng
// (2) snippetQuery (ngắn, hay khớp nhiều chỗ → KHÔNG exact; Kotlin lọc theo tương đồng bỏ-dấu).
// `progress` mỗi ứng viên = tiến độ section chứa nó (foliate phát {progress} trước mỗi section).

function matchText(excerpt) {
  return (excerpt && excerpt.match) || ''
}

async function collectMatches(query, exact, targetFraction, out) {
  let sectionProgress = typeof targetFraction === 'number' ? targetFraction : 0
  for await (const res of view.search({ query })) {
    if (res && typeof res.progress === 'number' && !res.subitems) {
      sectionProgress = res.progress // tiến độ section sắp tới
      continue
    }
    const subs = res && res.subitems ? res.subitems : (res && res.cfi ? [res] : [])
    for (const s of subs) {
      if (s && s.cfi) out.push({ cfi: s.cfi, progress: sectionProgress, text: matchText(s.excerpt), exact })
    }
  }
  try { view.clearSearch() } catch (_) {}
}

async function reAnchor(token, fullQuery, snippetQuery, targetFraction) {
  const candidates = []
  try {
    if (view) {
      if (fullQuery) await collectMatches(fullQuery, true, targetFraction, candidates)
      if (!candidates.length && snippetQuery) {
        await collectMatches(snippetQuery, false, targetFraction, candidates)
      }
    }
  } catch (e) { reportError('reAnchor', e) }
  post('reanchorResult', { token, candidates })
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
  setHighlights, removeHighlight,
  ping: function () { sendReady(0) },
}

sendReady(0)
