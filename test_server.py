import http.client
import io
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
import wave
from unittest.mock import patch

import server


def form(parts):
    body = bytearray()
    for name, value in parts:
        body.extend(b"--wa-test\r\n")
        header = f'Content-Disposition: form-data; name="{name}"'
        if name == "file":
            header += '; filename="../../arbitrary.ogg"'
        body.extend((header + "\r\n\r\n").encode())
        body.extend(value)
        body.extend(b"\r\n")
    body.extend(b"--wa-test--\r\n")
    return bytes(body)


PARTS = [("file", b"OggS\x00\xff\r\n\x01"), ("model", b"apple-speechanalyzer"),
         ("language", b"pt"), ("response_format", b"json")]


class EndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()

    def request(self, body=None, headers=None, path="/v1/audio/transcriptions"):
        conn = http.client.HTTPConnection("127.0.0.1", self.http.server_port, timeout=3)
        try:
            conn.request("POST", path, body=body if body is not None else form(PARTS), headers={
                "Content-Type": "multipart/form-data; boundary=wa-test", **(headers or {})})
            response = conn.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            conn.close()

    def test_extension_request_preserves_binary_and_selects_brazilian_portuguese(self):
        with patch.object(server, "transcribe", return_value={"text": "Olá"}) as transcribe:
            status, body, headers = self.request(headers={"Origin": "chrome-extension://" + "a" * 32})
        self.assertEqual(status, 200)
        self.assertIn("Olá".encode(), body)
        self.assertEqual(headers["Cache-Control"], "no-store")
        transcribe.assert_called_once_with(PARTS[0][1], "pt_BR")

    def test_common_web_page_cannot_invoke_transcription(self):
        with patch.object(server, "transcribe") as transcribe:
            status, _, headers = self.request(headers={"Origin": "https://web.whatsapp.com"})
        self.assertEqual(status, 403)
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        transcribe.assert_not_called()

    def test_rebound_or_malformed_host_is_rejected(self):
        for host in [f"attacker.example:{self.http.server_port}", "[malformed"]:
            with self.subTest(host=host):
                self.assertEqual(self.request(headers={"Host": host})[0], 403)

    def test_duplicate_file_and_wrong_model_are_rejected(self):
        with patch.object(server, "transcribe") as transcribe:
            self.assertEqual(self.request(form(PARTS + [PARTS[0]]))[0], 400)
            altered = [(name, b"parakeet" if name == "model" else data) for name, data in PARTS]
            self.assertEqual(self.request(form(altered))[0], 400)
        transcribe.assert_not_called()

    def test_oversized_upload_is_rejected_without_waiting_for_its_body(self):
        self.assertEqual(self.request(b"x", {"Content-Length": str(server.MAX_BODY + 1)})[0], 413)

    def test_concurrent_request_is_rejected(self):
        server.BUSY.acquire()
        try:
            self.assertEqual(self.request()[0], 429)
        finally:
            server.BUSY.release()

    def test_failed_request_releases_transcription_slot(self):
        with patch.object(server, "transcribe", side_effect=server.RequestError(415, "Inválido")):
            self.assertEqual(self.request()[0], 415)
        self.assertFalse(server.BUSY.locked())

    def test_audio_files_are_removed_after_conversion_failure(self):
        constructor = tempfile.TemporaryDirectory
        folders = []
        def temporary(**kwargs):
            value = constructor(**kwargs)
            folders.append(Path(value.name))
            return value
        with patch.object(server.tempfile, "TemporaryDirectory", side_effect=temporary), \
                patch.object(server.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)):
            with self.assertRaises(server.RequestError):
                server.transcribe(PARTS[0][1], "pt_BR")
        self.assertTrue(folders)
        self.assertTrue(all(not folder.exists() for folder in folders))

    def test_empty_recording_is_rejected_without_waiting_for_speech(self):
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
        with self.assertRaises(server.RequestError) as error:
            server.transcribe(buffer.getvalue(), "pt_BR")
        self.assertEqual(error.exception.status, 422)

    def test_duration_limit_rejects_audio_instead_of_returning_a_partial_transcript(self):
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(b"\x00\x00" * 1600)
        with patch.object(server, "MAX_DURATION", 0.01), self.assertRaises(server.RequestError) as error:
            server.transcribe(buffer.getvalue(), "pt_BR")
        self.assertEqual(error.exception.status, 413)


if __name__ == "__main__":
    unittest.main()
