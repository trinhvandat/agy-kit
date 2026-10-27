"""Sepia PDF → EPUB pipeline (chạy trên máy tính, tách rời app KMP).

Mốc 0 chỉ có bước `detect` (phân loại PDF theo trang/span). Các bước
extract/reflow/build_epub thuộc Mốc 1 (xem docs/07-roadmap.md).
"""

# Phiên bản pipeline — ghi vào EPUB để app biết bản dựng (Book.pipelineVersion).
# v2 (Mốc 1b): định tuyến engine + Docling cho scan_ocr + bỏ mục lục in sẵn → đầu ra đổi.
# v3: lọc dòng rác theo âm tiết Việt (cả hai engine) + bỏ tiêu đề chạy đầu trang (Docling).
# v4: bỏ tiêu đề chạy đầu trang TẮT mặc định (bbox không tách được header khỏi nhãn mục trong sách
#     tra cứu — spike-4 §v4) → giữ lại "Tên gọi:"/"LẤY HUYỆT"… vốn bị v3 xoá nhầm → đầu ra đổi.
# v5: route scan_ocr HYBRID — bố cục Docling + chữ Apple Vision từ cache (ADR-009) khi có cache;
#     không có cache → giữ v4 (lớp chữ ẩn ABBYY). Chữ sách scan đúng hơn hẳn (SPIKE-5 WER→3.9%).
# v6: vá rò lớp chữ ABBYY ở route hybrid — trên trang CÓ cache, khối không nhận dòng Vision nào thì
#     BỎ (không lấy item.text ABBYY); picture không chữ Vision → ảnh không caption; dòng Vision
#     "trôi" gom thành đoạn riêng chèn theo vị trí (không nhét vào khối khác cột). Trước đây v5 rò
#     ~8.5k từ ABBYY vào EPUB (độ phủ 107%). → đầu ra trang scan có cache đổi (SPIKE-5 v5.1).
# v7: bất biến A MỞ sang **ô bảng** — v6 còn chừa bảng: <td> giữ lớp chữ ABBYY (41 bảng, ~9.2k từ)
#     và dòng Vision vùng bảng "trôi" thành đoạn nhân đôi. Nay bảng là target: dòng Vision gán vào
#     ô theo bbox ô (TableCell.bbox) → ô mang chữ Vision; bảng trên trang CÓ cache không có dòng
#     Vision nào → BỎ (không lấy lưới ABBYY). Trang KHÔNG cache vẫn giữ lưới ABBYY (fallback v4).
#     → đầu ra trang scan có cache (có bảng) đổi (SPIKE-5 v5.1 đo trên TOÀN BỘ text EPUB).
PIPELINE_VERSION = 7

__all__ = ["PIPELINE_VERSION"]
