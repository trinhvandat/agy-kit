// OCR một ảnh bằng Apple Vision (native macOS, offline, KHÔNG cần cài gì).
// Dùng cho SPIKE-5 (OCR lại từ ảnh trang, bỏ qua lớp chữ ẩn ABBYY).
//
//   swiftc -O spikes/ocr_vision.swift -o <bin>
//   <bin> <đường-dẫn-ảnh> [accurate|fast]
//
// In văn bản nhận được ra stdout (mỗi quan sát một dòng); in `ocr_seconds=...` ra stderr.
// Chỉ chạy trên macOS ≥ 13 (Vision hỗ trợ `vi-VT` ở mức `accurate`).
import Foundation
import Vision
import AppKit

let args = CommandLine.arguments
guard args.count >= 2 else {
    FileHandle.standardError.write("usage: ocr_vision <image> [accurate|fast]\n".data(using: .utf8)!)
    exit(2)
}
let path = args[1]
let level: VNRequestTextRecognitionLevel = (args.count > 2 && args[2] == "fast") ? .fast : .accurate
guard let img = NSImage(contentsOfFile: path),
      let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write("cannot load image: \(path)\n".data(using: .utf8)!)
    exit(3)
}
let req = VNRecognizeTextRequest()
req.recognitionLevel = level
req.usesLanguageCorrection = true
req.recognitionLanguages = ["vi-VT"]   // tiếng Việt chỉ có ở mức `accurate`
let handler = VNImageRequestHandler(cgImage: cg, options: [:])
let t0 = Date()
try handler.perform([req])
let dt = Date().timeIntervalSince(t0)
var lines: [String] = []
for o in (req.results ?? []) {
    if let c = o.topCandidates(1).first { lines.append(c.string) }
}
FileHandle.standardError.write(String(format: "ocr_seconds=%.3f\n", dt).data(using: .utf8)!)
print(lines.joined(separator: "\n"))
