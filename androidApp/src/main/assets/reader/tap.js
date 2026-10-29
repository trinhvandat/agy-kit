// Nhận diện TAP (chạm đơn) thuần — tách khỏi bridge.js để test bằng node (`node --test`).
// KHÔNG phụ thuộc DOM/npm. Dùng cho fix-tap-bounce: phân biệt một cú CHẠM (lật trang) với một cú
// VUỐT (paginator tự snap) hay NHẤN GIỮ (chọn chữ). Tap = dịch chuyển nhỏ VÀ nhanh VÀ một ngón.

// Ngưỡng mặc định (px / ms). Vuốt thật vượt ngưỡng khoảng cách; nhấn giữ chọn chữ vượt ngưỡng thời gian.
export const TAP_MAX_MOVE_PX = 10
export const TAP_MAX_MS = 350

// g = {dx, dy, dt, touches}: dx/dy = |dịch chuyển| (px), dt = thời gian chạm (ms), touches = số ngón.
// opts (tuỳ chọn): {maxMovePx, maxMs} để test ngưỡng. Trả true nếu là một cú chạm đơn.
export function isTap(g, opts) {
  const maxMove = (opts && typeof opts.maxMovePx === 'number') ? opts.maxMovePx : TAP_MAX_MOVE_PX
  const maxMs = (opts && typeof opts.maxMs === 'number') ? opts.maxMs : TAP_MAX_MS
  if (!g || g.touches !== 1) return false
  const dx = Math.abs(g.dx || 0)
  const dy = Math.abs(g.dy || 0)
  const dt = g.dt || 0
  return dx <= maxMove && dy <= maxMove && dt >= 0 && dt <= maxMs
}
