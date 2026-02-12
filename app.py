import streamlit as st
import pdfplumber
import re
import pandas as pd
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

st.set_page_config(page_title="Leitor Cartão de Ponto", layout="centered")
st.title("📄 Leitor Inteligente - Cartão de Ponto")
st.write("Envie o PDF (TPBR ou JPBB). O app separa Motoboys e gera Excel no seu modelo.")

uploaded_file = st.file_uploader("Enviar PDF", type=["pdf"])


# ==========================
# Funções auxiliares (tempo)
# ==========================
def hhmm_to_minutes(hhmm: str) -> int:
    if not hhmm or ":" not in hhmm:
        return 0
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def minutes_to_hhmm(minutes: int) -> str:
    sign = "-" if minutes < 0 else ""
    minutes = abs(minutes)
    return f"{sign}{minutes // 60:02d}:{minutes % 60:02d}"


# ==========================
# Leitura do PDF
# ==========================
def extract_full_text(pdf_file) -> str:
    with pdfplumber.open(pdf_file) as pdf:
        parts = []
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
    return "\n".join(parts)


# ==========================
# Parser por funcionário
# ==========================
def parse_employee_blocks(texto: str) -> list[dict]:
    """
    Retorna uma lista de dicts por funcionário com:
      NOME, CARGO, NOTURNAS NORMAIS, TOTAL NORMAIS, TOTAL NOTURNO, FALTA, ATRASO, EXTRA 70%
    Observação: os TOTAIS variam por pessoa (2, 3, 4, 5, 6 valores...).
    """
    # Cada página contém "Cartão de Ponto", então usamos isso como separador de blocos
    blocos = re.split(r"\bCartão\s+de\s+Ponto\b", texto)

    out = []

    for bloco in blocos:
        if "NOME DO FUNCIONÁRIO:" not in bloco or "TOTAIS" not in bloco:
            continue

        nome_match = re.search(r"NOME DO FUNCIONÁRIO:\s*(.+?)\s+PIS", bloco)
        cargo_match = re.search(r"NOME DO CARGO:\s*(.+?)\s+CNPJ", bloco)
        totais_match = re.search(r"TOTAIS\s+([0-9:\s]+)", bloco)

        if not (nome_match and totais_match):
            continue

        nome = nome_match.group(1).strip()
        cargo = cargo_match.group(1).strip() if cargo_match else ""

        horarios = re.findall(r"\d{1,3}:\d{2}", totais_match.group(1))

        # Defaults
        noturnas_normais = "00:00"
        total_normais = "00:00"
        total_noturno = "00:00"
        falta_e_atraso = "00:00"
        extra70 = "00:00"

        # Heurísticas (cobrem TPBR e JPBB e variações):
        # 5 valores: NOTURNAS, TOTAL NORMAIS, TOTAL NOTURNO, FALTA E ATRASO, EXTRA 70
        if len(horarios) == 5:
            noturnas_normais, total_normais, total_noturno, falta_e_atraso, extra70 = horarios

        # 4 valores: TOTAL NORMAIS, TOTAL NOTURNO, FALTA E ATRASO, EXTRA 70
        elif len(horarios) == 4:
            total_normais, total_noturno, falta_e_atraso, extra70 = horarios

        # 6+ valores: normalmente inclui EXTRA 100% (ou outras colunas); usamos os 5 primeiros
        elif len(horarios) >= 6:
            base = horarios[:5]
            noturnas_normais, total_normais, total_noturno, falta_e_atraso, extra70 = base

        # 3 valores: (comum em alguns casos) TOTAL NORMAIS, TOTAL NOTURNO, EXTRA 70
        elif len(horarios) == 3:
            total_normais, total_noturno, extra70 = horarios

        # 2 valores: TOTAL NORMAIS, EXTRA 70  (sem noturno e sem falta/atraso)
        elif len(horarios) == 2:
            total_normais, extra70 = horarios

        # 1 valor: só TOTAL NORMAIS
        elif len(horarios) == 1:
            total_normais = horarios[0]

        # No PDF às vezes existe a coluna "FALTA E ATRASO" (tudo junto).
        # Para seu modelo, vamos colocar isso em FALTA e manter ATRASO zerado.
        falta = falta_e_atraso
        atraso = "00:00"

        out.append({
            "NOME": nome,
            "CARGO": cargo,
            "NOTURNAS NORMAIS": noturnas_normais,
            "TOTAL NORMAIS": total_normais,
            "TOTAL NOTURNO": total_noturno,
            "FALTA": falta,
            "ATRASO": atraso,
            "EXTRA 70%": extra70,
        })

    return out


