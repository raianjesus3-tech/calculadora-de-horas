import streamlit as st
st.write("🚀 App iniciou")

import re

# ==========================
# IDENTIFICAR LOJA
# ==========================
def identificar_loja(texto):
    texto = texto.upper()
    if "TPBR" in texto:
        return "TPBR"
    elif "JPBB" in texto:
        return "JPBB"
    return None


# ==========================
# IDENTIFICAR MÊS
# ==========================
def identificar_mes(texto):
    match = re.search(r"DE\s+\d{2}/(\d{2})/\d{4}", texto)
    if not match:
        return None

    mes_num = int(match.group(1))

    meses = {
        1: "JANEIRO",
        2: "FEVEREIRO",
        3: "MARCO",
        4: "ABRIL",
        5: "MAIO",
        6: "JUNHO",
        7: "JULHO",
        8: "AGOSTO",
        9: "SETEMBRO",
        10: "OUTUBRO",
        11: "NOVEMBRO",
        12: "DEZEMBRO"
    }

    return meses.get(mes_num)


# ==========================
# ENVIAR PARA GOOGLE SHEETS
# ==========================
def enviar_para_sheets(df_func, df_moto, texto_pdf):

    loja = identificar_loja(texto_pdf)
    mes = identificar_mes(texto_pdf)

    if not loja or not mes:
        st.error("Não foi possível identificar loja ou mês no PDF.")
        return

    nome_aba = f"{mes}_{loja}"

    # Verifica se aba existe
    abas_existentes = [ws.title for ws in spreadsheet.worksheets()]

    if nome_aba not in abas_existentes:
        worksheet = spreadsheet.add_worksheet(title=nome_aba, rows="100", cols="20")
    else:
        worksheet = spreadsheet.worksheet(nome_aba)

    # Limpa a aba antes de escrever
    worksheet.clear()

    # ==========================
    # BLOCO FUNCIONÁRIOS
    # ==========================
    worksheet.update("A1", [["NOME", "FALTA", "EXTRA", "EXTRA OU FALTA", "NOTURNO"]])

    linha = 2
    for _, row in df_func.iterrows():
        worksheet.update(
            f"A{linha}:E{linha}",
            [[row["NOME"], row["FALTA"], row["EXTRA"], row["EXTRA OU FALTA"], row["NOTURNO"]]]
        )
        linha += 1

    # ==========================
    # BLOCO MOTOBOYS
    # ==========================
    linha += 1
    worksheet.update(f"A{linha}", [["MOTOBOYS HORISTAS"]])
    linha += 1

    worksheet.update(
        f"A{linha}:D{linha}",
        [["NOME", "HORAS", "NOTURNO", "EXTRA"]]
    )

    linha += 1
    for _, row in df_moto.iterrows():
        worksheet.update(
            f"A{linha}:D{linha}",
            [[row["NOME"], row["HORAS"], row["NOTURNO"], row["EXTRA"]]]
        )
        linha += 1

    st.success(f"Planilha atualizada com sucesso na aba {nome_aba} 🚀")
