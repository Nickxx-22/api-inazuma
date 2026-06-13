import random

# ── Helpers ──────────────────────────────────────────────────────

def get_tecnica_por_tipo(jugador_id, tipo, db):
    """Devuelve una técnica aleatoria del jugador según el tipo."""
    jugador = db.jugadores.find_one({"_id": jugador_id})
    if not jugador:
        return None

    tecnicas_jugador = jugador.get("techniques", [])
    tecnicas_validas = []

    for t in tecnicas_jugador:
        tec_id = t.get("technique_id")
        tec = db.tecnicas.find_one({"_id": tec_id})
        if not tec:
            continue
        subtipo = tec.get("subtype", [])
        if tipo in subtipo:
            video_raw = tec.get("videoUrl", {})
            video_url = video_raw.get("url", "") if isinstance(video_raw, dict) else ""
            tecnicas_validas.append({
                "slug":      tec_id,
                "nombre":    tec.get("name", ""),
                "video_url": video_url,
                "poder":     tec.get("basePower", 0),
            })

    return random.choice(tecnicas_validas) if tecnicas_validas else None


def tiene_tecnica_tipo(jugador_id, tipo, db):
    """Comprueba si un jugador tiene al menos una técnica del tipo dado."""
    jugador = db.jugadores.find_one({"_id": jugador_id})
    if not jugador:
        return False
    for t in jugador.get("techniques", []):
        tec = db.tecnicas.find_one({"_id": t.get("technique_id")})
        if tec and tipo in tec.get("subtype", []):
            return True
    return False


def pick(lista):
    return random.choice(lista) if lista else None


def pick_con_tecnica(lista, tipo, db):
    candidatos = [j for j in lista if tiene_tecnica_tipo(j["id"], tipo, db)]
    return random.choice(candidatos) if candidatos else None


def construir_plantilla_mongo(slots, db):
    """Construye la plantilla a partir de los slots del equipo del usuario.
    slots puede ser una lista de strings (IDs directos) o dicts con 'characterId'.
    """
    plantilla = {"GK": [], "DF": [], "MD": [], "FW": []}
    for slot in slots:
        # ✅ FIX: el frontend guarda los slots como array de strings puros
        if isinstance(slot, str):
            char_id = slot
        elif isinstance(slot, dict):
            char_id = slot.get("characterId")
        else:
            continue  # None u otro tipo: slot vacío, ignorar

        if not char_id:
            continue
        p = db.jugadores.find_one({"_id": char_id})
        if not p:
            continue
        pos = p.get("position", "MD")
        if pos not in plantilla:
            pos = "MD"
        stats = p.get("stats", {})
        plantilla[pos].append({
            "id":      str(p["_id"]),
            "nombre":  p.get("name", ""),
            "posicion": pos,
            "poder":   stats.get("kicking", 50),
            "remate":  stats.get("kicking", 50),
            "defensa": stats.get("defense", 50),
            "agilidad": stats.get("agility", 50),
        })
    return plantilla


def generar_equipo_rival_mongo(equipo_db_id=None, db=None, nombre_override=None):
    """Genera un equipo rival desde MongoDB."""
    if equipo_db_id:
        equipo = db.equipos.find_one({"_id": equipo_db_id})
        if equipo:
            player_ids = equipo.get("player_ids", [])[:11]
            # ✅ FIX: normalizar a string por si los _id son ObjectId o str
            player_ids = [str(pid) for pid in player_ids]
            jugadores = list(db.jugadores.find({"_id": {"$in": player_ids}}))
            nombre = equipo.get("name", f"Equipo {random.randint(1, 99)}")
        else:
            jugadores = list(db.jugadores.aggregate([{"$sample": {"size": 11}}]))
            nombre = nombre_override or f"Equipo Misterioso {random.randint(1, 99)}"
    else:
        jugadores = list(db.jugadores.aggregate([{"$sample": {"size": 11}}]))
        nombre = nombre_override or f"Equipo Misterioso {random.randint(1, 99)}"

    plantilla = {"GK": [], "DF": [], "MD": [], "FW": []}
    for p in jugadores:
        pos = p.get("position", "MD")
        if pos not in plantilla:
            pos = "MD"
        stats = p.get("stats", {})
        plantilla[pos].append({
            "id":      str(p["_id"]),
            "nombre":  p.get("name", ""),
            "posicion": pos,
            "poder":   stats.get("kicking", 50),
            "remate":  stats.get("kicking", 50),
            "defensa": stats.get("defense", 50),
            "agilidad": stats.get("agility", 50),
        })

    return nombre, plantilla


