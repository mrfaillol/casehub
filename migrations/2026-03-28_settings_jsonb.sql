-- Migration: Add JSONB settings column to organizations
-- Date: 2026-03-28
-- Purpose: Admin customization panel for CaseHub Lite

ALTER TABLE organizations ADD COLUMN IF NOT EXISTS settings JSONB DEFAULT '{}';
