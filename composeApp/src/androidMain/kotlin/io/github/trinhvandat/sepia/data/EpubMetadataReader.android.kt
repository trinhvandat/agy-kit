package io.github.trinhvandat.sepia.data

import io.github.trinhvandat.sepia.domain.EpubMetadata
import org.w3c.dom.Element
import java.io.ByteArrayInputStream
import java.util.zip.ZipInputStream
import javax.xml.parsers.DocumentBuilderFactory

/**
 * Đọc OPF từ EPUB bằng java.util.zip + DOM của JDK (có cả trên JVM test lẫn Android runtime).
 * Không tải DTD ngoài (an toàn + nhanh). Chỉ cần vài file XML nhỏ nên đọc theo entry là đủ.
 */
actual class EpubMetadataReader actual constructor() {

    actual fun read(epubBytes: ByteArray): EpubMetadata {
        val container = readEntry(epubBytes, "META-INF/container.xml")
            ?: error("EPUB thiếu META-INF/container.xml")
        val opfPath = parseOpfPath(container) ?: error("container.xml không có rootfile full-path")
        val opf = readEntry(epubBytes, opfPath) ?: error("EPUB thiếu OPF: $opfPath")
        return parseOpf(opf)
    }

    private fun readEntry(bytes: ByteArray, name: String): ByteArray? {
        ZipInputStream(ByteArrayInputStream(bytes)).use { zis ->
            var entry = zis.nextEntry
            while (entry != null) {
                if (entry.name == name) return zis.readBytes()
                entry = zis.nextEntry
            }
        }
        return null
    }

    private fun documentBuilder() = DocumentBuilderFactory.newInstance().apply {
        isNamespaceAware = false
        runCatching { setFeature("http://apache.org/xml/features/nonvalidating/load-external-dtd", false) }
        runCatching { setFeature("http://xml.org/sax/features/external-general-entities", false) }
        runCatching { setFeature("http://xml.org/sax/features/external-parameter-entities", false) }
    }.newDocumentBuilder()

    private fun parseOpfPath(containerXml: ByteArray): String? {
        val doc = documentBuilder().parse(ByteArrayInputStream(containerXml))
        val nodes = doc.getElementsByTagName("rootfile")
        for (i in 0 until nodes.length) {
            val el = nodes.item(i) as? Element ?: continue
            val path = el.getAttribute("full-path")
            if (path.isNotBlank()) return path
        }
        return null
    }

    private fun parseOpf(opf: ByteArray): EpubMetadata {
        val doc = documentBuilder().parse(ByteArrayInputStream(opf))
        val rawIdentifier = firstText(doc.getElementsByTagName("dc:identifier"))
            ?: firstText(doc.getElementsByTagName("identifier"))
        val title = firstText(doc.getElementsByTagName("dc:title"))
            ?: firstText(doc.getElementsByTagName("title"))
            ?: ""
        val author = firstText(doc.getElementsByTagName("dc:creator"))
            ?: firstText(doc.getElementsByTagName("creator"))
            ?: ""
        val pipelineVersion = metaProperty(doc, "sepia:pipeline-version")?.toIntOrNull() ?: 0
        val sourcePdf = metaProperty(doc, "sepia:source-pdf")

        val bookUid = rawIdentifier?.takeIf { it.startsWith("sepia:") }
        return EpubMetadata(
            bookUid = bookUid,
            rawIdentifier = rawIdentifier,
            title = title.trim(),
            author = author.trim(),
            pipelineVersion = pipelineVersion,
            sourcePdfName = sourcePdf?.trim()?.takeIf { it.isNotEmpty() },
        )
    }

    private fun firstText(nodes: org.w3c.dom.NodeList): String? {
        if (nodes.length == 0) return null
        val text = nodes.item(0).textContent?.trim()
        return text?.takeIf { it.isNotEmpty() }
    }

    /** `<meta property="...">value</meta>` (EPUB3). */
    private fun metaProperty(doc: org.w3c.dom.Document, property: String): String? {
        val metas = doc.getElementsByTagName("meta")
        for (i in 0 until metas.length) {
            val el = metas.item(i) as? Element ?: continue
            if (el.getAttribute("property") == property) {
                val v = el.textContent?.trim()
                if (!v.isNullOrEmpty()) return v
            }
        }
        return null
    }
}