# ==========================
# Excel formatado (modelo)
# ==========================
def build_excel(df_func: pd.DataFrame, df_moto: pd.DataFrame) -> BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "RELATORIO"

    thin = Side(style="thin", color="000000")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    header_gray = PatternFill(start_color="BFBFBF", fill_type="solid")
    title_yellow = PatternFill(start_color="FFFF00", fill_type="solid")

    def style_cell(cell, bold=False, fill=None, center=True):
        cell.font = Font(bold=bold)
        if center:
            cell.alignment = Alignment(horizontal="center", vertical="center")
        if fill:
            cell.fill = fill
        cell.border = border

    # ===== BLOCO 1: FUNCIONÁRIOS =====
    start_row = 2

    # Cabeçalho bloco 1
    for col, name in enumerate(df_func.columns, start=1):
        c = ws.cell(row=start_row, column=col, value=name)
        style_cell(c, bold=True, fill=header_gray)

    # Dados bloco 1
    for r_idx, row in enumerate(df_func.itertuples(index=False), start=start_row + 1):
        for col_idx, value in enumerate(row, start=1):
            c = ws.cell(row=r_idx, column=col_idx, value=value)
            style_cell(c)

    # ===== TÍTULO MOTOBOYS =====
    row_title = start_row + len(df_func) + 3
    ws.merge_cells(start_row=row_title, start_column=1, end_row=row_title, end_column=4)
    t = ws.cell(row=row_title, column=1, value="MOTOBOYS HORISTAS")
    style_cell(t, bold=True, fill=title_yellow)
    ws.row_dimensions[row_title].height = 20

    # ===== BLOCO 2: MOTOBOYS =====
    header_row2 = row_title + 1

    for col, name in enumerate(df_moto.columns, start=1):
        c = ws.cell(row=header_row2, column=col, value=name)
        style_cell(c, bold=True, fill=header_gray)

    for r_idx, row in enumerate(df_moto.itertuples(index=False), start=header_row2 + 1):
        for col_idx, value in enumerate(row, start=1):
            c = ws.cell(row=r_idx, column=col_idx, value=value)
            style_cell(c)

    # Largura de colunas (ajuste fino)
    ws.column_dimensions["A"].width = 35
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 18
    ws.column_dimensions["E"].width = 14

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


# ==========================
# EXECUÇÃO PRINCIPAL
# ==========================
if uploaded_file:
    texto = extract_full_text(uploaded_file)
    dados = parse_employee_blocks(texto)

    if not dados:
        st.error("Não encontrei funcionários no PDF (texto vazio ou padrão inesperado).")
        st.stop()

    df = pd.DataFrame(dados)

    # EXTRA OU FALTA = EXTRA - FALTA (como você pediu)
    df["EXTRA OU FALTA"] = (
        df["EXTRA 70%"].apply(hhmm_to_minutes) - df["FALTA"].apply(hhmm_to_minutes)
    ).apply(minutes_to_hhmm)

    # Identificar motoboy pelo cargo
    is_motoboy = df["CARGO"].str.upper().str.contains("MOTOBOY", na=False)

    # ===== BLOCO 1 (somente NÃO-motoboy)
    df_func = df[~is_motoboy][["NOME", "FALTA", "EXTRA 70%", "EXTRA OU FALTA", "TOTAL NOTURNO"]].copy()
    df_func.columns = ["NOME", "FALTA", "EXTRA", "EXTRA OU FALTA", "NOTURNO"]

    # ===== BLOCO 2 (somente motoboy)
    df_moto_raw = df[is_motoboy].copy()
    df_moto = df_moto_raw[["NOME", "TOTAL NOTURNO", "TOTAL NORMAIS", "EXTRA 70%"]].copy()
    df_moto.columns = ["NOME", "NOTURNO", "HORAS", "EXTRA"]

    st.success("✅ Relatório gerado com sucesso!")

    st.subheader("FUNCIONÁRIOS")
    st.dataframe(df_func, use_container_width=True)

    st.subheader("MOTOBOYS HORISTAS")
    st.dataframe(df_moto, use_container_width=True)

    excel_buffer = build_excel(df_func, df_moto)
    st.download_button(
        "⬇️ Baixar Excel no modelo",
        data=excel_buffer,
        file_name="Relatorio_Modelo.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
