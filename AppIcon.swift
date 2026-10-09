import AppKit

// App icon is rendered from Apple's SF Symbols; no generated or third-party artwork.
let image = NSImage(size: NSSize(width: 512, height: 512))
image.lockFocus()
NSColor.systemBlue.setFill()
NSBezierPath(roundedRect: NSRect(x: 32, y: 32, width: 448, height: 448), xRadius: 100, yRadius: 100).fill()
let configuration = NSImage.SymbolConfiguration(pointSize: 250, weight: .medium)
    .applying(NSImage.SymbolConfiguration(paletteColors: [.white]))
let symbol = NSImage(systemSymbolName: "waveform", accessibilityDescription: nil)!
    .withSymbolConfiguration(configuration)!
symbol.draw(in: NSRect(x: 116, y: 116, width: 280, height: 280))
image.unlockFocus()
let bitmap = NSBitmapImageRep(data: image.tiffRepresentation!)!
try bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: CommandLine.arguments[1]))
