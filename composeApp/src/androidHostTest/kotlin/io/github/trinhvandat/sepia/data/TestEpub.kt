package io.github.trinhvandat.sepia.data

import java.io.ByteArrayOutputStream
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

/** Dựng byte EPUB tối thiểu trong test (tránh commit file .epub — .gitignore chặn *.epub). */
object TestEpub {
    fun bytes(
        identifier: String? = "sepia:deadbeef",
        title: String = "Sách Thử",
        author: String? = "Tác Giả",
        pipelineVersion: Int? = 2,
        sourcePdf: String? = "nguon.pdf",
        // Nội dung thừa để contentHash đổi giữa các "bản build" khác nhau.
        filler: String = "",
    ): ByteArray {
        val opf = buildString {
            append("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n")
            append("<package xmlns=\"http://www.idpf.org/2007/opf\" version=\"3.0\" unique-identifier=\"id\">\n")
            append("<metadata xmlns:dc=\"http://purl.org/dc/elements/1.1/\">\n")
            if (identifier != null) append("<dc:identifier id=\"id\">$identifier</dc:identifier>\n")
            append("<dc:title>$title</dc:title>\n")
            if (author != null) append("<dc:creator>$author</dc:creator>\n")
            if (pipelineVersion != null) append("<meta property=\"sepia:pipeline-version\">$pipelineVersion</meta>\n")
            if (sourcePdf != null) append("<meta property=\"sepia:source-pdf\">$sourcePdf</meta>\n")
            if (filler.isNotEmpty()) append("<meta property=\"sepia:filler\">$filler</meta>\n")
            append("</metadata>\n<manifest/>\n<spine/>\n</package>\n")
        }
        val container = """
            <?xml version="1.0"?>
            <container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
              <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
            </container>
        """.trimIndent()

        val out = ByteArrayOutputStream()
        ZipOutputStream(out).use { zos ->
            zos.putNextEntry(ZipEntry("mimetype"))
            zos.write("application/epub+zip".toByteArray())
            zos.closeEntry()
            zos.putNextEntry(ZipEntry("META-INF/container.xml"))
            zos.write(container.toByteArray())
            zos.closeEntry()
            zos.putNextEntry(ZipEntry("OEBPS/content.opf"))
            zos.write(opf.toByteArray())
            zos.closeEntry()
        }
        return out.toByteArray()
    }
}
