import io
import re
import zipfile
import clamd
from app.config import settings


class SecurityError(Exception):
    pass


class DocxSecurityPipeline:
    """
    Validates and sanitizes incoming student DOCX files:
    1. Magic bytes validation (PK\x03\x04)
    2. Zip bomb decompression bomb protection
    3. Stripping VBA macros, activeX, and malicious XML entity injections
    4. ClamAV virus scanning
    """

    MAX_COMPRESSED_MB = 20
    MAX_DECOMPRESSED_MB = 100

    def __init__(self, clam_socket_path: str = None):
        self.clam_socket_path = clam_socket_path or settings.CLAMAV_SOCKET

    def run(self, file_bytes: bytes, filename: str = "assignment.docx") -> bytes:
        if len(file_bytes) > self.MAX_COMPRESSED_MB * 1024 * 1024:
            raise SecurityError(f"File size exceeds maximum allowed {self.MAX_COMPRESSED_MB}MB")

        self._check_magic_bytes(file_bytes)
        self._check_zip_bomb(file_bytes)
        sanitized = self._strip_dangerous_content(file_bytes)
        self._clam_scan(sanitized, filename)
        return sanitized

    def _check_magic_bytes(self, data: bytes):
        if not data.startswith(b"PK\x03\x04"):
            raise SecurityError("Invalid file signature: Not a valid DOCX / OOXML archive")

    def _check_zip_bomb(self, data: bytes):
        total_size = 0
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for info in zf.infolist():
                    total_size += info.file_size
                    if total_size > self.MAX_DECOMPRESSED_MB * 1024 * 1024:
                        raise SecurityError("Security alert: Zip bomb detected (decompressed size too large)")
        except zipfile.BadZipFile:
            raise SecurityError("Corrupt archive: Unable to read DOCX contents")

    def _strip_dangerous_content(self, data: bytes) -> bytes:
        """Strip VBA macros, activeX controls, and XML entity injections while preserving safe embedded tables."""
        DANGEROUS_EXTENSIONS = (".vba", ".bin", ".exe", ".vbs", ".cmd", ".bat", ".ps1")
        DANGEROUS_PREFIXES = ("word/activeX/", "customXml/", "word/vba")

        output = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data)) as src, \
             zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as dst:
            for item in src.infolist():
                fname = item.filename.lower()
                # Skip dangerous macro files
                if fname.endswith(DANGEROUS_EXTENSIONS) and "vba" in fname:
                    continue
                if any(fname.startswith(p) for p in DANGEROUS_PREFIXES):
                    continue

                content = src.read(item.filename)
                # Strip external DOCTYPE / ENTITY injection
                if item.filename.endswith((".xml", ".rels")):
                    content = re.sub(rb"<!(?:DOCTYPE|ENTITY)[^>]*>", b"", content, flags=re.DOTALL)

                dst.writestr(item, content)

        return output.getvalue()

    def _clam_scan(self, data: bytes, filename: str):
        try:
            cd = clamd.ClamdUnixSocket(path=self.clam_socket_path)
            res = cd.instream(io.BytesIO(data))
            status, reason = res.get("stream", ("OK", ""))
            if status == "FOUND":
                raise SecurityError(f"Malware signature detected in uploaded file: {reason}")
        except Exception:
            # In development mode, allow upload if ClamAV daemon is warming up
            if settings.ENVIRONMENT == "production":
                raise SecurityError("Virus scanner unavailable: Upload blocked for security")
            pass
