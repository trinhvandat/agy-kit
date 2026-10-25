# Biến thể: Đông y

> **Biến thể đầu tiên** của bản nền Sepia, đồng thời là **kho sách dogfood/test** trong giai đoạn đầu.
> Mọi thứ trong file này là **đặc thù lĩnh vực** — **không** thuộc lõi (xem [../01-requirements.md](../01-requirements.md), [../02-architecture.md](../02-architecture.md) §7).
> Cập nhật: 2026-10-26.

## 1. Người dùng mục tiêu

- **Giai đoạn đầu**: chính tác giả — đang học Đông y, có nhiều sách PDF, cần đọc dịu mắt hằng ngày trên điện thoại.
- **Về sau (một hướng thương mại hóa)**: sinh viên Đông y năm 1–2. Đây là hướng đi của **riêng biến thể Đông y**, không phải mục tiêu của lõi.

## 2. Đặc thù kho sách Đông y

- **Chữ Hán phồn thể (Traditional)** xuất hiện nhiều (tên vị thuốc, huyệt, trích dẫn cổ văn) → cần fallback font CJK **ưu tiên phồn thể**.
- **Nhiều trang hình/sơ đồ**: hình huyệt vị, kinh lạc, bảng phân loại vị thuốc → thuộc nhóm "trang ảnh" (US-A6): nhúng nguyên trang thành ảnh, không ép reflow.
- **Có thể có sách dùng font cũ TCVN3/VNI** (sách số hóa đời cũ) → dùng nhánh chuyển mã của pipeline (xem [../03-pdf-pipeline.md](../03-pdf-pipeline.md) §3–4).
- Trộn **Việt + Hán** trong cùng trang/đoạn là bình thường → kiểm `quality.py` phải whitelist dải CJK (đã có ở lõi).

## 3. Tính năng riêng (giai đoạn sau, bật bằng feature flag)

Tất cả nằm **ngoài lõi**, cắm qua điểm mở rộng US-F2 ([../01-requirements.md](../01-requirements.md)):

- **Tra huyệt**: tra cứu huyệt vị (tên, vị trí, kinh thuộc) từ dữ liệu đi kèm biến thể.
- **Tra từ Hán Việt**: tra nghĩa/âm Hán Việt cho chữ Hán bôi chọn trong lúc đọc.
- **Nhãn gợi ý sẵn cho ghi chú** (US-F1): bộ nhãn/chủ đề mặc định theo lĩnh vực — *kinh lạc, tạng phủ, huyệt vị, bệnh chứng* — nạp như **dữ liệu của biến thể**, không hardcode trong lõi (lõi chỉ biết "nhãn/chủ đề do người dùng đặt").
- **Gói từ điển / dữ liệu tra cứu**: đóng gói cùng content pack của biến thể.

## 4. Cấu hình `VariantConfig` dự kiến

| Trường | Giá trị cho biến thể Đông y |
|--------|------------------------------|
| `appName` | (vd) "Sepia Đông y" |
| Màu thương hiệu | (đặt sau) |
| Theme mặc định | Sepia |
| **Font fallback theo hệ chữ** (app chèn qua CSS) | ưu tiên **phồn thể**: `["Literata", "Noto Serif", "Noto Serif CJK TC", "Noto Serif CJK SC", "serif"]` (có thể dùng font CJK hệ thống thay vì nhúng) |
| Feature flags | `tra_huyet = true`, `tra_han_viet = true`, `goi_y_nhan = true` (giai đoạn đầu: tất cả `false`) |
| Content pack | thư mục `.epub` Đông y + `manifest.json` + (sau) dữ liệu tra cứu |

> Lưu ý: đây chỉ là **cấu hình + dữ liệu**; thêm biến thể này **không sửa lõi** (ADR-007).

> **Profile font của pipeline** (chỉ để **đọc thử bằng app EPUB ngoài** như KOReader — **không** ảnh hưởng app Sepia): profile `dongy` trong file cấu hình của `pdf-pipeline/`, ưu tiên phồn thể, trùng danh sách fallback ở trên. Chạy `--font-profile dongy` để ghi tên font cụ thể vào EPUB. Trong app Sepia, font **luôn** theo `VariantConfig` này, không theo CSS của EPUB (xem [../03-pdf-pipeline.md](../03-pdf-pipeline.md) §8).

## 5. Vai trò trong dogfood/test của lõi

- Kho sách Đông y thật là **bộ dữ liệu đầu vào cho SPIKE-0** (kiểm kê kho PDF: tỷ lệ text/scan/font cũ) và **SPIKE-4** (chạy pipeline trên 3 cuốn đại diện, đọc thử bằng KOReader) — xem [../06-risks.md](../06-risks.md), [../07-roadmap.md](../07-roadmap.md).
- Vì là người dùng đầu tiên, các vấn đề gặp khi đọc sách Đông y thật sẽ **định hướng cải tiến lõi** — nhưng mọi khái niệm đặc thù phát sinh phải quay về **file biến thể này**, không rò rỉ vào docs/code lõi.
