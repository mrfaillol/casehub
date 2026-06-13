from datetime import date

from services.calendario_judicial import inferir_tribunal, normalizar_tribunal
from services.prazos_cpc import eh_dia_util, proximo_dia_util


def test_corpus_christi_suspension_for_tjmg_2026():
    assert eh_dia_util(date(2026, 6, 4), estado="MG", tribunal="TJMG") is False
    assert eh_dia_util(date(2026, 6, 5), estado="MG", tribunal="TJMG") is False
    assert proximo_dia_util(date(2026, 6, 4), estado="MG", tribunal="TJMG") == date(2026, 6, 8)


def test_mg_forensic_fallback_for_unknown_tribunal_2026():
    assert eh_dia_util(date(2026, 6, 5), estado="MG", tribunal="Outro") is False
    assert eh_dia_util(date(2026, 6, 5), estado="MG", tribunal=None) is False
    assert proximo_dia_util(date(2026, 6, 5), estado="MG", tribunal="Outro") == date(2026, 6, 8)


def test_inferir_tribunal_from_cnj_number():
    assert inferir_tribunal("0000000-00.2026.5.03.0000") == "TRT3"
    assert inferir_tribunal("0000000-00.2026.8.13.0000") == "TJMG"
    assert normalizar_tribunal("TRF-6") == "TRF6"
