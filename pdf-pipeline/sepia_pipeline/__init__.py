"""Sepia PDF → EPUB pipeline (chạy trên máy tính, tách rời app KMP).

Mốc 0 chỉ có bước `detect` (phân loại PDF theo trang/span). Các bước
extract/reflow/build_epub thuộc Mốc 1 (xem docs/07-roadmap.md).
"""

# Phiên bản pipeline — ghi vào EPUB để app biết bản dựng (Book.pipelineVersion).
# v2 (Mốc 1b): định tuyến engine + Docling cho scan_ocr + bỏ mục lục in sẵn → đầu ra đổi.
# v3: lọc dòng rác theo âm tiết Việt (cả hai engine) + bỏ tiêu đề chạy đầu trang (Docling).
# v4: bỏ tiêu đề chạy đầu trang TẮT mặc định (bbox không tách được header khỏi nhãn mục trong sách
#     tra cứu — spike-4 §v4) → giữ lại "Tên gọi:"/"LẤY HUYỆT"… vốn bị v3 xoá nhầm → đầu ra đổi.
PIPELINE_VERSION = 4

__all__ = ["PIPELINE_VERSION"]
