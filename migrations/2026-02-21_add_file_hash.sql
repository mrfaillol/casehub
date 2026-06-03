-- Migration: Add file_hash column for deduplication
-- Date: 2026-02-21
-- Purpose: Enable SHA256-based deduplication for Google Drive sync

-- Add file hash column (SHA256 = 64 hex characters)
ALTER TABLE documents ADD COLUMN IF NOT EXISTS file_hash VARCHAR(64);

-- Create index for fast duplicate checking
CREATE INDEX IF NOT EXISTS idx_documents_file_hash ON documents(file_hash);

-- Add unique constraint to prevent duplicate hashes per client
-- (allows same file for different clients, but not duplicates for same client)
CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_unique_hash_client
  ON documents(file_hash, client_id)
  WHERE file_hash IS NOT NULL;

-- Add comment
COMMENT ON COLUMN documents.file_hash IS 'SHA256 hash for deduplication (calculated on file content)';
