import AppKit
import SwiftUI

struct ModelInfo: Decodable, Sendable {
    let available: Bool
    let installed_locales: [String]
}

struct ServerReply: Decodable, Sendable {
    var state: String
    var running: Bool
    var busy: Bool
    var autostart: Bool
    var loaded: Bool
    var url: String
    var model: String
    var message: String
    var test_text: String?
    var models: ModelInfo?

    static let initial = ServerReply(state: "checking", running: false, busy: false,
        autostart: false, loaded: false, url: "http://127.0.0.1:5092/v1",
        model: "apple-speechanalyzer", message: "")
}

enum Backend {
    struct Failure: LocalizedError, Sendable {
        let message: String
        var errorDescription: String? { message }
    }

    static func run(root: String, arguments: [String]) throws -> ServerReply {
        let process = Process()
        let bundled = URL(fileURLWithPath: root + "/Contents/Helpers/wa-backend.app/Contents/MacOS/wa-backend")
        if FileManager.default.isExecutableFile(atPath: bundled.path) {
            process.executableURL = bundled
            process.arguments = arguments + ["--json"]
        } else {
            process.executableURL = URL(fileURLWithPath: root + "/.venv/bin/python")
            process.arguments = [root + "/manage.py"] + arguments + ["--json"]
        }
        process.currentDirectoryURL = URL(fileURLWithPath: root)
        let output = Pipe()
        process.standardOutput = output
        process.standardError = FileHandle.nullDevice
        try process.run()
        let data = output.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        if let dictionary = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let error = dictionary["error"] as? String {
            throw Failure(message: error)
        }
        guard process.terminationStatus == 0 else {
            throw Failure(message: "Não foi possível controlar o servidor. Abra as instruções e tente novamente.")
        }
        do {
            return try JSONDecoder().decode(ServerReply.self, from: data)
        } catch {
            throw Failure(message: "O servidor não respondeu como esperado. Tente atualizar o estado.")
        }
    }
}

@MainActor
final class ServerModel: ObservableObject {
    @Published var server = ServerReply.initial
    @Published var action: String?
    @Published var notice: String?
    @Published var testText: String?
    @Published var modelsChecked = false
    @Published var portugueseReady = false
    private var refreshing = false
    private var polling: Task<Void, Never>?
    let root: String

    init() {
        root = Bundle.main.object(forInfoDictionaryKey: "WAServerRoot") as? String
            ?? (Bundle.main.bundleURL.pathExtension == "app" ? Bundle.main.bundleURL.path : nil)
            ?? FileManager.default.currentDirectoryPath
        polling = Task { [weak self] in
            await self?.refresh()
            await self?.loadModels()
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(3))
                if Task.isCancelled { break }
                await self?.refresh()
            }
        }
    }

    var working: Bool { action != nil }
    var canControl: Bool { !working && server.state != "checking" && server.state != "conflict" }
    var canStop: Bool { canControl && !server.busy }
    var title: String {
        if action == "start" { return "Iniciando servidor…" }
        if action == "stop" { return "Parando servidor…" }
        switch server.state {
        case "checking": return "Verificando servidor…"
        case "running": return "Servidor ativo"
        case "busy": return "Transcrevendo áudio"
        case "starting": return "Servidor iniciando"
        case "stopped": return "Servidor parado"
        default: return "Servidor indisponível"
        }
    }
    var subtitle: String {
        switch server.state {
        case "running": return "Pronto para receber áudios da extensão."
        case "busy": return "Aguarde a transcrição terminar para parar o servidor."
        case "stopped": return "Inicie o servidor para transcrever no WhatsApp."
        case "checking", "starting": return "Aguarde a conexão com o serviço local."
        default: return server.message.isEmpty ? "Atualize o estado ou tente iniciar novamente." : server.message
        }
    }
    var statusSymbol: String {
        switch server.state {
        case "running": return "checkmark.circle.fill"
        case "busy": return "waveform"
        case "stopped": return "pause.circle"
        case "checking", "starting": return "clock"
        default: return "exclamationmark.triangle.fill"
        }
    }
    var statusColor: Color {
        switch server.state {
        case "running": return .green
        case "busy": return .accentColor
        case "error", "conflict": return .orange
        default: return .secondary
        }
    }

    func refresh() async {
        guard !working && !refreshing else { return }
        refreshing = true
        defer { refreshing = false }
        do {
            let directory = root
            let reply = try await Task.detached { try Backend.run(root: directory, arguments: ["status"]) }.value
            guard !working else { return }
            server = reply
        } catch {
            guard !working else { return }
            server.state = "error"
            server.running = false
            server.message = error.localizedDescription
        }
    }

    func loadModels() async {
        do {
            let directory = root
            let reply = try await Task.detached { try Backend.run(root: directory, arguments: ["models"]) }.value
            portugueseReady = reply.models?.available == true && reply.models?.installed_locales.contains("pt_BR") == true
        } catch {
            portugueseReady = false
        }
        modelsChecked = true
    }

    func perform(_ command: String, value: String? = nil) {
        guard !working else { return }
        action = command
        notice = nil
        if command == "test" { testText = nil }
        let directory = root
        let arguments = [command] + (value.map { [$0] } ?? [])
        Task {
            do {
                let reply = try await Task.detached { try Backend.run(root: directory, arguments: arguments) }.value
                server = reply
                if let text = reply.test_text { testText = text }
                if command == "prepare-model" {
                    portugueseReady = reply.models?.available == true && reply.models?.installed_locales.contains("pt_BR") == true
                    modelsChecked = true
                }
            } catch {
                notice = error.localizedDescription
            }
            action = nil
            await refresh()
        }
    }

    func copy(_ text: String) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
        notice = "Copiado. Cole esse valor na configuração da extensão."
    }

    func openWhatsApp() {
        guard let chrome = NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.google.Chrome"),
              let url = URL(string: "https://web.whatsapp.com/") else { return }
        NSWorkspace.shared.open([url], withApplicationAt: chrome, configuration: NSWorkspace.OpenConfiguration())
    }
}

