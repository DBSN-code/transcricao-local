"""Local OpenAI-shaped audio endpoint backed exclusively by Apple Speech."""

import argparse
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import threading
from urllib.parse import urlsplit
import wave

import runtime_paths

ROOT = Path(__file__).resolve().parent
WORKER = runtime_paths.WORKER
MODEL = "apple-speechanalyzer"
MAX_AUDIO = 25 * 1024 * 1024
MAX_BODY = MAX_AUDIO + 1024 * 1024
MAX_DURATION = 30 * 60
BUSY = threading.Lock()
LOCALES = {"pt": "pt_BR", "en": "en_US", "es": "es_ES", "fr": "fr_FR"}


class RequestError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def audio_extension(data):
    if data.startswith(b"OggS"):
        return ".ogg"
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return ".wav"
    if data.startswith(b"fLaC"):
        return ".flac"
    if data[4:8] == b"ftyp":
        return ".m4a"
    if data.startswith(b"ID3") or (len(data) > 1 and data[0] == 255 and data[1] & 224 == 224):
        return ".mp3"
    if data.startswith(b"\x1aE\xdf\xa3"):
        return ".webm"
    raise RequestError(415, "Formato de áudio não reconhecido.")


def multipart(content_type, body):
    if not content_type.lower().startswith("multipart/form-data;"):
        raise RequestError(415, "Envie o áudio como multipart/form-data.")
    message = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: " + content_type.encode("ascii") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body
    )
    if not message.is_multipart() or message.defects:
        raise RequestError(400, "Formulário de áudio inválido.")
    fields, audio = {}, None
    for part in message.iter_parts():
        if part.is_multipart() or part.defects or part.get_content_disposition() != "form-data":
            raise RequestError(400, "Campo do formulário inválido.")
        name = part.get_param("name", header="content-disposition")
        value = part.get_payload(decode=True)
        if name == "file":
            if audio is not None or not value:
                raise RequestError(400, "Envie um único arquivo de áudio.")
            if len(value) > MAX_AUDIO:
                raise RequestError(413, "O áudio ultrapassa 25 MB.")
            audio = value
        elif name in {"model", "language", "response_format"}:
            if name in fields or len(value or b"") > 128:
                raise RequestError(400, "Campo do formulário inválido.")
            fields[name] = value.decode("utf-8")
        else:
            raise RequestError(400, "Campo não suportado pelo servidor local.")
    if audio is None:
        raise RequestError(400, "O campo file é obrigatório.")
    if fields.get("model") != MODEL:
        raise RequestError(400, "Selecione o modelo apple-speechanalyzer na extensão.")
    if fields.get("response_format", "json") != "json":
        raise RequestError(400, "Este servidor devolve transcrições em JSON.")
    language = fields.get("language", "pt") or "pt"
    locale = LOCALES.get(language, language.replace("-", "_"))
    if not re.fullmatch(r"[a-z]{2,3}_[A-Z]{2}", locale):
        raise RequestError(400, "Idioma inválido. Selecione Português na extensão.")
    return audio, locale


