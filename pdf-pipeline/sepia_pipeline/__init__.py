"""Sepia PDF → EPUB pipeline (chạy trên máy tính, tách rời app KMP).

Mốc 0 chỉ có bước `detect` (phân loại PDF theo trang/span). Các bước
extract/reflow/build_epub thuộc Mốc 1 (xem docs/07-roadmap.md).
"""

# Phiên bản pipeline — ghi vào EPUB để app biết bản dựng (Book.pipelineVersion).
# v2 (Mốc 1b): định tuyến engine + Docling cho scan_ocr + bỏ mục lục in sẵn → đầu ra đổi.
# v3: lọc dòng rác theo âm tiết Việt (cả hai engine) + bỏ tiêu đề chạy đầu trang (Docling).
PIPELINE_VERSION = 3

__all__ = ["PIPELINE_VERSION"]
