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
# v8: CHIA NHỎ file XHTML cho nhẹ trên điện thoại — gộp các mục liên tiếp tới ~10k ký tự/file, tách
#     ở ranh giới heading (coarsest, vd h1; cấp sâu hơn chỉ tách khi gần trần), không cắt đôi
#     đoạn/bảng/ảnh. Trước đây chỉ ~7 file ~50k ký tự; nay ~40–80 file. Chỉ đổi ranh giới file XHTML
#     (nội dung block/bất biến A/B không đổi) → đầu ra đổi (nhánh display-qa).
# v9: SẠCH HIỂN THỊ (nhánh clean-display, issue #20). (1) Bỏ ĐỒ ĐẠC (tiêu đề chạy + số trang) ngay ở
#     mức DÒNG VISION theo bbox, trước khi gán khối — route hybrid trước đây để lọt ~79 dòng/trang
#     vào thân bài (khối Docling không mang top_ratio nên drop_running_headers không chạy). Bất biến
#     B mở thành assigned + floating + **furniture** = tổng dòng cache. (2) drop_printed_toc nhận
#     thêm dấu dẫn "_" (OCR của dãy chấm) → bỏ mục lục in sẵn p21/p61/p85. (3) "»"/"®" dẫn đầu dòng
#     → "• " (gạch đầu dòng OCR sai). (4) Bảng ≥4 cột: hàng đầu = <thead>, ô mang data-label →
#     app hiện dạng "thẻ" trên màn hẹp; tr break-inside avoid. → đầu ra đổi.
PIPELINE_VERSION = 9

__all__ = ["PIPELINE_VERSION"]
