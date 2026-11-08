"""Image intake with explicit limits and full decode.

Pillow's ``Image.open`` is lazy, so ``verify`` followed by a fresh ``load`` is
required; otherwise a truncated or decompression-bomb image could pass the
first check. Only PNG and JPEG are accepted.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import io
import struct
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

from .errors import ApiError

MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_REQUEST_CHARS = 16 * 1024 * 1024
MAX_PIXELS = 20_000_000
ALLOWED_FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg"}


@dataclass(frozen=True)
class DecodedImage:
    content: bytes
    content_hash: str
    media_type: str
    width: int
    height: int


def _sniff_format_and_size(content: bytes) -> tuple[str | None, int | None, int | None]:
    """Read dimensions from PNG/JPEG headers before Pillow decodes pixels."""
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        if len(content) >= 24:
            width, height = struct.unpack(">II", content[16:24])
            return "PNG", width, height
        return "PNG", None, None
    if content[:2] == b"\xff\xd8":
        index = 2
        while index + 9 <= len(content):
            if content[index] != 0xFF:
                index += 1
                continue
            marker = content[index + 1]
            index += 2
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                continue
            if index + 2 > len(content):
                break
            length = struct.unpack(">H", content[index:index + 2])[0]
            if length < 2:
                break
            if (0xC0 <= marker <= 0xCF) and marker not in (0xC4, 0xC8, 0xCC):
                if index + 7 <= len(content):
                    height, width = struct.unpack(">HH", content[index + 3:index + 7])
                    return "JPEG", width, height
                return "JPEG", None, None
            index += length
        return "JPEG", None, None
    return None, None, None


def decode_source(image_base64: str) -> DecodedImage:
    if len(image_base64) > MAX_REQUEST_CHARS:
        raise ApiError(413, "REQUEST_TOO_LARGE", "请求体超过大小限制",
                       cause=f"image_base64 超过 {MAX_REQUEST_CHARS} 字符",
                       fix="压缩图片或降低分辨率后重试")
    try:
        content = base64.b64decode(image_base64, validate=True)
    except (binascii.Error, ValueError):
        raise ApiError(422, "INVALID_BASE64", "图片来源不是合法 base64",
                       cause="base64 解码失败", fix="检查上传内容是否为完整 base64")
    if not content:
        raise ApiError(422, "EMPTY_IMAGE", "图片来源为空", fix="选择非空图片")
    if len(content) > MAX_SOURCE_BYTES:
        raise ApiError(413, "SOURCE_TOO_LARGE", "原件超过大小限制",
                       cause=f"解码后 {len(content)} 字节 > {MAX_SOURCE_BYTES}",
                       fix="压缩到限制以内后重试")
    sniffed, header_width, header_height = _sniff_format_and_size(content)
    if sniffed is None:
        raise ApiError(415, "UNSUPPORTED_IMAGE_TYPE", "只接受 PNG 或 JPEG",
                       cause="文件头不是 PNG/JPEG", fix="转换为 PNG/JPEG 后重试")
    if header_width and header_height and header_width * header_height > MAX_PIXELS:
        raise ApiError(413, "IMAGE_TOO_MANY_PIXELS", "图片像素超过限制",
                       cause=f"header {header_width}x{header_height} > {MAX_PIXELS}",
                       fix="缩小图片后重试")
    try:
        with Image.open(io.BytesIO(content)) as probe:
            fmt = probe.format
            width, height = probe.size
            if width * height > MAX_PIXELS:
                raise ApiError(413, "IMAGE_TOO_MANY_PIXELS", "图片像素超过限制",
                               cause=f"{width}x{height} > {MAX_PIXELS}",
                               fix="缩小图片后重试")
            probe.verify()
        if fmt not in ALLOWED_FORMATS:
            raise ApiError(415, "UNSUPPORTED_IMAGE_TYPE", "只接受 PNG 或 JPEG",
                           cause=f"实际格式 {fmt!r}", fix="转换为 PNG/JPEG 后重试")
        with Image.open(io.BytesIO(content)) as image:
            image.load()
            width, height = image.size
            if width <= 0 or height <= 0:
                raise ApiError(422, "INVALID_IMAGE_DIMENSIONS", "图片尺寸非法")
            if width * height > MAX_PIXELS:
                raise ApiError(413, "IMAGE_TOO_MANY_PIXELS", "图片像素超过限制",
                               cause=f"{width}x{height} > {MAX_PIXELS}",
                               fix="缩小图片后重试")
    except ApiError:
        raise
    except Image.DecompressionBombError as exc:
        raise ApiError(413, "IMAGE_TOO_MANY_PIXELS", "图片像素超过限制",
                       cause=f"Pillow decompression bomb guard: {exc}",
                       fix="缩小图片后重试") from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ApiError(415, "INVALID_IMAGE", "图片无法完整解码",
                       cause=f"{type(exc).__name__}: {exc}",
                       fix="确认文件未截断且为真实 PNG/JPEG") from exc
    return DecodedImage(
        content=content,
        content_hash=hashlib.sha256(content).hexdigest(),
        media_type=ALLOWED_FORMATS[fmt],
        width=width,
        height=height,
    )


def synthetic_png(width: int = 64, height: int = 96) -> bytes:
    """Deterministic synthetic image for tests/demos; never a real heritage page."""
    image = Image.new("RGB", (width, height), (235, 225, 200))
    for x in range(width):
        for y in range(0, height, 8):
            image.putpixel((x, y), (80, 60, 40))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
