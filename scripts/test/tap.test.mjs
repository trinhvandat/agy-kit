// Test thuần cho nhận diện chạm đơn (assets/reader/tap.js) — chạy bằng `node --test scripts/test/`.
// KHÔNG thêm phụ thuộc npm (chỉ node:test / node:assert). Phân biệt TAP (lật trang) với VUỐT / NHẤN GIỮ
// / ĐA CHẠM để sửa lỗi bật-về-trang-cũ (fix-tap-bounce): tap mới được chặn snap + chặn click trong bridge.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { isTap, TAP_MAX_MOVE_PX, TAP_MAX_MS } from '../../androidApp/src/main/assets/reader/tap.js'

const cases = [
  // name, gesture, expected
  ['chạm gọn (0px, 80ms, 1 ngón) → tap', { dx: 0, dy: 0, dt: 80, touches: 1 }, true],
  ['rung tay nhỏ (6px, 120ms) → tap', { dx: 6, dy: -4, dt: 120, touches: 1 }, true],
  ['đúng ngưỡng khoảng cách (10px) → tap', { dx: 10, dy: 0, dt: 100, touches: 1 }, true],
  ['đúng ngưỡng thời gian (350ms) → tap', { dx: 2, dy: 2, dt: TAP_MAX_MS, touches: 1 }, true],
  ['dy âm nhỏ → tap (dùng trị tuyệt đối)', { dx: -3, dy: -9, dt: 90, touches: 1 }, true],
  ['vuốt ngang (120px) → KHÔNG tap', { dx: 120, dy: 5, dt: 150, touches: 1 }, false],
  ['vuốt dọc (0px ngang, 40px dọc) → KHÔNG tap', { dx: 0, dy: 40, dt: 150, touches: 1 }, false],
  ['quá ngưỡng khoảng cách (11px) → KHÔNG tap', { dx: 11, dy: 0, dt: 100, touches: 1 }, false],
  ['nhấn giữ chọn chữ (4px, 600ms) → KHÔNG tap', { dx: 4, dy: 4, dt: 600, touches: 1 }, false],
  ['quá ngưỡng thời gian (351ms) → KHÔNG tap', { dx: 1, dy: 1, dt: TAP_MAX_MS + 1, touches: 1 }, false],
  ['hai ngón (zoom) dù gọn → KHÔNG tap', { dx: 2, dy: 2, dt: 90, touches: 2 }, false],
  ['không ngón → KHÔNG tap', { dx: 0, dy: 0, dt: 90, touches: 0 }, false],
]

for (const [name, g, expected] of cases) {
  test(`tap: ${name}`, () => {
    assert.equal(isTap(g), expected)
  })
}

test('tap: null/undefined an toàn → false', () => {
  assert.equal(isTap(null), false)
  assert.equal(isTap(undefined), false)
})

test('tap: ngưỡng tuỳ chỉnh qua opts', () => {
  // Nới ngưỡng khoảng cách lên 20px: 15px giờ là tap.
  assert.equal(isTap({ dx: 15, dy: 0, dt: 100, touches: 1 }), false)
  assert.equal(isTap({ dx: 15, dy: 0, dt: 100, touches: 1 }, { maxMovePx: 20 }), true)
  // Siết ngưỡng thời gian xuống 50ms: 80ms không còn là tap.
  assert.equal(isTap({ dx: 0, dy: 0, dt: 80, touches: 1 }, { maxMs: 50 }), false)
})

test('tap: hằng số ngưỡng mặc định đúng tài liệu (10px / 350ms)', () => {
  assert.equal(TAP_MAX_MOVE_PX, 10)
  assert.equal(TAP_MAX_MS, 350)
})
