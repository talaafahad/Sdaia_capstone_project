/**
 * Optional supporting-document upload (implementation plan section 13).
 *
 * Accepts text-layer PDF and plain text only — images / scanned documents
 * needing OCR are explicitly out of scope for the prototype.
 *
 * Per section 13's closing note, this component feeds
 * `CaseState.area_sqm_from_document` **directly** rather than routing through a
 * generic attachments bucket, because the Verifier's discrepancy check depends
 * on that one field being populated before it runs.
 *
 * Phase A: extraction is mocked in the browser. Phase B replaces
 * `mockExtract()` with a real PyMuPDF call on the backend — the
 * `UploadedDocument` shape it returns stays the same.
 */

import { useRef, useState } from 'react';

import type { UploadedDocument } from '../store/caseStore';
import styles from './DocumentUpload.module.css';

interface DocumentUploadProps {
  document: UploadedDocument | null;
  onChange: (doc: UploadedDocument | null) => void;
  disabled?: boolean;
}

const MAX_BYTES = 10 * 1024 * 1024;

/** Stands in for PyMuPDF text extraction until Phase B. */
const MOCK_LEASE_AREA_SQM = 95;

function mockExtract(file: File): UploadedDocument | { error: string } {
  const lower = file.name.toLowerCase();
  const isPdf = file.type === 'application/pdf' || lower.endsWith('.pdf');
  const isTxt = file.type.startsWith('text/') || lower.endsWith('.txt');

  if (!isPdf && !isTxt) {
    return {
      error:
        'Only text-layer PDF and plain text files are accepted. Scanned images needing OCR are out of scope for this prototype.',
    };
  }
  if (file.size > MAX_BYTES) {
    return { error: 'File is larger than 10 MB.' };
  }

  if (isPdf) {
    return {
      filename: file.name,
      size_bytes: file.size,
      kind: 'pdf',
      extracted_area_sqm: MOCK_LEASE_AREA_SQM,
      extraction_note: `Mocked extraction — a leased area of ${MOCK_LEASE_AREA_SQM} sqm was read from the document's text layer. Phase B replaces this with PyMuPDF.`,
    };
  }

  return {
    filename: file.name,
    size_bytes: file.size,
    kind: 'txt',
    extracted_area_sqm: null,
    extraction_note:
      'Plain text accepted as additional context. No area value extracted, so the discrepancy check will not run on this file.',
  };
}

export function DocumentUpload({ document, onChange, disabled = false }: DocumentUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const handleFile = (file: File | undefined) => {
    if (!file) return;
    const result = mockExtract(file);
    if ('error' in result) {
      setError(result.error);
      onChange(null);
      return;
    }
    setError(null);
    onChange(result);
  };

  const clear = () => {
    setError(null);
    onChange(null);
    if (inputRef.current) inputRef.current.value = '';
  };

  return (
    <div className={styles.wrap}>
      <div className={styles.labelRow}>
        <span className={styles.label}>Supporting document</span>
        <span className={styles.optional}>Optional</span>
      </div>

      {!document && (
        <div
          className={`${styles.drop} ${dragging ? styles.dropActive : ''} ${
            disabled ? styles.dropDisabled : ''
          }`}
          onDragOver={(e) => {
            e.preventDefault();
            if (!disabled) setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            if (!disabled) handleFile(e.dataTransfer.files?.[0]);
          }}
        >
          <p className={styles.dropTitle}>Drop a lease PDF here</p>
          <p className={styles.dropHint}>
            PDF (text layer) or TXT · max 10 MB. A lease is what makes the discrepancy check run.
          </p>
          <button
            type="button"
            className={styles.browse}
            onClick={() => inputRef.current?.click()}
            disabled={disabled}
          >
            Choose a file
          </button>
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,application/pdf,.txt,text/plain"
            className={styles.input}
            onChange={(e) => handleFile(e.target.files?.[0])}
            disabled={disabled}
          />
        </div>
      )}

      {document && (
        <div className={styles.file}>
          <div className={styles.fileHead}>
            <span className={styles.fileName}>{document.filename}</span>
            <button type="button" className={styles.remove} onClick={clear} disabled={disabled}>
              Remove
            </button>
          </div>
          <p className={styles.fileMeta}>
            {document.kind.toUpperCase()} · {(document.size_bytes / 1024).toFixed(0)} KB
          </p>

          {document.extracted_area_sqm !== null && (
            <p className={styles.extracted}>
              <strong>area_sqm_from_document = {document.extracted_area_sqm}</strong>
              <span className={styles.mockTag}>MOCKED EXTRACTION</span>
            </p>
          )}
          <p className={styles.note}>{document.extraction_note}</p>
        </div>
      )}

      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
