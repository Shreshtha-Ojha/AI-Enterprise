# ADR-0007: Add PDF support via pypdf, through the existing extractor registry

**Status:** Accepted — supersedes the "single format" scope of
[ADR-0006](./0006-single-document-format.md), not its reasoning.

## Context

[ADR-0006](./0006-single-document-format.md) shipped the MVP with `.txt`
only, deliberately, to prove the ingest → chunk → embed → retrieve →
generate loop before taking on format-specific extraction complexity. That
loop is now proven (49 tests, real-model retrieval verified). Real
knowledge-base documents are overwhelmingly PDF or Word, not plain text —
ADR-0006 named this as the MVP's single biggest practical limitation and
pointed at this as the natural next increment (see
[ROADMAP.md](../ROADMAP.md)).

The extension point ADR-0006 built for exactly this — `TextExtractor` +
the `EXTRACTORS` registry keyed by file extension
(`rag/services/extractors.py`) — is what made this a small, additive change
rather than a pipeline rewrite.

## Decision

Add `PdfExtractor(TextExtractor)`, registered under `.pdf` in `EXTRACTORS`,
using [`pypdf`](https://pypi.org/project/pypdf/) (pure-Python, no system
dependency like Poppler/`pdftotext`, actively maintained). Nothing outside
`rag/services/extractors.py` and `rag/services/ingestion.py` changed to
make this work — `get_extractor(filename)` already dispatched on extension,
so the pipeline, chunking, embedding, storage, and API layers are unaware a
new format exists.

Two small, additive extensions to the existing abstraction:

- `TextExtractor` gained an `extract_metadata(file_bytes) -> dict` method,
  defaulting to `{}` in the base class. `PdfExtractor` overrides it to
  return `{"page_count": N}`; `TxtExtractor` doesn't override it. This
  metadata flows through `IngestedDocument.metadata` (new field, default
  `{}`) into a new nullable `Document.page_count` column — `null` for
  `.txt`, populated for `.pdf`.
- A new `ExtractionError` exception (distinct from `UnsupportedFileTypeError`)
  for a file whose extension is supported but whose *content* isn't a
  parseable PDF (empty upload, corrupted file, or a non-PDF file renamed to
  `.pdf`). `DocumentUploadView` catches it the same way it already catches
  `UnsupportedFileTypeError` — a clean `400`, not a stack trace.

## Rationale

- **Proves the abstraction ADR-0006 designed.** Adding a second format was,
  as predicted: one subclass, one registry entry. No changes to
  `chunking.py`, `embedding.py`, `vector_store.py`, `pipeline.py`, or the
  API contract.
- **`pypdf` over alternatives.** `pdfplumber` and `unstructured` pull in
  heavier dependency trees (the latter is effectively a document-processing
  framework, not a library) for capability this project doesn't need yet
  (table extraction, layout analysis). `pypdf` does exactly one thing —
  read text and metadata from a PDF's object structure — with no system
  binary dependency, which keeps `poetry install` fully self-contained.
- **No OCR.** `pypdf` reads the text layer already embedded in a PDF. A
  scanned/image-only PDF has no text layer, so extraction legitimately
  yields empty text. That is not treated as a special case: it flows into
  the exact same "no extractable text after cleaning" path that a
  whitespace-only `.txt` upload already hit (`chunks == []` → `Document`
  recorded with `status=failed` and an explanatory message, HTTP `201`, not
  a crash). OCR (e.g. `pytesseract`) was deliberately not added — it's a
  materially different capability (image processing, not text parsing)
  with its own dependency and accuracy tradeoffs, out of scope for this
  increment.
- **`ExtractionError` is a new exception, not a repurposed one**, because
  it means something different from `UnsupportedFileTypeError`:
  unsupported-type is "we don't have an extractor for this extension at
  all"; extraction-error is "we have the right extractor, but this specific
  file's content doesn't parse." Both map to `400` today (nothing currently
  needs to distinguish them for the client), but conflating them into one
  exception would have made the error message dishonest — the file's
  extension may be exactly what the registry expects.

## Consequences

- **Two-parse cost per PDF upload.** `IngestionService.ingest()` calls both
  `extractor.extract()` and `extractor.extract_metadata()`, and
  `PdfExtractor` re-parses the PDF for each (`PdfReader` is constructed
  twice). For the file sizes this MVP handles synchronously in one HTTP
  request, this is negligible; it would be worth collapsing into a single
  parse (extractor returns `(text, metadata)` together) if PDFs large
  enough to make that matter show up.
- **No password/encrypted-PDF support.** An encrypted PDF fails the same
  way a corrupted one does — `ExtractionError`, `400` — not a request for a
  password.
- **DOCX and other formats remain unsupported** — this ADR only closes the
  PDF gap named in ADR-0006, not the whole "arbitrary document format"
  problem. Adding DOCX is the same shape of change (one more
  `TextExtractor` subclass) when it's next prioritized.

## Alternatives considered

- **OCR fallback for image-only PDFs** — rejected for this increment; a
  materially larger dependency and accuracy surface (Tesseract or a cloud
  OCR API) than "extract the text layer that's already there."
- **`pdfplumber`** — richer layout/table extraction, but a heavier
  dependency for capability this project's chunking strategy (flat
  character windows, see [ADR-0003](./0003-fixed-size-chunking.md)) doesn't
  use yet.
- **Returning `(text, metadata)` as a single tuple from `extract()`** —
  would avoid the double-parse noted above, but changes every
  `TextExtractor.extract()` call site and the existing `TxtExtractor`
  contract for a cost (two parses of a typically-small file) that isn't
  actually a problem yet. Deferred until it is one.
