#!/usr/bin/env python3
"""
CaseHub - Upsert de prazos processuais a partir da planilha oficial Example Legal.

Lógica:
- Para processos com número CNJ: busca o case pelo número, encontra o prazo
  existente para esse case_id e atualiza. Se não existir, insere.
- Para "PROCESSO ADMINISTRATIVO": insere sempre como novo (sem case_id,
  com processo_override e cliente_override) se não houver prazo idêntico.
- Responsável: preserva o existente se a planilha não informou nenhum.
- Executa em org_id=4 (Example Legal).

Uso:
    python scripts/upsert_prazos_planilha.py [--dry-run]
"""
import argparse
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import get_db, init_db
from sqlalchemy import text

ORG_ID = 4

# ---------------------------------------------------------------------------
# Dados da planilha (gerado automaticamente a partir do Excel)
# ---------------------------------------------------------------------------
PLANILHA = [
    {"cliente": "REGINA VILLANOVA DE CARVALHO", "parte": "SEBASTIÃO VILANOVA", "processo": "1007113-93.2026.8.13.0145", "data_intimacao": "2026-06-02", "dias": 30, "data_vencimento": "2026-07-14", "descricao": "Aguarda documentação (requerimento inss)", "status": "pendente"},
    {"cliente": "NORMA TAVARES DE OLIVEIRA TEODOSIO", "parte": "JOSÉ RICARDO FREITAS LISBOA", "processo": "5000034-79.2026.8.13.0408", "data_intimacao": "2026-05-19", "dias": 30, "data_vencimento": "2026-06-30", "descricao": "apresentar certidões negativas em nome do de cujus, bem como do imóvel partilhado. Ademais, deve ser apresentada certidão de quitação do ITCD e de inexistência de testamento", "status": "pendente"},
    {"cliente": "MARINA DE ALMEIDA PIRES", "parte": "WALTER LORDELLO RAPOSO NETO", "processo": "1013351-31.2026.8.13.0145", "data_intimacao": "2026-06-09", "dias": 15, "data_vencimento": "2026-06-30", "descricao": "Saiu a tutela - pedir ofício (inicial) // FEITO", "status": "pendente"},
    {"cliente": "REGINA VIEIRA BARBOSA", "parte": "IBÉRIA LINHAS AÉREAS", "processo": "5003298-88.2024.8.13.0145", "data_intimacao": "2026-06-09", "dias": 15, "data_vencimento": "2026-06-30", "descricao": "Procedente o recurso", "status": "pendente"},
    {"cliente": "ROGÉRIO CONDE TOLEDO DE ALMEIDA", "parte": None, "processo": "PROCESSO ADMINISTRATIVO", "data_intimacao": "2026-06-26", "dias": 1, "data_vencimento": "2026-06-29", "descricao": "Para dar continuidade ao pedido, ligue no telefone 135 e agende a perícia médica de Auxílio-Acidente.", "status": "pendente"},
    {"cliente": "ANA CLÁUDIA DOS SANTOS SILVA E LEONARDO PASSOS DE OLIVEIRA", "parte": None, "processo": "1007105-19.2026.8.13.0145", "data_intimacao": "2026-06-03", "dias": 15, "data_vencimento": "2026-06-24", "descricao": "Ciencia // FEITO", "status": "pendente"},
    {"cliente": "ADRIANA APARECIDA DAVID", "parte": "UNIMED JF", "processo": "1008769-85.2026.8.13.0145", "data_intimacao": "2026-06-03", "dias": 15, "data_vencimento": "2026-06-24", "descricao": "Impugnação à contestação", "status": "pendente"},
    {"cliente": "RAFAELA CRISTINA SILVA DE ABREU", "parte": "ANDRE LUIZ PEREIRA DORE", "processo": "1012290-38.2026.8.13.0145", "data_intimacao": "2026-06-02", "dias": 15, "data_vencimento": "2026-06-23", "descricao": "Concedida tutela antecipada dos alimentos // FEITO", "status": "pendente"},
    {"cliente": "SUELI APARECIDA DUTRA E MARIA DE LOURDES DUTRA", "parte": "ELIZRA, MUNICÍPIO CONSELEHIRO LAFAEITE, FERNANDO, DELCIO, ADRIADNE", "processo": "0050048-76.2011.8.13.0183", "data_intimacao": "2026-06-02", "dias": 15, "data_vencimento": "2026-06-23", "descricao": "Processo de reintegração de posse - ver c o example-user", "status": "pendente"},
    {"cliente": "ISAMARA GOMES DA SILVA", "parte": "FELIPE THOMAZ DA SILVA", "processo": "5042579-17.2025.8.13.0145", "data_intimacao": "2026-06-02", "dias": 15, "data_vencimento": "2026-06-23", "descricao": "Ciência do despacho (indeferiu pedido de revisão da modalidade de guarda feito pelo MP) // FEITO", "status": "pendente"},
    {"cliente": "ASSOCIAÇÃO SANTA CLARA", "parte": "DIEGO ROCHA RIBEIRO", "processo": "1007669-32.2025.8.13.0145", "data_intimacao": "2026-06-09", "dias": 10, "data_vencimento": "2026-06-23", "descricao": "Recolher custas p SISBAJUD + planilha de atualização de débitos", "status": "pendente"},
    {"cliente": "ROSANA APARECIDA FERNANDES", "parte": "INSS", "processo": "6007708-28.2026.4.06.3801", "data_intimacao": "2026-06-09", "dias": 10, "data_vencimento": "2026-06-23", "descricao": "Indeferida a petição inicial e extinto o processo", "status": "pendente"},
    {"cliente": "FÁBIO APARECIDO DA SILVA", "parte": "INSS", "processo": "6008669-66.2026.4.06.3801", "data_intimacao": "2026-06-01", "dias": 15, "data_vencimento": "2026-06-22", "descricao": "Anexar indeferimento administrativo - comunicações", "status": "pendente"},
    {"cliente": "FABIANA VALÉRIO LOPES", "parte": "OTÁVIO MARTINS CORREA", "processo": "1008284-22.2025.8.13.0145", "data_intimacao": "2026-06-01", "dias": 15, "data_vencimento": "2026-06-22", "descricao": "Informar outro endereço do réu // FEITO", "status": "pendente"},
    {"cliente": "LUIZA MARIA DOS SANTOS NONATO", "parte": "UNIÃO - FAZENDA NACIONAL", "processo": "6005941-52.2026.4.06.3801", "data_intimacao": "2026-06-01", "dias": 15, "data_vencimento": "2026-06-22", "descricao": "Fazer petição informando que não precisa de prévio indeferimento // FEITO", "status": "pendente"},
    {"cliente": "CLAUDIA REJANE GONÇALVES BERNARDO", "parte": "GILMAR GOMES DA SILVA", "processo": "1010940-15.2026.8.13.0145", "data_intimacao": "2026-06-01", "dias": 15, "data_vencimento": "2026-06-22", "descricao": "Apresentar documentação comprobatória da hipossuficiência + certidão de nascimento/casamento atualizada das partes, bem como declarações de, pelo menos, 3 testemunhas que indiquem as datas de início e término da união, as quais deverão corroborar as informações constantes entre si e com os documentos colecionados nos autos", "status": "pendente"},
    {"cliente": "ELIZA SOUZA GOMES FARIA", "parte": "INSS", "processo": "6008326-70.2026.4.06.3801", "data_intimacao": "2026-06-01", "dias": 15, "data_vencimento": "2026-06-22", "descricao": "Emenda à petição inicial indicando, objetivamente, todas as pessoas que residem consigo no mesmo endereço, especificando o grau de parentesco e os rendimentos porventura auferidos, ainda que informais, tendo em vista que a concessão do benefício assistencial postulado depende da apuração da renda per capita do grupo familiar e não somente do requerente + docs da família = inscrição no cad unico", "status": "pendente"},
    {"cliente": "FABIANA VALÉRIO LOPES", "parte": "OTAVIO MARTINS CORREA", "processo": "1008587-36.2025.8.13.0145", "data_intimacao": "2026-06-08", "dias": 10, "data_vencimento": "2026-06-22", "descricao": "Atualizar o memorial de débito e requerer o de direito: multa de dez por cento e, também, de honorários advocatícios de dez por cento // FEITO", "status": "pendente"},
    {"cliente": "SANDRO ALVES DA SILVA", "parte": "INSS", "processo": "5000705-09.2026.4.02.5108", "data_intimacao": "2026-06-08", "dias": 10, "data_vencimento": "2026-06-22", "descricao": "(JFRJ) Vista sobre despacho - apresentar contatos (telefone, e-mail) e ponto de referência caso o endereço seja de difícil acesso, a fim de possibilitar a verificação social", "status": "pendente"},
    {"cliente": "GRACIELE MARTINS DE OLIVEIRA", "parte": "INSS", "processo": "6006462-94.2026.4.06.3801", "data_intimacao": "2026-06-08", "dias": 10, "data_vencimento": "2026-06-22", "descricao": "Julgado improcedente o pedido", "status": "pendente"},
    {"cliente": "VANILDE MARIA DA SILVA BRAZ", "parte": "INSS", "processo": "6014190-60.2024.4.06.3801", "data_intimacao": "2026-06-08", "dias": 10, "data_vencimento": "2026-06-22", "descricao": "RPV sacado - ciência", "status": "pendente"},
    {"cliente": "VIRGILIO SALLES DE ALMEIDA", "parte": "ELIANA VITORIA DE OLIVEIRA", "processo": "5006130-02.2021.8.13.0145", "data_intimacao": "2026-06-08", "dias": 10, "data_vencimento": "2026-06-22", "descricao": "contrarrazões à apelação", "status": "pendente"},
    {"cliente": "PRISCILA TERESA", "parte": "RODRIGO", "processo": "5031989-78.2025.8.13.0145", "data_intimacao": "2026-05-30", "dias": 15, "data_vencimento": "2026-06-19", "descricao": "MANIFESTAR- VALÉRIA VAI INSTRUIR", "status": "pendente"},
    {"cliente": "JOSIANE MARTINS DA SILVA MARCATO", "parte": None, "processo": "PROCESSO ADMINISTRATIVO", "data_intimacao": "2026-06-17", "dias": 1, "data_vencimento": "2026-06-18", "descricao": "EXAMPLE USER -1) ANEXAR IDENTIDADE E CPF DE JOSEMAR COUTINHO\n2) CERTIDÃO DE NASCIMENTO DE JOSIANE MARTINS\n3) CERTIDÃO JUDICIAL QUE ATESTE O REGIME E A DATA DA RECLUSÃO", "status": "pendente"},
    {"cliente": "DANILA BATISTA DUTRA CAMARA", "parte": "BERNARDO FIGUEIREDO", "processo": "5041689-78.2025.8.13.0145", "data_intimacao": "2026-05-27", "dias": 15, "data_vencimento": "2026-06-17", "descricao": "Impugnar contestação c/c reconvenção", "status": "pendente"},
    {"cliente": "FRANCO NIBI", "parte": "CONDOMÍNIO DO EDIFÍCIO PLAZA MAYOR", "processo": "5012604-18.2023.8.13.0145", "data_intimacao": "2026-06-09", "dias": 5, "data_vencimento": "2026-06-16", "descricao": "Esperar corac", "status": "pendente"},
    {"cliente": "ADALMAR WILSON NEVES LEITE", "parte": "INSS", "processo": "6008327-55.2026.4.06.3801", "data_intimacao": "2026-06-09", "dias": 5, "data_vencimento": "2026-06-16", "descricao": "Perícia designada", "status": "pendente"},
    {"cliente": "ASSOCIAÇÃO SANTA CLARA", "parte": "UNIÃO - FAZENDA NACIONAL", "processo": "5001047-95.2023.4.02.5117", "data_intimacao": "2026-05-25", "dias": 15, "data_vencimento": "2026-06-15", "descricao": "Conferir com o example-user - TJRJ - example-user vai fazer", "status": "pendente"},
    {"cliente": "EXAMPLE USER EXAMPLE LEGAL DE ALMEIDA", "parte": "GUILHERME ARAÚJO SIMÕES", "processo": "1016964-59.2026.8.13.0145", "data_intimacao": "2026-06-08", "dias": 5, "data_vencimento": "2026-06-15", "descricao": "Audiência designada - 07/07/2026 15:30 // FEITO", "status": "pendente"},
    {"cliente": "MARIANA REZENDE DA SILVA", "parte": "INSS", "processo": "6006466-34.2026.4.06.3801", "data_intimacao": "2026-06-08", "dias": 5, "data_vencimento": "2026-06-15", "descricao": "Vista sobre RPV", "status": "pendente"},
    {"cliente": "MARCIA APARECIDA DE OLIVEIRA", "parte": None, "processo": "PROCESSO ADMINISTRATIVO", "data_intimacao": "2026-06-08", "dias": 3, "data_vencimento": "2026-06-11", "descricao": "COMPARECER NO DIA 17/6/2026, AS 10:00, NO INSS DE JUIZ DE FORA/MG, PARA REALIZAÇÃO DE PERÍCIA MÉDICA LC 142.\nENDEREÇO: AV DOS ANDRADAS Nº 221, TÉRREO, CENTRO JUIZ DE FORA/MG CEP: 36.036-000", "status": "pendente"},
    {"cliente": "WLADIMIR SANTOS BARRETO", "parte": None, "processo": "1000633-12.2025.8.13.0056", "data_intimacao": "2026-05-20", "dias": 15, "data_vencimento": "2026-06-10", "descricao": "Valéria - emendar a inicial + ver sobre gratuidade de justiça // EMENDA FEITA, VER DOCUMENTOS", "status": "pendente"},
    {"cliente": "VALÉRIA CRISTINA DA COSTA", "parte": "ANTONIO JORGE GOMES MOREIRA", "processo": "5033503-66.2025.8.13.0145", "data_intimacao": "2026-06-03", "dias": 5, "data_vencimento": "2026-06-10", "descricao": "Cessado desconto da pensão no inss", "status": "pendente"},
]


