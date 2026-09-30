// Text and star reader for game screenshots, using macOS Vision. No network, no AI model.
// usage: ocr file1.png file2.png ...   -> one JSON object per line
//   {"file","w","h","lines":[{"t","c","x","y","w","h"}],"stars":[{"label","x","y","filled"}]}
import Foundation
import Vision
import AppKit

struct Px { var w: Int; var h: Int; var data: [UInt8] }

func pixels(_ cg: CGImage) -> Px? {
    let w = cg.width, h = cg.height
    var data = [UInt8](repeating: 0, count: w * h * 4)
    guard let ctx = CGContext(data: &data, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4,
                              space: CGColorSpaceCreateDeviceRGB(),
                              bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return nil }
    ctx.draw(cg, in: CGRect(x: 0, y: 0, width: w, height: h))
    return Px(w: w, h: h, data: data)
}

// Count filled (orange) stars in a band under a QUALITY or PRODUCTIVITY label.
func filledStars(_ px: Px, x: Double, y: Double, h: Double) -> Int {
    let y0 = max(0, Int(y + h + 8)), y1 = min(px.h - 1, Int(y + h + 120))
    let x0 = max(0, Int(x) - 15), x1 = min(px.w - 1, Int(x) + 300)
    if y0 >= y1 || x0 >= x1 { return 0 }
    var cols = [Int](repeating: 0, count: x1 - x0 + 1)
    for yy in y0...y1 {
        for xx in x0...x1 {
            let i = (yy * px.w + xx) * 4
            let r = Int(px.data[i]), g = Int(px.data[i + 1]), b = Int(px.data[i + 2])
            if r > 200 && g > 110 && g < 205 && b < 95 { cols[xx - x0] += 1 }
        }
    }
    var runs = 0, width = 0, gap = 100
    for c in cols {
        if c >= 3 { width += 1; gap = 0 }
        else { gap += 1; if gap == 8 && width >= 12 { runs += 1 }; if gap >= 8 { width = 0 } }
    }
    if width >= 12 { runs += 1 }
    return min(runs, 5)
}

func recognize(_ path: String) -> [String: Any] {
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return ["file": path, "error": "unreadable image"] }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = (ProcessInfo.processInfo.environment["OCR_LEVEL"] == "fast") ? .fast : .accurate
    req.usesLanguageCorrection = false
    req.minimumTextHeight = 0.006
    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    do { try handler.perform([req]) } catch { return ["file": path, "error": "\(error)"] }
    let W = Double(cg.width), H = Double(cg.height)
    let px = pixels(cg)
    var lines: [[String: Any]] = [], stars: [[String: Any]] = []
    for o in (req.results ?? []) {
        guard let best = o.topCandidates(1).first else { continue }
        let b = o.boundingBox
        let x = (b.origin.x * W).rounded(), y = ((1.0 - b.origin.y - b.size.height) * H).rounded()
        let w = (b.size.width * W).rounded(), h = (b.size.height * H).rounded()
        lines.append(["t": best.string, "c": Double(best.confidence), "x": x, "y": y, "w": w, "h": h])
        let up = best.string.uppercased().trimmingCharacters(in: .whitespaces)
        if let px = px, (up == "QUALITY" || up == "PRODUCTIVITY") {
            stars.append(["label": up, "x": x, "y": y, "filled": filledStars(px, x: x, y: y, h: h)])
        }
    }
    return ["file": path, "w": Int(W), "h": Int(H), "lines": lines, "stars": stars]
}

let paths = Array(CommandLine.arguments.dropFirst())
var out = [String](repeating: "", count: paths.count)
let lock = NSLock()
DispatchQueue.concurrentPerform(iterations: paths.count) { i in
    let obj = recognize(paths[i])
    if let d = try? JSONSerialization.data(withJSONObject: obj), let s = String(data: d, encoding: .utf8) {
        lock.lock(); out[i] = s; lock.unlock()
    }
}
for s in out { print(s) }
