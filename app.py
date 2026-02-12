for linha in linhas:

    if ("TPBR SERVICOS" in linha or "JPBB SERVICOS" in linha) and "TOTAL:" not in linha:

        # Extrair nome corretamente
        nome_match = re.search(r"SERVICOS DE ALIMENTACAO LTDA (.*?) \d{11}", linha)

        if not nome_match:
            continue

        nome = nome_match.group(1).strip()

        # Capturar todos horários
        valores = re.findall(r"\d{1,3}:\d{2}", linha)

        if len(valores) < 2:
            continue

        # Identificar campos dinamicamente
        noturno = valores[1] if len(valores) > 1 else "00:00"
        falta = valores[2] if len(valores) > 2 else "00:00"
        extra70 = valores[3] if len(valores) > 3 else "00:00"
        extra100 = valores[4] if len(valores) > 4 else "00:00"

        total_extra_min = hhmm_to_minutes(extra70) + hhmm_to_minutes(extra100)
        total_falta_min = hhmm_to_minutes(falta)

        saldo = minutes_to_hhmm(total_extra_min - total_falta_min)

        if "MOTOBOY" in linha.upper():

            dados_motoboys.append({
                "NOME": nome,
                "NOTURNO": noturno,
                "HORAS": valores[0] if len(valores) > 0 else "00:00",
                "EXTRA": saldo
            })

        else:

            dados_normais.append({
                "NOME": nome,
                "FALTA": falta,
                "EXTRA": minutes_to_hhmm(total_extra_min),
                "EXTRA OU FALTA": saldo,
                "NOTURNO": noturno
            })
