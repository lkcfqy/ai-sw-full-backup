import Foundation
import Vision
import AppKit

let inputs = CommandLine.arguments.dropFirst()
for path in inputs {
    let url = URL(fileURLWithPath: path)
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["ko-KR", "en-US"]
    request.usesLanguageCorrection = true
    let qr = VNDetectBarcodesRequest()
    let handler = VNImageRequestHandler(url: url)
    do {
        try handler.perform([request, qr])
        let lines = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        let codes = (qr.results ?? []).compactMap { $0.payloadStringValue }
        let result: [String: Any] = ["path": path, "text": lines.joined(separator: "\n"), "barcodes": codes]
        let data = try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys, .withoutEscapingSlashes])
        print(String(data: data, encoding: .utf8)!)
    } catch {
        print("{\"error\":\"OCR failed\"}")
    }
}