struct ConnectionRow: View {
    let title: String
    let value: String
    let copy: () -> Void
    var body: some View {
        LabeledContent(title) {
            HStack(spacing: 8) {
                Text(value).font(.system(.callout, design: .monospaced)).textSelection(.enabled)
                Button(action: copy) { Image(systemName: "doc.on.doc") }
                    .buttonStyle(.borderless).help("Copiar \(title.lowercased())")
                    .accessibilityLabel("Copiar \(title.lowercased())")
            }
        }
    }
}

struct ControlWindow: View {
    @ObservedObject var model: ServerModel
    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 14) {
                Image(systemName: "waveform").font(.system(size: 30, weight: .medium)).foregroundStyle(.tint)
                VStack(alignment: .leading, spacing: 4) {
                    Text("Transcrição Local").font(.title2.weight(.semibold))
                    Text("Áudios do WhatsApp, no seu Mac.").foregroundStyle(.secondary)
                }
                Spacer()
            }.padding(.horizontal, 24).padding(.top, 20).padding(.bottom, 4)

            Form {
                Section {
                    HStack(alignment: .center, spacing: 14) {
                        Image(systemName: model.statusSymbol).font(.title2).foregroundStyle(model.statusColor)
                        VStack(alignment: .leading, spacing: 4) {
                            Text(model.title).font(.headline)
                            Text(model.subtitle).font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                        }
                        Spacer(minLength: 8)
                        if model.action == "start" || model.action == "stop" {
                            ProgressView().controlSize(.small).accessibilityLabel(model.title)
                        } else {
                            Button(model.server.running || model.server.loaded ? "Parar servidor" : "Iniciar servidor") {
                                model.perform(model.server.running || model.server.loaded ? "stop" : "start")
                            }
                            .buttonStyle(.borderedProminent).controlSize(.large)
                            .disabled(model.server.running || model.server.loaded ? !model.canStop : !model.canControl)
                        }
                    }.padding(.vertical, 6)
                    HStack {
                        Label("Transcrição no próprio Mac", systemImage: "lock.shield")
                        Spacer()
                        Text(model.modelsChecked ? (model.portugueseReady ? "Português disponível" : "Verifique o modelo") : "Verificando modelo…")
                            .foregroundStyle(.secondary)
                    }.font(.callout)
                    if model.modelsChecked && !model.portugueseReady {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Baixe o modelo de português da Apple uma vez. Isso exige internet; as transcrições continuam no seu Mac.")
                                .font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                            HStack {
                                if model.action == "prepare-model" { ProgressView().controlSize(.small) }
                                Button(model.action == "prepare-model" ? "Preparando português…" : "Preparar português") {
                                    model.perform("prepare-model")
                                }.disabled(model.working)
                            }
                        }.padding(.vertical, 4)
                    }
                }

                Section {
                    Toggle("Iniciar o servidor ao entrar no Mac", isOn: Binding(
                        get: { model.server.autostart },
                        set: { model.perform("autostart", value: $0 ? "on" : "off") }
                    )).toggleStyle(.switch).disabled(!model.canControl)
                } footer: {
                    Text("Esta opção vale para a próxima entrada no Mac. Ligar ou parar agora não altera essa preferência.")
                }

                Section("Conectar a extensão") {
                    ConnectionRow(title: "Endereço", value: model.server.url) { model.copy(model.server.url) }
                    ConnectionRow(title: "Modelo", value: model.server.model) { model.copy(model.server.model) }
                    LabeledContent("Idioma", value: "Português do Brasil")
                    HStack {
                        Text("Na extensão: Servidor compatível com OpenAI. Chave em branco.")
                            .font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                        Spacer()
                        Button("Abrir WhatsApp", action: model.openWhatsApp).help("Abrir WhatsApp Web no Chrome")
                    }
                }

                Section("Testar o funcionamento") {
                    HStack {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(model.action == "test" ? "Testando a transcrição…" : "Uma mensagem de exemplo")
                            Text("Sem usar o microfone ou seus áudios.").font(.callout).foregroundStyle(.secondary)
                        }
                        Spacer()
                        if model.action == "test" { ProgressView().controlSize(.small) }
                        Button("Testar transcrição") { model.perform("test") }
                            .disabled(!model.server.running || model.server.busy || model.working || !model.portugueseReady)
                    }
                    if let text = model.testText {
                        VStack(alignment: .leading, spacing: 8) {
                            Label("Teste concluído", systemImage: "checkmark.circle").foregroundStyle(.green)
                            Text(text).font(.callout).textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
                        }.padding(.vertical, 4)
                    }
                }

                if let notice = model.notice {
                    Section {
                        HStack(alignment: .top) {
                            Text(notice).font(.callout).fixedSize(horizontal: false, vertical: true)
                            Spacer()
                            Button { model.notice = nil } label: { Image(systemName: "xmark") }
                                .buttonStyle(.borderless).accessibilityLabel("Fechar aviso")
                        }
                    }
                }
            }.formStyle(.grouped)

            HStack {
                Text("Fechar a janela mantém o servidor e o ícone de menus.").font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button { Task { await model.refresh(); await model.loadModels() } } label: {
                    Image(systemName: "arrow.clockwise")
                }.buttonStyle(.borderless).help("Atualizar estado").accessibilityLabel("Atualizar estado")
            }.padding(.horizontal, 24).padding(.bottom, 16)
        }.frame(minWidth: 570, minHeight: 650)
    }
}

