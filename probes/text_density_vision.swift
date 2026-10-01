// 文字密度仪器(第四轮 OCR 密度分层用): macOS Vision 文字检测/识别, 与被测 OCR(RapidOCR)无关, 不读真值。
// 每框只输出几何 + 两个数: 非空白字符数 n、是否抖音水印字样 wm(串含「抖音」或「音号」)。
// ★ 识别出的文字本身不输出, 不进任何产物。
// 用法: swiftc -O text_density_vision.swift -o tdv && ./tdv a.jpg b.jpg ...  → 每图一行 JSON
//   boxes: [[x, y, w, h, n, wm], ...] 像素坐标, 原点左上
import Foundation
import Vision
import ImageIO

func run(_ img: CGImage) throws -> [VNRecognizedTextObservation] {
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.recognitionLanguages = ["zh-Hans", "en-US"]
    req.usesLanguageCorrection = false
    req.revision = VNRecognizeTextRequestRevision3
    try VNImageRequestHandler(cgImage: img, options: [:]).perform([req])
    return req.results ?? []
}

for path in CommandLine.arguments.dropFirst() {
    guard let src = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil),
          let img = CGImageSourceCreateImageAtIndex(src, 0, nil) else {
        print("{\"path\":\"\(path)\",\"error\":\"decode\"}"); continue
    }
    let W = Double(img.width), H = Double(img.height)
    // 首次调用偶发冷启动失败(实测 1 次) ⇒ 只重试一次, 仍失败记 error
    guard let obs = (try? run(img)) ?? (try? run(img)) else {
        print("{\"path\":\"\(path)\",\"error\":\"vision\"}"); continue
    }
    var rows: [String] = []
    for o in obs {
        let b = o.boundingBox  // 归一化, 原点左下
        let s = o.topCandidates(1).first?.string ?? ""
        let n = s.filter { !$0.isWhitespace }.count
        let wm = (s.contains("抖音") || s.contains("音号")) ? 1 : 0
        rows.append(String(format: "[%.1f,%.1f,%.1f,%.1f,%d,%d]",
                           b.minX * W, (1 - b.maxY) * H, b.width * W, b.height * H, n, wm))
    }
    print("{\"path\":\"\(path)\",\"w\":\(Int(W)),\"h\":\(Int(H)),\"boxes\":[\(rows.joined(separator: ","))]}")
}