# ── Motor principal ───────────────────────────────────────────────

def simular_partido(plantilla_local, nombre_local, plantilla_rival, nombre_rival, db):
    eventos         = []
    goles_local     = 0
    goles_visitante = 0
    stats = {
        "goleadores": {},
        "porteros":   {},
        "regates":    {},
        "robos":      {},
    }

    minutos = sorted(random.sample(range(1, 91), random.randint(22, 32)))

    for minuto in minutos:
        es_local        = random.random() < 0.5
        ataca           = plantilla_local  if es_local else plantilla_rival
        defiende        = plantilla_rival  if es_local else plantilla_local
        nombre_atacante = nombre_local     if es_local else nombre_rival
        nombre_defensor = nombre_rival     if es_local else nombre_local

        tipo_evento = random.choices(
            ["regate", "robo", "ocasion", "tiro"],
            weights=[25, 20, 20, 35]
        )[0]

        evento = {
            "minuto":      minuto,
            "tipo":        tipo_evento,
            "equipo":      nombre_atacante,
            "tecnica":     None,
            "descripcion": "",
            "es_gol":      False,
        }

        if tipo_evento == "regate":
            candidatos = ataca.get("DF", []) + ataca.get("MD", []) + ataca.get("FW", [])
            jugador = pick_con_tecnica(candidatos, "regate", db)
            if jugador:
                tecnica = get_tecnica_por_tipo(jugador["id"], "regate", db)
                if tecnica:
                    evento["jugador"] = jugador["nombre"]
                    evento["tecnica"] = {"regate": tecnica}
                    evento["descripcion"] = (
                        f"min {minuto}' — {jugador['nombre']} ({nombre_atacante}) "
                        f"supera a su rival con {tecnica['nombre']}!"
                    )
                    factor_poder = 1 + (jugador.get("poder", 50) - 50) * 0.002
                    if random.random() < min(0.95, 0.6 * factor_poder):
                        s = stats["regates"].setdefault(jugador["id"], {"nombre": jugador["nombre"], "regates": 0})
                        s["regates"] += 1

        elif tipo_evento == "robo":
            candidatos = defiende.get("DF", []) + defiende.get("MD", [])
            jugador = pick_con_tecnica(candidatos, "quitar", db)
            if jugador:
                tecnica = get_tecnica_por_tipo(jugador["id"], "quitar", db)
                if tecnica:
                    evento["jugador"] = jugador["nombre"]
                    evento["equipo"]  = nombre_defensor
                    evento["tecnica"] = {"robo": tecnica}
                    evento["descripcion"] = (
                        f"min {minuto}' — {jugador['nombre']} ({nombre_defensor}) "
                        f"roba el balón con {tecnica['nombre']}!"
                    )
                    r = stats["robos"].setdefault(jugador["id"], {"nombre": jugador["nombre"], "robos": 0})
                    r["robos"] += 1

        elif tipo_evento == "ocasion":
            jugador = pick(ataca.get("FW", []) + ataca.get("MD", []))
            if jugador:
                evento["jugador"] = jugador["nombre"]
                evento["descripcion"] = (
                    f"min {minuto}' — ¡Ocasión! {jugador['nombre']} ({nombre_atacante}) "
                    f"se queda solo ante el portero!"
                )

        elif tipo_evento == "tiro":
            candidatos_tiro = ataca.get("FW", []) + ataca.get("MD", [])
            tirador = pick_con_tecnica(candidatos_tiro, "tiro", db) or pick(candidatos_tiro)
            candidatos_gk = defiende.get("GK", [])
            portero = pick_con_tecnica(candidatos_gk, "parada", db) or pick(candidatos_gk)

            if tirador and portero:
                tec_tiro   = get_tecnica_por_tipo(tirador["id"], "tiro",   db)
                tec_parada = get_tecnica_por_tipo(portero["id"], "parada", db)

                factor_tirador = 1 + (tirador.get("poder", 50) - 50) * 0.003
                factor_portero = 1 + (portero.get("poder",  50) - 50) * 0.003
                poder_tiro   = (tirador.get("remate", 50) + (tec_tiro["poder"]   if tec_tiro   else 0)) * factor_tirador
                poder_parada = (portero.get("defensa", 50) + (tec_parada["poder"] if tec_parada else 0)) * factor_portero
                prob_gol     = poder_tiro / (poder_tiro + poder_parada + 1)
                es_gol       = random.random() < prob_gol

                evento["jugador"] = tirador["nombre"]
                evento["tecnica"] = {"tiro": tec_tiro, "parada": tec_parada}

                if es_gol:
                    if es_local:
                        goles_local += 1
                    else:
                        goles_visitante += 1
                    evento["es_gol"] = True
                    g = stats["goleadores"].setdefault(tirador["id"], {"nombre": tirador["nombre"], "goles": 0})
                    g["goles"] += 1
                    evento["descripcion"] = f"min {minuto}' ⚽ ¡GOL! {tirador['nombre']} marca"
                    if tec_tiro:
                        evento["descripcion"] += f" con {tec_tiro['nombre']}"
                    evento["descripcion"] += f"! ({nombre_local} {goles_local} - {goles_visitante} {nombre_rival})"
                else:
                    ps = stats["porteros"].setdefault(portero["id"], {"nombre": portero["nombre"], "paradas": 0})
                    ps["paradas"] += 1
                    evento["descripcion"] = f"min {minuto}' — {tirador['nombre']} dispara"
                    if tec_tiro:
                        evento["descripcion"] += f" con {tec_tiro['nombre']}"
                    evento["descripcion"] += f" pero {portero['nombre']}"
                    if tec_parada:
                        evento["descripcion"] += f" lo para con {tec_parada['nombre']}"
                    else:
                        evento["descripcion"] += " lo detiene"
                    evento["descripcion"] += "!"

        if evento.get("descripcion"):
            eventos.append(evento)

    # Penaltis si hay empate
    if goles_local == goles_visitante:
        pen_local = random.randint(3, 5)
        pen_visitante = random.randint(3, 5)
        while pen_local == pen_visitante:
            pen_visitante = random.randint(3, 5)
        goles_local     += pen_local
        goles_visitante += pen_visitante
        ganador = nombre_local if pen_local > pen_visitante else nombre_rival
        eventos.append({
            "minuto":      90,
            "tipo":        "penaltis",
            "equipo":      ganador,
            "tecnica":     None,
            "descripcion": f"¡Penaltis! {nombre_local} {pen_local} - {pen_visitante} {nombre_rival}. ¡{ganador} gana!",
            "es_gol":      False,
        })

    return goles_local, goles_visitante, eventos, stats


def sortear_torneo(nombre_usuario, db):
    """Genera el cuadro del torneo con 16 equipos de MongoDB."""
    equipos_cursor = list(db.equipos.aggregate([
        {"$match": {"name": {"$ne": nombre_usuario}}},
        {"$sample": {"size": 15}}
    ]))

    if len(equipos_cursor) < 15:
        raise ValueError("No hay suficientes equipos en la base de datos")

    nombres_rivales = [
        {"nombre": eq.get("name", ""), "id": str(eq["_id"]), "es_real": True}
        for eq in equipos_cursor
    ]

    random.shuffle(nombres_rivales)

    pos_usuario = random.randint(0, 15)
    nombres_rivales.insert(pos_usuario, {
        "nombre":     nombre_usuario,
        "id":         "usuario",
        "es_usuario": True,
    })

    enfrentamientos = []
    for i in range(0, 16, 2):
        enfrentamientos.append({
            "local":     nombres_rivales[i],
            "visitante": nombres_rivales[i + 1],
            "jugado":    False,
            "resultado": None,
        })

    return {
        "ronda_1":  enfrentamientos,
        "equipos":  nombres_rivales,
    }