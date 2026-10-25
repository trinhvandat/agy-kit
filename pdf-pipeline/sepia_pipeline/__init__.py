"""Sepia PDF → EPUB pipeline (chạy trên máy tính, tách rời app KMP).

Mốc 0 chỉ có bước `detect` (phân loại PDF theo trang/span). Các bước
extract/reflow/build_epub thuộc Mốc 1 (xem docs/07-roadmap.md).
"""

# Phiên bản pipeline — ghi vào EPUB sau này để app biết bản dựng (Book.pipelineVersion).
PIPELINE_VERSION = 1

__all__ = ["PIPELINE_VERSION"]
