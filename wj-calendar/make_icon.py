"""바탕화면 아이콘(calendar.ico)을 외부 라이브러리 없이 만든다."""
import struct
import zlib
from pathlib import Path


def png(size: int) -> bytes:
    blue, dark, white = (91, 108, 255, 255), (54, 69, 214, 255), (255, 255, 255, 255)
    r = size // 6
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            # 둥근 모서리
            cx = min(max(x, r), size - 1 - r)
            cy = min(max(y, r), size - 1 - r)
            if (x - cx) ** 2 + (y - cy) ** 2 > r * r:
                row += bytes((0, 0, 0, 0))
                continue
            c = dark if y < size * 0.28 else blue
            # 흰 날짜 칸 3x2
            gx, gy = (x - size * 0.16) / (size * 0.68), (y - size * 0.40) / (size * 0.46)
            if 0 <= gx < 1 and 0 <= gy < 1:
                fx, fy = (gx * 3) % 1, (gy * 2) % 1
                if 0.12 < fx < 0.88 and 0.14 < fy < 0.86:
                    c = white
            row += bytes(c)
        rows.append(bytes(row))
    raw = zlib.compress(b"".join(rows), 9)

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", raw) + chunk(b"IEND", b""))


def ico(path: Path, sizes=(16, 32, 48, 256)) -> None:
    imgs = [png(s) for s in sizes]
    head = struct.pack("<HHH", 0, 1, len(imgs))
    off = 6 + 16 * len(imgs)
    dirs = b""
    for s, im in zip(sizes, imgs):
        dirs += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(im), off)
        off += len(im)
    path.write_bytes(head + dirs + b"".join(imgs))


if __name__ == "__main__":
    ico(Path(__file__).resolve().parent / "calendar.ico")
