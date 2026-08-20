"""Deterministic, dependency-free PDF fixture builder for tests.

Hand-writes a minimal valid PDF (one object per page, a content stream per
page drawing text with the built-in Helvetica font, and a plain xref table).
No external tool or network access required, so tests stay fast and
reproducible.
"""


def build_minimal_pdf(page_texts: list[str]) -> bytes:
    n = len(page_texts)
    page_first = 3
    content_first = page_first + n
    font_num = content_first + n

    bodies: list[bytes] = []

    bodies.append(b"<< /Type /Catalog /Pages 2 0 R >>")

    kids = " ".join(f"{page_first + i} 0 R" for i in range(n))
    bodies.append(f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode("ascii"))

    for i in range(n):
        bodies.append(
            (
                f"<< /Type /Page /Parent 2 0 R "
                f"/Resources << /Font << /F1 {font_num} 0 R >> >> "
                f"/MediaBox [0 0 612 792] /Contents {content_first + i} 0 R >>"
            ).encode("ascii")
        )

    for text in page_texts:
        escaped = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        stream = f"BT /F1 24 Tf 72 712 Td ({escaped}) Tj ET".encode("latin-1")
        bodies.append(f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream")

    bodies.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    assert len(bodies) == font_num

    out = bytearray()
    out += b"%PDF-1.4\n"
    offsets = [0]
    for i, body in enumerate(bodies, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode("ascii")
        out += body
        out += b"\nendobj\n"

    xref_offset = len(out)
    total_objs = len(bodies) + 1
    out += f"xref\n0 {total_objs}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode("ascii")
    out += f"trailer\n<< /Size {total_objs} /Root 1 0 R >>\n".encode("ascii")
    out += f"startxref\n{xref_offset}\n%%EOF".encode("ascii")

    return bytes(out)


def build_blank_pdf(page_count: int = 1) -> bytes:
    """A structurally valid PDF whose pages have no text content — the
    scanned/image-only PDF case, which yields no extractable text."""
    return build_minimal_pdf([""] * page_count)
