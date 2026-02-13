def parse_employee_blocks(texto: str) -> list[dict]:
    blocos = re.split(r"\bCart[aã]o\s+de\s+Ponto\b", texto, flags=re.IGNORECASE)
    out = []

    for bloco in blocos:
        if ("NOME DO FUNCION" not in bloco.upper()) or ("TOTAIS" not in bloco.upper()):
            continue

        nome_match = re.search(
            r"NOME DO FUNCION[AÁ]RIO:\s*(.+?)\s+PIS",
            bloco,
            flags=re.IGNORECASE | re.DOTALL
        )
        if not nome_match:
            continue

        nome = nome_match.group(1).replace("\n", " ").strip()

        cargo_match = re.search(r"NOME DO CARGO:\s*(.+)", bloco, flags=re.IGNORECASE)
        cargo = cargo_match.group(1).split("\n")[0].strip().upper() if cargo_match else ""

        totais_match = re.search(r"TOTAIS\s+([0-9:\s]+)", bloco, flags=re.IGNORECASE)
        if not totais_match:
            continue

        horarios = re.findall(r"\d{1,3}:\d{2}(?::\d{2})?", totais_match.group(1))

        # Padroniza ignorando segundos
        horarios = [h[:5] for h in horarios]

        # Valores padrão
        noturnas_normais = "00:00"
        total_normais = "00:00"
        total_noturno = "00:00"
        falta = "00:00"
        extra70 = "00:00"

        is_motoboy = "MOTOBOY" in cargo.upper()

        # 🔥 REGRA CORRIGIDA
        if is_motoboy:
            # Normalmente motoboy vem:
            # TOTAL NORMAIS, TOTAL NOTURNO, FALTA, EXTRA
            if len(horarios) >= 4:
                total_normais = horarios[0]
                total_noturno = horarios[1]
                falta = horarios[2]
                extra70 = horarios[3]
            elif len(horarios) == 3:
                total_normais = horarios[0]
                total_noturno = horarios[1]
                extra70 = horarios[2]
            elif len(horarios) == 2:
                total_normais = horarios[0]
                extra70 = horarios[1]
            elif len(horarios) == 1:
                total_normais = horarios[0]

        else:
            # Funcionário normal
            if len(horarios) >= 5:
                noturnas_normais = horarios[0]
                total_normais = horarios[1]
                total_noturno = horarios[2]
                falta = horarios[3]
                extra70 = horarios[4]
            elif len(horarios) == 4:
                total_normais = horarios[0]
                total_noturno = horarios[1]
                falta = horarios[2]
                extra70 = horarios[3]
            elif len(horarios) == 3:
                total_normais = horarios[0]
                total_noturno = horarios[1]
                extra70 = horarios[2]
            elif len(horarios) == 2:
                total_normais = horarios[0]
                extra70 = horarios[1]
            elif len(horarios) == 1:
                total_normais = horarios[0]

        out.append({
            "NOME": nome,
            "CARGO": cargo,
            "NOTURNAS NORMAIS": noturnas_normais,
            "TOTAL NORMAIS": total_normais,
            "TOTAL NOTURNO": total_noturno,
            "FALTA": falta,
            "ATRASO": "00:00",
            "EXTRA 70%": extra70,
        })

    return out