def _parse_date(s):
    from datetime import datetime
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def upsert_prazos(dry_run: bool = False):
    init_db()
    db = next(get_db())

    updated = 0
    inserted = 0
    skipped = 0
    errors = []

    try:
        for row in PLANILHA:
            processo = row["processo"]
            cliente_nome = row["cliente"]
            parte = row.get("parte")
            data_intimacao = _parse_date(row["data_intimacao"])
            data_vencimento = _parse_date(row["data_vencimento"])
            dias = row.get("dias", 15)
            descricao = row.get("descricao") or ""
            status = row.get("status", "pendente")

            # ----------------------------------------------------------------
            # data_inicio = next business day after data_intimacao
            # ----------------------------------------------------------------
            if data_intimacao:
                di = data_intimacao + __import__("datetime").timedelta(days=1)
                # Skip weekends
                while di.weekday() >= 5:
                    di += __import__("datetime").timedelta(days=1)
                data_inicio = di
            else:
                data_inicio = None

            # ----------------------------------------------------------------
            # PROCESSO ADMINISTRATIVO — insert without case_id
            # ----------------------------------------------------------------
            if processo == "PROCESSO ADMINISTRATIVO":
                # Check if identical record already exists
                dup = db.execute(text("""
                    SELECT id FROM prazos_processuais
                    WHERE org_id = :org_id
                      AND processo_override = 'PROCESSO ADMINISTRATIVO'
                      AND cliente_override ILIKE :nome
                      AND data_intimacao = :di
                    LIMIT 1
                """), {"org_id": ORG_ID, "nome": f"%{cliente_nome.split()[0]}%", "di": data_intimacao}).fetchone()

                if dup:
                    print(f"[skip] PROC.ADMIN {cliente_nome} já existe (id={dup[0]})")
                    skipped += 1
                    continue

                if not dry_run:
                    db.execute(text("""
                        INSERT INTO prazos_processuais
                            (org_id, tipo, data_intimacao, data_inicio, data_vencimento,
                             dias_prazo, status, descricao, uf, dobro,
                             processo_override, cliente_override, updated_at)
                        VALUES
                            (:org_id, '', :di, :ds, :dv, :dias, :status, :desc, 'MG', false,
                             'PROCESSO ADMINISTRATIVO', :cli, now())
                    """), {
                        "org_id": ORG_ID,
                        "di": data_intimacao,
                        "ds": data_inicio,
                        "dv": data_vencimento,
                        "dias": dias,
                        "status": status,
                        "desc": descricao,
                        "cli": cliente_nome,
                    })
                print(f"[insert] PROC.ADMIN {cliente_nome} venc={data_vencimento}")
                inserted += 1
                continue

            # ----------------------------------------------------------------
            # Numbered processo — find case_id
            # ----------------------------------------------------------------
            case_row = db.execute(text("""
                SELECT id FROM cases
                WHERE org_id = :org_id AND numero_processo = :num
                LIMIT 1
            """), {"org_id": ORG_ID, "num": processo}).fetchone()

            case_id = case_row[0] if case_row else None

            if not case_id:
                # Create the client and case if missing
                # Find client first
                parts = cliente_nome.split(None, 1)
                first = parts[0]
                last = parts[1] if len(parts) > 1 else ""

                client_row = db.execute(text("""
                    SELECT id FROM clients
                    WHERE org_id = :org_id
                      AND (first_name || ' ' || last_name) ILIKE :nome
                    LIMIT 1
                """), {"org_id": ORG_ID, "nome": f"%{cliente_nome}%"}).fetchone()

                if not client_row:
                    # Try first name only
                    client_row = db.execute(text("""
                        SELECT id FROM clients
                        WHERE org_id = :org_id AND first_name ILIKE :fn
                        LIMIT 1
                    """), {"org_id": ORG_ID, "fn": f"%{first}%"}).fetchone()

                if client_row:
                    client_id = client_row[0]
                else:
                    if not dry_run:
                        db.execute(text("""
                            INSERT INTO clients (first_name, last_name, org_id, status)
                            VALUES (:fn, :ln, :org_id, 'active')
                        """), {"fn": first, "ln": last, "org_id": ORG_ID})
                        db.flush()
                        client_id = db.execute(text(
                            "SELECT id FROM clients WHERE org_id=:o AND first_name=:fn ORDER BY id DESC LIMIT 1"
                        ), {"o": ORG_ID, "fn": first}).fetchone()[0]
                        print(f"  [new-client] {cliente_nome} id={client_id}")
                    else:
                        client_id = -1

                import secrets as _sec
                case_number = f"PROC-{_sec.token_hex(3).upper()}"
                case_name = f"{processo} - {cliente_nome}"

                if not dry_run:
                    db.execute(text("""
                        INSERT INTO cases
                            (client_id, case_number, numero_processo, polo_passivo,
                             status, case_name, org_id)
                        VALUES
                            (:cid, :cn, :np, :pp, 'ativo', :cname, :org_id)
                    """), {
                        "cid": client_id,
                        "cn": case_number,
                        "np": processo,
                        "pp": parte,
                        "cname": case_name,
                        "org_id": ORG_ID,
                    })
                    db.flush()
                    case_id = db.execute(text(
                        "SELECT id FROM cases WHERE org_id=:o AND numero_processo=:np LIMIT 1"
                    ), {"o": ORG_ID, "np": processo}).fetchone()[0]
                    print(f"  [new-case] {processo} id={case_id}")

            # ----------------------------------------------------------------
            # Find existing prazo for this case_id
            # ----------------------------------------------------------------
            existing = None
            if case_id and case_id != -1:
                existing = db.execute(text("""
                    SELECT id, responsavel FROM prazos_processuais
                    WHERE org_id = :org_id AND case_id = :cid
                    ORDER BY id ASC
                    LIMIT 1
                """), {"org_id": ORG_ID, "cid": case_id}).fetchone()

            if existing:
                prazo_id, existing_responsavel = existing
                # Preserve responsavel if not provided in spreadsheet
                final_responsavel = existing_responsavel  # keep existing by default

                if not dry_run:
                    db.execute(text("""
                        UPDATE prazos_processuais SET
                            data_intimacao = :di,
                            data_inicio    = :ds,
                            data_vencimento = :dv,
                            dias_prazo     = :dias,
                            status         = :status,
                            descricao      = :desc,
                            responsavel    = :resp,
                            updated_at     = now()
                        WHERE id = :pid
                    """), {
                        "di": data_intimacao,
                        "ds": data_inicio,
                        "dv": data_vencimento,
                        "dias": dias,
                        "status": status,
                        "desc": descricao,
                        "resp": final_responsavel,
                        "pid": prazo_id,
                    })
                print(f"[update] id={prazo_id} {processo} ({cliente_nome}) venc={data_vencimento} resp={final_responsavel!r}")
                updated += 1
            else:
                if not dry_run and case_id and case_id != -1:
                    db.execute(text("""
                        INSERT INTO prazos_processuais
                            (case_id, org_id, tipo, data_intimacao, data_inicio,
                             data_vencimento, dias_prazo, status, descricao, uf,
                             dobro, updated_at)
                        VALUES
                            (:cid, :org_id, '', :di, :ds,
                             :dv, :dias, :status, :desc, 'MG',
                             false, now())
                    """), {
                        "cid": case_id,
                        "org_id": ORG_ID,
                        "di": data_intimacao,
                        "ds": data_inicio,
                        "dv": data_vencimento,
                        "dias": dias,
                        "status": status,
                        "desc": descricao,
                    })
                print(f"[insert] {processo} ({cliente_nome}) venc={data_vencimento}")
                inserted += 1

        if not dry_run:
            db.commit()
        else:
            print("\n[DRY RUN — nenhuma alteração gravada]")

        print(f"\n✓ Concluído. Atualizados: {updated} | Inseridos: {inserted} | Pulados: {skipped}")
        if errors:
            print("Erros:")
            for e in errors:
                print(f"  {e}")

    except Exception as e:
        db.rollback()
        print(f"\nERRO: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    upsert_prazos(dry_run=args.dry_run)
