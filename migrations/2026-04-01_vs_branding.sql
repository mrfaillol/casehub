-- Migration: o cliente branding (org_id=42)
-- Cores: Azul Royal #1C2447 (primary), Branco (secondary), Dourado #B57F74 (accent)
-- Fonte: Maven Pro
-- [parceiro] pediu: "nao pesar azul na vista" — usar como accent, nao full background

UPDATE organizations
SET
    primary_color = '#1C2447',
    secondary_color = '#FFFFFF',
    settings = COALESCE(settings, '{}'::jsonb)
        || '{"accent_color": "#1C2447", "font_family": "Maven Pro", "theme_bg": "#f7f7f8"}'::jsonb,
    updated_at = NOW()
WHERE id = 42;
