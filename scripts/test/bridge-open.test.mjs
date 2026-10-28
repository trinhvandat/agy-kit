// Test cho bridge.js open() — fallback khi CFI lưu cũ không còn khớp DOM (content-pack đổi bản,
// ADR-008/fix-pack-reanchor). Chạy bằng `node --test scripts/test/`.
//
// bridge.js tĩnh import foliate/view.js, lớp View extends HTMLElement + customElements.define(...)
// chạy ngay lúc nạp module → cần global.HTMLElement/customElements TỐI THIỂU để import không ném,
// dù ta không dùng View thật (document.createElement('foliate-view') bên dưới trả view GIẢ do ta
// điều khiển). KHÔNG thêm phụ thuộc npm (không jsdom) — đây là "lightest test" cho phần DOM còn lại.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const bridgeUrl = `file://${join(here, '../../androidApp/src/main/assets/reader/bridge.js')}`

global.HTMLElement = class {}
global.customElements = { define() {} }
// text-walker.js dùng NodeFilter.SHOW_ELEMENT|SHOW_TEXT ở top-level (hằng số, không DOM thật cần cho test này).
global.NodeFilter = { SHOW_ELEMENT: 1, SHOW_TEXT: 4 }

const posts = []
const created = []
// Mỗi test lập trình hành vi init/open TRƯỚC khi gọi open() (reset ở đầu mỗi test).
let nextInitBehavior = () => Promise.resolve()
let nextOpenBehavior = () => Promise.resolve()

function makeFakeView() {
  const calls = { init: [], open: [] }
  const fake = {
    renderer: { setAttribute() {}, setStyles() {} },
    addEventListener() {},
    remove() {},
    async open(url) {
      calls.open.push(url)
      return nextOpenBehavior()
    },
    async init(opts) {
      calls.init.push(opts)
      return nextInitBehavior(calls.init.length)
    },
  }
  created.push({ fake, calls })
  return fake
}

global.document = {
  createElement(tag) {
    if (tag === 'foliate-view') return makeFakeView()
    throw new Error(`createElement không mong đợi: ${tag}`)
  },
  body: { appendChild() {} },
  documentElement: { appendChild() {} },
}

global.window = {
  kmpJsBridge: {
    callNative(method, json) { posts.push({ method, payload: JSON.parse(json) }) },
  },
  innerWidth: 400,
}

// Nạp bridge.js SAU khi đã gắn shim ở trên (side effect: định nghĩa window.sepia).
await import(bridgeUrl)

function reset() {
  posts.length = 0
  created.length = 0
  nextInitBehavior = () => Promise.resolve()
  nextOpenBehavior = () => Promise.resolve()
}

function readyPost() { return posts.find((p) => p.method === 'ready') }
function errorPost() { return posts.find((p) => p.method === 'error') }

test('open() với CFI hợp lệ: init một lần, ready cfiFailed=false', async () => {
  reset()
  await window.sepia.open('https://x/book.epub', 'epubcfi(/6/2!/4)')
  assert.equal(created.length, 1)
  assert.deepEqual(created[0].calls.init, [{ lastLocation: 'epubcfi(/6/2!/4)', showTextStart: false }])
  assert.deepEqual(readyPost().payload, { restoredCfi: 'epubcfi(/6/2!/4)', cfiFailed: false })
  assert.equal(errorPost(), undefined)
})

test('open() không CFI: init một lần ở đầu sách, ready cfiFailed=false', async () => {
  reset()
  await window.sepia.open('https://x/book.epub', null)
  assert.deepEqual(created[0].calls.init, [{ lastLocation: null, showTextStart: true }])
  assert.deepEqual(readyPost().payload, { restoredCfi: '', cfiFailed: false })
})

test('open() với CFI hỏng (view.init ném "setStart on Range"): fallback mở ở đầu + ready cfiFailed=true', async () => {
  reset()
  // Lượt init đầu tiên (dùng CFI) ném lỗi mô phỏng đúng ca lỗi thật (setStart trên Range cũ) —
  // lượt thứ hai (fallback, lastLocation: null) phải thành công.
  nextInitBehavior = (callIndex) =>
    callIndex === 1
      ? Promise.reject(new Error("Failed to execute 'setStart' on 'Range'"))
      : Promise.resolve()

  await window.sepia.open('https://x/book.epub', 'epubcfi(/stale)')

  assert.equal(created.length, 1, 'không tạo lại view — chỉ init lại trên view hiện có')
  assert.deepEqual(created[0].calls.init, [
    { lastLocation: 'epubcfi(/stale)', showTextStart: false },
    { lastLocation: null, showTextStart: true },
  ])
  // KHÔNG hiện banner lỗi (không có post 'error') — chỉ báo cfiFailed để Kotlin tự re-anchor bằng snippet.
  assert.equal(errorPost(), undefined, 'lỗi CFI không được rò ra reportError/banner')
  assert.deepEqual(readyPost().payload, { restoredCfi: '', cfiFailed: true })
})

test('open() lỗi thật (EPUB không mở được): vẫn báo error, KHÔNG post ready', async () => {
  reset()
  nextOpenBehavior = () => Promise.reject(new Error('EPUB hỏng'))

  await window.sepia.open('https://x/broken.epub', 'epubcfi(/6/2)')

  assert.equal(readyPost(), undefined, 'mở EPUB thất bại thật thì không được coi là ready')
  assert.equal(errorPost().payload.where, 'open')
  assert.match(errorPost().payload.message, /EPUB hỏng/)
})
