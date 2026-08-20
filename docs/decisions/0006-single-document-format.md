# ADR-0006: Support one document format (.txt) for the initial MVP

**Status:** Accepted

## Context

The pipeline needs to turn an uploaded file into plain text before
chunking. The original project scope named "text extraction for the
currently supported format(s)" — deliberately open-ended on *which*
formats, not a request for a specific set. Deciding to ship with exactly
one format was a genuine scope decision made during implementation, not a
constraint handed down in advance.

## Decision

Support `.txt` only at this phase, via a `TextExtractor` abstract base
class and an `EXTRACTORS` registry keyed by file extension
(`rag/services/extractors.py`). Uploading an unsupported extension returns
a `400` with a clear message listing what's supported.

## Rationale

- **Proves the pipeline end-to-end before adding format-specific
  complexity.** PDF and DOCX extraction each bring their own failure modes
  (encrypted PDFs, scanned/image-only PDFs needing OCR, malformed OOXML,
  encoding edge cases) that are orthogonal to whether chunking, embedding,
  retrieval, and grounded generation work correctly. Isolating "can this
  pipeline answer questions correctly from real text" from "can this
  pipeline extract text from every real-world file" kept the MVP scope
  honest and demonstrable.
- **The extension point already exists and costs nothing today.** Adding a
  new format is: write one `TextExtractor` subclass, register it in
  `EXTRACTORS`. Nothing else in the pipeline (chunking, embedding, storage,
  the API, the frontend) needs to change — the upload endpoint already
  returns a clear, typed error for anything not yet registered rather than
  failing silently or guessing.
- **Failure is explicit, not silent.** `UnsupportedFileTypeError` maps to a
  `400` with the exact list of supported extensions
  (`rag/views.py::DocumentUploadView`), so the frontend can show the user
  precisely why an upload was rejected.

## Consequences

- Real-world "knowledge base" documents are very often PDFs or Word docs,
  not plain text — this is the single biggest practical limitation on this
  MVP's usefulness as-is, and is called out as such in the README rather
  than glossed over.
- No OCR, no scanned-document support, no HTML/Markdown-aware extraction.

## Alternatives considered

Shipping PDF support from the start was considered and deliberately
deferred — it's a larger, less certain effort (dependency choice between
`pypdf`, `pdfplumber`, `unstructured`, etc., plus handling malformed/
scanned PDFs) that doesn't change anything about how chunking, embedding,
retrieval, or generation behave once text exists. Adding it is the most
natural next increment (see [ROADMAP.md](../ROADMAP.md)).
