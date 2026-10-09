import Foundation
import AVFoundation
import Speech

// Transcription stays on-device. Asset downloads occur only with explicit --install.
@main
struct SpeechWorker {
    static func emit(_ value: [String: Any]) throws {
        let data = try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data([10]))
    }

    static func main() async {
        do {
            guard SpeechTranscriber.isAvailable else {
                throw Failure("O transcritor da Apple não está disponível neste Mac.")
            }
            let supported = await SpeechTranscriber.supportedLocales
            let installed = await SpeechTranscriber.installedLocales
            if CommandLine.arguments.dropFirst().first == "--info" {
                try emit([
                    "available": true,
                    "supported_locales": supported.map(\.identifier).sorted(),
                    "installed_locales": installed.map(\.identifier).sorted()
                ])
                return
            }
            guard CommandLine.arguments.count == 3 else {
                throw Failure("Uso: speech-worker arquivo.wav pt_BR")
            }
            let requested = Locale(identifier: CommandLine.arguments[2])
            guard let locale = await SpeechTranscriber.supportedLocale(equivalentTo: requested) else {
                throw Failure("Este idioma não é suportado pelo transcritor da Apple.")
            }
            if CommandLine.arguments[1] == "--install" {
                // false means it was already reserved, which is valid on retry.
                _ = try await AssetInventory.reserve(locale: locale)
                let module = SpeechTranscriber(locale: locale, preset: .transcription)
                if let request = try await AssetInventory.assetInstallationRequest(supporting: [module]) {
                    try await request.downloadAndInstall()
                }
                let ready = await SpeechTranscriber.installedLocales
                guard ready.contains(where: { $0.identifier == locale.identifier }) else {
                    throw Failure("O português ainda não está disponível. Confira a conexão e tente novamente.")
                }
                try emit(["available": true, "supported_locales": supported.map(\.identifier).sorted(),
                          "installed_locales": ready.map(\.identifier).sorted()])
                return
            }
            guard installed.contains(where: { $0.identifier == locale.identifier }) else {
                throw Failure("O modelo de \(locale.identifier) não está instalado no Mac. Selecione Português.")
            }
            let file = try AVAudioFile(forReading: URL(fileURLWithPath: CommandLine.arguments[1]))
            guard file.length > 0 else {
                throw Failure("O arquivo não contém amostras de áudio.")
            }
            let transcriber = SpeechTranscriber(locale: locale, preset: .transcription)
            let analyzer = SpeechAnalyzer(modules: [transcriber])
            async let collected = transcriber.results.reduce("") { text, result in
                text + String(result.text.characters)
            }
            if let end = try await analyzer.analyzeSequence(from: file) {
                try await analyzer.finalizeAndFinish(through: end)
            } else {
                await analyzer.cancelAndFinishNow()
            }
            let text = try await collected.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !text.isEmpty else {
                throw Failure("Não foi possível identificar fala neste áudio.")
            }
            try emit(["text": text, "language": locale.identifier, "on_device": true])
        } catch {
            try? emit(["error": ["message": error.localizedDescription]])
            exit(1)
        }
    }

    struct Failure: LocalizedError {
        let message: String
        init(_ message: String) { self.message = message }
        var errorDescription: String? { message }
    }
}