struct StatusMenu: View {
    @ObservedObject var model: ServerModel
    @Environment(\.openWindow) private var openWindow
    var body: some View {
        Label(model.title, systemImage: model.statusSymbol)
        Divider()
        Button("Abrir Transcrição Local") {
            openWindow(id: "control")
            NSApp.activate(ignoringOtherApps: true)
        }
        Button(model.server.running || model.server.loaded ? "Parar servidor" : "Iniciar servidor") {
            model.perform(model.server.running || model.server.loaded ? "stop" : "start")
        }.disabled(model.server.running || model.server.loaded ? !model.canStop : !model.canControl)
        Toggle("Iniciar o servidor ao entrar no Mac", isOn: Binding(
            get: { model.server.autostart },
            set: { model.perform("autostart", value: $0 ? "on" : "off") }
        )).disabled(!model.canControl)
        Divider()
        Button("Copiar endereço") { model.copy(model.server.url) }
        Button("Abrir WhatsApp no Chrome", action: model.openWhatsApp)
        Divider()
        Button("Sair do aplicativo") { NSApp.terminate(nil) }
        Text("Sair mantém o servidor em seu estado atual.")
    }
}

@main
struct TranscriptionApp: App {
    @StateObject private var model = ServerModel()
    var body: some Scene {
        Window("Transcrição Local", id: "control") {
            ControlWindow(model: model)
        }.defaultSize(width: 610, height: 700)
            .windowResizability(.contentMinSize)
            .commands {
                CommandGroup(replacing: .newItem) {}
                CommandGroup(after: .appInfo) {
                    Button("Atualizar estado") { Task { await model.refresh(); await model.loadModels() } }
                        .keyboardShortcut("r", modifiers: .command)
                }
            }
        MenuBarExtra("Transcrição Local", systemImage: model.server.running ? "waveform" : "waveform.slash") {
            StatusMenu(model: model)
        }.menuBarExtraStyle(.menu)
    }
}
