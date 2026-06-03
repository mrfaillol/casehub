"""CaseHub - Maestro training pipeline scaffold.

GATED MODULE: nothing in here runs unless settings.MAESTRO_TRAINING_COLLECTION_ENABLED
is True AND per-org consent is recorded (see whatsapp_inbound_service.py for the entry
point that decides whether to seed a sample).

Layout (filled progressively until beta agosto):
  data_collector.py    — turn (inbound, field_request, admin-resolve) tuples into samples
  dataset_builder.py   — group samples into JSONL train/eval splits per field_name
  embeddings.py        — Ollama local embeddings; no external LLM call by default
  eval_harness.py      — toy precision/recall for trivial fields (cep, cpf, rg)

NOTHING TRAINS A MODEL. Training itself requires Council ruling per
agents/knowledge/council/principles.md + DPA per provider — see PR #479 spec.
"""
