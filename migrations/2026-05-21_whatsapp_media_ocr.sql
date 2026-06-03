-- Migration: wa_messages.media_ocr_text — texto extraído de PDFs recebidos
-- Date: 2026-05-21
-- Author: Claude Opus 4.7 (1M ctx) — Fase 3 OCR, integration/whatsapp-clone-2026-05
--
-- Purpose:
--   OCR automático de PDFs recebidos via WhatsApp. O bot (server-lite.js)
--   extrai o texto com pdf-parse no momento do recebimento; este campo guarda
--   o resultado para o clone exibir e tornar buscável.
--
-- Idempotência: ADD COLUMN IF NOT EXISTS dentro de bloco guardado — segue o
--   template §4 da migration 2026-05-21_whatsapp_clone_schema.sql. Safe re-run.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'wa_messages') THEN
        BEGIN
            ALTER TABLE wa_messages
                ADD COLUMN IF NOT EXISTS media_ocr_text TEXT;
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'wa_messages.media_ocr_text: %', SQLERRM;
        END;
    END IF;
END $$;