def transcribe(audio, locale):
    # TemporaryDirectory removes the original audio and converted WAV on every exit path.
    with tempfile.TemporaryDirectory(prefix="wa-apple-") as directory:
        source = Path(directory) / ("input" + audio_extension(audio))
        wav = Path(directory) / "converted.wav"
        source.write_bytes(audio)
        converted = subprocess.run(
            [runtime_paths.ffmpeg_executable(), "-nostdin", "-hide_banner", "-loglevel", "error",
             "-protocol_whitelist", "file,pipe", "-i", str(source), "-map", "0:a:0", "-vn",
             "-t", str(MAX_DURATION + 1), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-y", str(wav)],
            capture_output=True, timeout=30,
        )
        if converted.returncode:
            raise RequestError(415, "Não foi possível converter este arquivo de áudio.")
        with wave.open(str(wav), "rb") as decoded:
            duration = decoded.getnframes() / decoded.getframerate()
            if duration <= 0:
                raise RequestError(422, "O arquivo não contém amostras de áudio.")
            if duration > MAX_DURATION:
                raise RequestError(413, "O áudio ultrapassa o limite local de 30 minutos.")
        result = subprocess.run(
            [str(WORKER), str(wav), locale], capture_output=True, timeout=140,
        )
        try:
            payload = json.loads(result.stdout)
        except (ValueError, UnicodeDecodeError):
            raise RequestError(503, "O transcritor da Apple não respondeu. Reinicie o servidor local.")
        if result.returncode:
            raise RequestError(422, payload.get("error", {}).get("message", "Falha na transcrição local."))
        if not isinstance(payload.get("text"), str) or not payload["text"].strip():
            raise RequestError(422, "Não foi possível identificar fala neste áudio.")
        return payload


class Handler(BaseHTTPRequestHandler):
    server_version = "WAApple/1.0"
    protocol_version = "HTTP/1.1"

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def trusted(self):
        # Loopback binding plus Host/Origin checks prevents ordinary web pages and DNS rebinding.
        if len(self.headers.get_all("Host", [])) != 1:
            return False
        try:
            host = urlsplit("http://" + self.headers["Host"])
            valid_host = host.hostname in {"127.0.0.1", "localhost"} and host.port == self.server.server_port
        except ValueError:
            return False
        origins = self.headers.get_all("Origin", [])
        return valid_host and (not origins or len(origins) == 1 and bool(
            re.fullmatch(r"chrome-extension://[a-p]{32}", origins[0])
        ))

    def send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        origin = self.headers.get("Origin")
        if self.trusted() and origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.close_connection = True
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        if not self.trusted():
            return self.send_json(403, {"error": {"message": "Origem não permitida."}})
        if self.path == "/health":
            return self.send_json(200, {"status": "ok", "model": MODEL, "on_device": True,
                                        "default_language": "pt_BR", "busy": BUSY.locked()})
        if self.path == "/v1/models":
            return self.send_json(200, {"object": "list", "data": [
                {"id": MODEL, "object": "model", "owned_by": "local"}]})
        return self.send_json(404, {"error": {"message": "Rota não encontrada."}})

    def do_OPTIONS(self):
        if not self.trusted():
            return self.send_json(403, {"error": {"message": "Origem não permitida."}})
        self.send_response(204)
        if self.headers.get("Origin"):
            self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

    def do_POST(self):
        acquired = False
        try:
            if not self.trusted():
                raise RequestError(403, "Origem não permitida.")
            if self.path != "/v1/audio/transcriptions":
                raise RequestError(404, "Rota não encontrada.")
            sizes = self.headers.get_all("Content-Length", [])
            if len(sizes) != 1 or not re.fullmatch(r"[0-9]+", sizes[0]) or self.headers.get("Transfer-Encoding"):
                raise RequestError(411, "Content-Length é obrigatório.")
            size = int(sizes[0])
            if size > MAX_BODY:
                raise RequestError(413, "O áudio ultrapassa 25 MB.")
            if not 0 < size:
                raise RequestError(400, "O áudio está vazio.")
            acquired = BUSY.acquire(blocking=False)
            if not acquired:
                raise RequestError(429, "Já há um áudio sendo transcrito. Aguarde e tente novamente.")
            body = self.rfile.read(size)
            if len(body) != size:
                raise RequestError(400, "O envio do áudio foi interrompido.")
            audio, locale = multipart(self.headers.get("Content-Type", ""), body)
            self.send_json(200, transcribe(audio, locale))
        except RequestError as error:
            self.send_json(error.status, {"error": {"message": error.message}})
        except (UnicodeError, ValueError):
            self.send_json(400, {"error": {"message": "Formulário inválido."}})
        except (subprocess.TimeoutExpired, TimeoutError):
            self.send_json(408, {"error": {"message": "A transcrição demorou demais. Tente um áudio menor."}})
        except Exception:
            # Never log audio, transcripts, request bodies, or any Authorization header.
            self.send_json(503, {"error": {"message": "O servidor local não conseguiu concluir a transcrição."}})
        finally:
            if acquired:
                BUSY.release()

    def log_message(self, format, *args):
        # Avoid logging user-controlled request paths or any recording/transcript content.
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5092)
    args = parser.parse_args()
    if not WORKER.is_file():
        parser.error("Compile primeiro o transcritor em bin/speech-worker.")
    runtime_paths.ffmpeg_executable()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    # Join accepted requests on shutdown so their temporary files are cleaned up.
    server.daemon_threads = False
    def shutdown(signum, frame):
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, shutdown)
    print(f"Transcrição Apple disponível em http://127.0.0.1:{args.port}/v1", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
