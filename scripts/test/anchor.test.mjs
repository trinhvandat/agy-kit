// Test thuần cho logic neo vùng chọn (assets/reader/anchor.js) — chạy bằng `node --test scripts/test/`.
// KHÔNG thêm phụ thuộc npm (chỉ dùng node:test / node:assert). Dùng chung fixture với test Kotlin
// (AnchorContractTest) để đảm bảo HỢP ĐỒNG JS↔Kotlin: neo do JS tạo, khi nối lại, là chuỗi con của
// văn bản section đã chuẩn hoá → re-anchor (foliate search) sẽ khớp.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { computeAnchor, normTrim } from '../../androidApp/src/main/assets/reader/anchor.js'

const here = dirname(fileURLToPath(import.meta.url))
const cases = JSON.parse(readFileSync(join(here, '../fixtures/anchor_cases.json'), 'utf8'))

for (const c of cases) {
  test(`anchor: ${c.name}`, () => {
    const a = computeAnchor(c.before, c.selected, c.after)
    assert.deepEqual(a, c.anchor, 'computeAnchor khác fixture')
    // Hợp đồng: nối prefix+text+suffix (chuẩn hoá) phải là chuỗi con của section (chuẩn hoá).
    const section = normTrim(c.before + c.selected + c.after)
    const query = normTrim(a.prefix + a.text + a.suffix)
    assert.ok(section.includes(query), `query "${query}" không nằm trong section "${section}"`)
  })
}
