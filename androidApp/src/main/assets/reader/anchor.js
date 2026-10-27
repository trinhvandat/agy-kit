// Logic tính neo vùng chọn — THUẦN (không DOM) để test bằng `node --test` (xem scripts/test/anchor.test.mjs).
//
// Khớp `AnchorText` phía Kotlin (docs/04 §3.1): NFC + gộp khoảng trắng.
// KHÁC biệt quan trọng (sửa lỗi review 3a): prefix/suffix **GIỮ khoảng trắng ranh giới** (không trim),
// và khoảng trắng đầu/cuối của chính vùng chọn được **chuyển sang prefix/suffix**. Nhờ vậy
// `fullQuery = normalize(prefix + textSnippet + suffix)` KHÔNG mất space giữa các mảnh
// (vd "Huyệt " + "Hợp cốc" + " nằm ở" → "Huyệt Hợp cốc nằm ở", khớp sách — không còn "HuyệtHợp cốcnằm ở").

export const CTX_LEN = 32

/** NFC + gộp mọi khoảng trắng về một space. KHÔNG trim (giữ space đầu/cuối). */
export function normCollapse(s) {
  return (s || '').normalize('NFC').replace(/\s+/g, ' ')
}

/** NFC + gộp khoảng trắng + trim — khớp `AnchorText.normalize` (Kotlin). */
export function normTrim(s) {
  return normCollapse(s).trim()
}

/**
 * Tính neo từ 3 mảnh thô quanh vùng chọn.
 * @param {string} beforeRaw  văn bản ngay TRƯỚC vùng chọn (lấy đuôi làm prefix)
 * @param {string} selectedRaw chính vùng chọn
 * @param {string} afterRaw   văn bản ngay SAU vùng chọn (lấy đầu làm suffix)
 * @param {number} ctxLen     độ dài tối đa prefix/suffix (mặc định CTX_LEN)
 * @returns {{text:string, prefix:string, suffix:string}}
 *   prefix/suffix đã chuẩn hoá (giữ space ranh giới), cắt ctxLen; text = vùng chọn đã bỏ space đầu/cuối.
 */
export function computeAnchor(beforeRaw, selectedRaw, afterRaw, ctxLen = CTX_LEN) {
  let before = normCollapse(beforeRaw)
  let sel = normCollapse(selectedRaw)
  let after = normCollapse(afterRaw)
  // normCollapse đã gộp về tối đa một space mỗi bên → chuyển space đầu/cuối của sel sang prefix/suffix.
  if (sel.startsWith(' ')) { before += ' '; sel = sel.slice(1) }
  if (sel.endsWith(' ')) { after = ' ' + after; sel = sel.slice(0, -1) }
  return {
    text: sel,
    prefix: before.slice(-ctxLen),
    suffix: after.slice(0, ctxLen),
  }
}
