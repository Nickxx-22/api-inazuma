from flask import Flask, jsonify, send_from_directory, request
from pymongo import MongoClient
from bson.objectid import ObjectId
import os
from flask_cors import CORS
from datetime import datetime, timedelta
import jwt
import re
from werkzeug.security import check_password_hash

# ----------------- CONFIGURACIÓN DINÁMICA -----------------
app = Flask(__name__)

# Permitimos peticiones desde tu web de GitHub y desde tu entorno local de desarrollo
CORS(app, resources={r"/*": {
    "origins": ["https://Nickxx-22.github.io", "http://localhost:5173"]
}})

# Variables de entorno (Si no existen, usa los valores por defecto locales)
# En Render, configurarás estas variables en el panel de control
SECRET_KEY = os.environ.get("SECRET_KEY", "rockruff")
BASE_API_URL = os.environ.get("BASE_API_URL", "http://127.0.0.1:5000")
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")

# Rutas de archivos usando rutas absolutas para evitar errores en el servidor
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGENES_FOLDER = os.path.join(BASE_DIR, "img")

# ----------------- CONEXIÓN MONGO -----------------
# Usamos el MONGO_URI dinámico (localhost para ahora, Atlas para después)
client = MongoClient(MONGO_URI)
db = client["Lisensiado"]

tecnicas = db["tecnicas"]
equipos = db["equipos"]
jugadores = db["jugadores"]
usuarios = db["usuarios"]

# ── AUTO-SETUP: crea el usuario admin si no existe ──────────────────
def _ensure_admin():
    """Crea el usuario admin 'Nico' al arrancar si no existe ya."""
    if not usuarios.find_one({"username": "Nico"}):
        usuarios.insert_one({
            "username":           "Nico",
            "email":              "nico@admin.com",
            "password":           "20052722",
            "role":               "admin",
            "favoritos":          [],
            "favoritos_tecnicas": [],
            "equipo":             [],
            "equipos":            {},
            "createdAt":          datetime.utcnow(),
        })
        print("✅ Admin 'Nico' creado automáticamente")
    else:
        # Nos aseguramos de que siempre tenga role=admin
        usuarios.update_one({"username": "Nico"}, {"$set": {"role": "admin", "password": "20052722"}})

_ensure_admin()
# ─────────────────────────────────────────────────────────────────────

# ----------------- RUTA DE IMÁGENES -----------------
@app.route("/img/<path:filename>")
def serve_image(filename):
    """
    Esta ruta es dinámica gracias a <path:filename>. 
    Si pides /img/jugadoresID/Byron_Love.png, buscará en img/jugadoresID/Byron_Love.png
    """
    file_path = os.path.join(IMAGENES_FOLDER, filename)
    
    print(f"--- Solicitud de Imagen ---")
    print(f"Buscando en disco: {file_path}")
    
    if not os.path.exists(file_path):
        print("❌ Archivo no encontrado")
        return jsonify({"error": f"Imagen no encontrada: {filename}"}), 404

    print("✅ Archivo encontrado")
    # Es importante pasar la subcarpeta si el filename la incluye
    directory = os.path.dirname(file_path)
    name = os.path.basename(file_path)
    return send_from_directory(directory, name)

# ---------------- RUTA TECNICAS -----------------
@app.route('/tecnicas/<path:filename>')
def serve_video_tecnica(filename):
    # APUNTAMOS A LA RUTA REAL: api_inazuma/img/tecnicas
    base_dir = os.path.dirname(os.path.abspath(__file__))
    tecnicas_path = os.path.join(base_dir, 'img', 'tecnicas') # <--- Añadimos 'img' aquí
    
    file_path = os.path.join(tecnicas_path, filename)
    
    print(f"--- DEBUG DE RUTA ---")
    print(f"Buscando en: {file_path}")
    
    if not os.path.exists(file_path):
        return jsonify({"error": "No encontrado", "ruta_revisada": file_path}), 404

    return send_from_directory(tecnicas_path, filename)

# ----------------- REGISTRO -----------------
@app.route('/registrar', methods=['POST'])
def registrar_usuario():
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    confirm_password = data.get('confirm_password')

    if not username or not email or not password or not confirm_password:
        return jsonify({"message": "⚠️ Todos los campos son obligatorios"}), 400

    email_pattern = r'^[\w\.-]+@[\w\.-]+\.(com|es)$'
    if not re.match(email_pattern, email):
        return jsonify({"message": "⚠️ El correo debe ser válido y terminar en .com o .es"}), 400

    if password != confirm_password:
        return jsonify({"message": "⚠️ Las contraseñas no coinciden"}), 400

    if usuarios.find_one({"email": email}):
        return jsonify({"message": "⚠️ El correo ya está en uso"}), 400

    nuevo_usuario = {
        "username": username,
        "email": email,
        "password": password,  # ⚠️ En producción: usar hash
        "favoritos": [],
        "equipo": [],
        "createdAt": datetime.utcnow()
    }

    usuarios.insert_one(nuevo_usuario)
    return jsonify({"message": "✅ Registro exitoso"}), 201

# ----------------- LOGIN -----------------
@app.route('/iniciar_sesion', methods=['POST'])
def iniciar_sesion():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"message": "⚠️ Se requiere nombre de usuario y contraseña"}), 400

    usuario = usuarios.find_one({"username": username})
    if usuario and usuario['password'] == password:
        payload = {
            "sub": str(usuario["_id"]),
            "exp": datetime.utcnow() + timedelta(hours=1)
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
        if isinstance(token, bytes):
            token = token.decode('utf-8')

        usuario_info = {
            "id": str(usuario["_id"]),
            "username": usuario["username"],
            "email": usuario["email"],
            "role": usuario.get("role", "user"),
            "favoritos": usuario.get("favoritos", []),
            "equipo": usuario.get("equipo", [])
        }

        return jsonify({
            "message": f"✅ Bienvenido, {usuario['username']}!", 
            "token": token, 
            "usuario": usuario_info
        }), 200
    else:
        return jsonify({"message": "⚠️ Usuario o contraseña incorrectos"}), 401

# ----------------- JUGADORES -----------------
@app.route("/jugadores", methods=["GET"])
def obtener_jugadores():
    resultado = []

    for j in jugadores.find():
        genero = "Masculino" if j.get("sex") == "M" else "Femenino"

        # Obtener la URL de la imagen y asegurarse de que sea completa
        imagen_url = ""
        image_field = j.get("image")
        if image_field and isinstance(image_field, dict):
            imagen_url = image_field.get("url", "")
            if imagen_url.startswith("/"):
                imagen_url = f"{BASE_API_URL}{imagen_url}"

        # Procesar imagen del pais
        country_raw = j.get("country", "")
        country_img = ""
        if isinstance(country_raw, dict):
            country_name = country_raw.get("name", "")
            flag_path = country_raw.get("flag", "") or country_raw.get("image", "")
            if flag_path and flag_path.startswith("/"):
                country_img = f"{BASE_API_URL}{flag_path}"
            elif flag_path:
                country_img = flag_path
        else:
            country_name = str(country_raw) if country_raw else ""
            # Intentar leer country_image si country es string
            ci = j.get("country_image")
            if ci and isinstance(ci, dict):
                ci_path = ci.get("url", "")
                if ci_path.startswith("/"):
                    country_img = f"{BASE_API_URL}{ci_path}"

        # Imagen de posición
        position_img = ""
        pos_img_field = j.get("position_image")
        if pos_img_field and isinstance(pos_img_field, dict):
            pos_path = pos_img_field.get("url", "")
            if pos_path.startswith("/"):
                position_img = f"{BASE_API_URL}{pos_path}"

        # Imagen de elemento
        element_img = ""
        el_img_field = j.get("element_image")
        if el_img_field and isinstance(el_img_field, dict):
            el_path = el_img_field.get("url", "")
            if el_path.startswith("/"):
                element_img = f"{BASE_API_URL}{el_path}"

        # ── Seasons: leídas DIRECTAMENTE de teams[].seasons del jugador ───
        # Estructura real en BD: teams: [{team_id, seasons: "Season_T3", ...}]
        # "seasons" en cada team_entry es un string como "Season_T3"
        # Mapeamos a IE1/IE2/IE3 según el sufijo (T1→IE1, T2→IE2, T3→IE3, etc.)
        SEASON_MAP = {
            "T1": "IE1", "Season_T1": "IE1",
            "T2": "IE2", "Season_T2": "IE2",
            "T3": "IE3", "Season_T3": "IE3",
            "IE1": "IE1", "IE2": "IE2", "IE3": "IE3",
        }
        seasons_set = set()
        for team_entry in j.get("teams", []):
            raw = team_entry.get("seasons", "")
            if isinstance(raw, list):
                for s in raw:
                    mapped = SEASON_MAP.get(str(s), str(s))
                    seasons_set.add(mapped)
            elif raw:
                mapped = SEASON_MAP.get(str(raw), str(raw))
                seasons_set.add(mapped)
        # Fallback campo directo
        if not seasons_set and j.get("season"):
            seasons_set.add(SEASON_MAP.get(j.get("season"), j.get("season")))
        seasons_list = sorted(seasons_set)

        resultado.append({
            "id": str(j["_id"]),
            "name": j.get("name", ""),
            "japaneseName": j.get("japaneseName", ""),
            "element": j.get("element", ""),
            "elementImg": element_img,
            "position": j.get("position", ""),
            "positionImg": position_img,
            "gender": genero,
            "nature": j.get("nature", ""),
            "role": j.get("role", ""),
            "seasons": seasons_list,
            "season": seasons_list[0] if seasons_list else "",
            "power": j.get("stats", {}).get("kicking", 0),
            "image": imagen_url,
            "country": country_name,
            "countryImg": country_img,
        })

    return jsonify(resultado)

# ----------------- JUGADORES INFO -----------------
@app.route("/jugadores/<id>", methods=["GET"])
def detalle_jugador(id):
    try:
        jugador = jugadores.find_one({"_id": id})
        if not jugador:
            return jsonify({"error": f"Jugador {id} no encontrado"}), 404

        base_url = globals().get('BASE_API_URL', 'http://127.0.0.1:5000')

        # --- LÓGICA DE IMAGEN ---
        if "imageDetail" in jugador:
            path_imagen = jugador["imageDetail"].get("url", "")
        else:
            path_imagen = f"/img/jugadoresID/{id.lower()}.png"

        imagen_url = f"{base_url}{path_imagen}" if path_imagen.startswith("/") else f"{base_url}/{path_imagen}"
            
        # ── Imagen de elemento ──
        element_img = ""
        el_img_field = jugador.get("element_image")
        if el_img_field and isinstance(el_img_field, dict):
            el_path = el_img_field.get("url", "")
            if el_path.startswith("/"):
                element_img = f"{base_url}{el_path}"

        # ── Imagen de posición ──
        position_img = ""
        pos_img_field = jugador.get("position_image")
        if pos_img_field and isinstance(pos_img_field, dict):
            pos_path = pos_img_field.get("url", "")
            if pos_path.startswith("/"):
                position_img = f"{base_url}{pos_path}"

        # ── País e imagen de país ──
        country_raw = jugador.get("country", "")
        if isinstance(country_raw, dict):
            country_name = country_raw.get("name", "")
            flag_path = country_raw.get("flag", "") or country_raw.get("image", "")
            country_img = f"{base_url}{flag_path}" if flag_path.startswith("/") else flag_path
        else:
            country_name = str(country_raw) if country_raw else ""
            # country es string — buscar country_image separado
            ci = jugador.get("country_image")
            if ci and isinstance(ci, dict):
                ci_path = ci.get("url", "")
                country_img = f"{base_url}{ci_path}" if ci_path.startswith("/") else ci_path
            else:
                country_img = ""

        character = {
            "id": str(jugador["_id"]),
            "name": jugador.get("name"),
            "japaneseName": jugador.get("japaneseName", ""),
            "element": jugador.get("element"),
            "elementImg": element_img,
            "position": jugador.get("position"),
            "positionImg": position_img,
            "gender": "Masculino" if jugador.get("sex") == "M" else "Femenino",
            "nature": jugador.get("nature"),
            "role": jugador.get("role"),
            "season": jugador.get("season", "IE1"),
            "description": jugador.get("description", ""),
            "image": imagen_url,
            "stats": jugador.get("stats", {}),
            "matchStats": jugador.get("matchStats", { "stamina": 0, "tension": 0 }),
            "power": jugador.get("stats", {}).get("kicking", 0),
            "teams": jugador.get("teams", []),
            "country": country_name,
            "countryImg": country_img,
        }

        # --- TÉCNICAS (CON VIDEO Y COSTES) ---
        tech_data = []
        for t in jugador.get("techniques", []):
            t_id = t.get("technique_id")
            relacion = t.get("relation", "normal").lower()
            info_tech = tecnicas.find_one({"_id": t_id})
            
            if info_tech:
                # Modificadores recordados
                mod = 1.0
                if relacion == "heredero": mod = 0.5 #[cite: 2026-02-27]
                elif relacion == "copia": mod = 0.3 #[cite: 2026-02-11]
                
                video_raw = info_tech.get("videoUrl", {}).get("url", "")
                video_url = f"{base_url}{video_raw}" if video_raw else None

                tech_data.append({
                    "id": t_id,
                    "name": info_tech.get("name"),
                    "type": info_tech.get("type"),
                    "element": info_tech.get("element"),
                    "relation": relacion,
                    "finalPower": int(info_tech.get("basePower", 0) * mod),
                    "videoUrl": video_url,
                    "cost": info_tech.get("cost", {"stamina": 0, "tension": 0})
                })
            else:
                # ESTO TE DIRÁ QUÉ TÉCNICA FALTA EN TU CONSOLA
                print(f"ALERTA: La técnica '{t_id}' no existe en la colección 'tecnicas'")

        return jsonify({
            "character": character,
            "techniques": tech_data
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

#------------------ TECNICAS -------------------
@app.route('/tecnicas', methods=['GET'])
def get_all_techniques():
    try:
        # Buscamos todas las técnicas
        tecnicas_db = list(db.tecnicas.find())
        base_url = "http://127.0.0.1:5000"

        for tech in tecnicas_db:
            tech['_id'] = str(tech['_id'])
            
            # Aseguramos que matchStats exista (instrucción de memoria)
            if 'matchStats' not in tech:
                tech['matchStats'] = {}

            # Construimos la URL del video de forma segura
            # Si 'videoUrl' es un diccionario con la subclave 'url'
            if isinstance(tech.get('videoUrl'), dict) and tech['videoUrl'].get('url'):
                video_path = tech['videoUrl']['url']
                tech['videoUrl'] = f"{base_url}{video_path}"
            
            # Normalizamos el tipo para el frontend (Shot -> Tiro, etc.) si es necesario
            # O simplemente lo pasamos a minúsculas para que el filtro no falle
            if 'type' in tech:
                tech['type'] = tech['type'].lower()

        return jsonify(tecnicas_db), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


#---------------- EQUIPOS --------------------------
@app.route('/equipos', methods=['GET'])
def get_all_teams():
    try:
        teams_db = list(db.equipos.find())
        base_url = "http://127.0.0.1:5000" 
        
        for team in teams_db:
            team['_id'] = str(team['_id'])
            
            # 1. Imagen del equipo
            if 'image' in team and team['image'].get('url'):
                if not team['image']['url'].startswith('http'):
                    team['image']['url'] = f"{base_url}{team['image']['url']}"

            # 2. BUSCAR JUGADORES DE ESTE EQUIPO
            player_ids = team.get('player_ids', [])
            players_db = list(db.jugadores.find({"_id": {"$in": player_ids}}))
            
            processed_players = []
            for p in players_db:
                # BUSCAR EL DORSAL: Como 'teams' es un array, buscamos el que coincida con este equipo
                dorsal = None
                if 'teams' in p:
                    for t_info in p['teams']:
                        if t_info.get('team_id') == team['_id']: # Comparamos con Zeus_T1
                            dorsal = t_info.get('number')
                            break

                player_data = {
                    "id": str(p.get("_id")), # Guardamos el ID real para el Link
                    "name": p.get("name"),
                    "number": dorsal, # Usamos el dorsal de la relación del equipo
                    "element": p.get("element"),
                    "matchStats": p.get("matchStats", {"stamina": 0, "tension": 0})
                }
                
                # Procesar imagen del jugador
                if 'image' in p and p['image'].get('url'):
                    url = p['image']['url']
                    player_data["image_url"] = f"{base_url}{url}" if not url.startswith('http') else url
                else:
                    player_data["image_url"] = None

                processed_players.append(player_data)

            # ORDENAR POR DORSAL (de menor a mayor)
            # Usamos 999 como fallback si no tiene número para que se vayan al final
            processed_players.sort(key=lambda x: x['number'] if x['number'] is not None else 999)

            team['players'] = processed_players
            
        return jsonify(teams_db), 200
        
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500
#---------------------LLAMADA JUGADORES EQUIPOS--------------
@app.route('/equipos/<team_id>', methods=['GET'])
def get_team_by_id(team_id):
    try:
        team = db.equipos.find_one({"_id": team_id})
        if not team:
            return jsonify({"error": "Equipo no encontrado"}), 404
        
        # IMPORTANTE: En producción, base_url debería ser la URL de tu backend real
        # Si usas rutas relativas en el frontend, a veces es mejor enviar solo el path
        base_url = "http://127.0.0.1:5000" 
        
        team['_id'] = str(team['_id'])
        
        # 1. Imagen del equipo
        if 'image' in team and team['image'].get('url'):
            if not team['image']['url'].startswith('http'):
                team['image']['url'] = f"{base_url}{team['image']['url']}"

        # 2. BUSCAR JUGADORES Y FILTRAR SOLO LO QUE PIDES
        player_ids = team.get('player_ids', [])
        players_db = list(db.jugadores.find({"_id": {"$in": player_ids}}))
        
        processed_players = []
        for p in players_db:
            # Solo extraemos lo que necesitas: nombre, dorsal, elemento e imagen
            player_data = {
                "name": p.get("name"),
                "number": p.get("number"),
                "element": p.get("element"),
                "matchStats": p.get("matchStats", {}) # Mantengo esto por tus instrucciones previas
            }
            
            # Procesar imagen del jugador
            if 'image' in p and p['image'].get('url'):
                url = p['image']['url']
                player_data["image_url"] = f"{base_url}{url}" if not url.startswith('http') else url
            else:
                player_data["image_url"] = None

            processed_players.append(player_data)

        team['players'] = processed_players 
        return jsonify(team), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500     

#----------------- GURDAR EQUIPOS ------------------
@app.route('/guardar_equipo', methods=['POST'])
def guardar_equipo():
    data = request.get_json()
    user_id = data.get('user_id')
    nuevo_equipo = data.get('equipo')  # Array de 11 IDs
    nombre = data.get('nombre_equipo', 'Mi Equipo')

    if not user_id or not nuevo_equipo:
        return jsonify({"message": "⚠️ Faltan datos"}), 400

    try:
        # Usamos notación de puntos para guardar múltiples equipos en un objeto 'equipos'
        resultado = usuarios.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {
                f"equipos.{nombre}": nuevo_equipo,
                "ultimo_equipo_editado": nombre
            }}
        )
        
        return jsonify({"message": "✅ Equipo guardado correctamente"}), 200
            
    except Exception as e:
        return jsonify({"message": f"❌ Error en DB: {str(e)}"}), 500

@app.route('/eliminar_equipo', methods=['DELETE'])
def eliminar_equipo():
    # En DELETE con fetch, el body llega igual por get_json()
    data = request.get_json()
    user_id = data.get('user_id')
    nombre = data.get('nombre_equipo')

    if not user_id or not nombre:
        return jsonify({"message": "Faltan datos requeridos"}), 400

    try:
        # 1. Eliminamos el equipo específico usando $unset
        # Esto elimina la 'key' dentro del objeto 'equipos'
        resultado = usuarios.update_one(
            {"_id": ObjectId(user_id)},
            {"$unset": { f"equipos.{nombre}": "" }}
        )

        if resultado.modified_count == 0:
            return jsonify({"message": "No se encontró el equipo o el usuario"}), 404
        
        # 2. Buscamos al usuario de nuevo para devolver la lista actualizada
        user_actualizado = usuarios.find_one({"_id": ObjectId(user_id)})
        equipos_restantes = user_actualizado.get('equipos', {})
        
        return jsonify({
            "message": "Eliminado correctamente",
            "equipos": equipos_restantes
        }), 200

    except Exception as e:
        print(f"Error al eliminar: {str(e)}")
        return jsonify({"message": "Error interno del servidor"}), 500


#------------------- HELPER: verificar token JWT -----------------
def verify_token(req):
    """Extrae y valida el JWT del header Authorization. Devuelve el user_id o None."""
    auth_header = req.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None
    token = auth_header.split(' ', 1)[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload.get('sub')  # 'sub' es el string del ObjectId
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None

#------------------- OBTENER USUARIO (equipos + favoritos) -----------------
@app.route('/obtener_usuario/<user_id>', methods=['GET'])
def obtener_usuario(user_id):
    """Devuelve los datos del usuario incluyendo todos sus equipos guardados."""
    try:
        usuario = usuarios.find_one(
            {"_id": ObjectId(user_id)},
            {"password": 0}  # nunca devolvemos la contraseña
        )
        if not usuario:
            return jsonify({"message": "Usuario no encontrado"}), 404

        usuario_info = {
            "id":                   str(usuario["_id"]),
            "username":             usuario.get("username", ""),
            "email":                usuario.get("email", ""),
            "role":                 usuario.get("role", "user"),
            "favoritos":            usuario.get("favoritos", []),
            "favoritos_tecnicas":   usuario.get("favoritos_tecnicas", []),
            "equipo":               usuario.get("equipo", []),
            "equipos":              usuario.get("equipos", {}),
        }
        return jsonify({"usuario": usuario_info}), 200

    except Exception as e:
        return jsonify({"message": f"Error: {str(e)}"}), 500

#------------------- OBTENER EQUIPO (legacy) -----------------
@app.route('/obtener_equipo/<user_id>', methods=['GET'])
def obtener_equipo(user_id):
    try:
        usuario = usuarios.find_one({"_id": ObjectId(user_id)}, {"equipo": 1, "nombre_equipo": 1})
        if usuario:
            return jsonify({
                "equipo": usuario.get("equipo", []),
                "nombre_equipo": usuario.get("nombre_equipo", "Mi Equipo")
            }), 200
        return jsonify({"message": "Usuario no encontrado"}), 404
    except Exception as e:
        return jsonify({"message": str(e)}), 500     
    

#----------------- FAVORITOS -----------------
@app.route('/toggle_favorito', methods=['POST'])
def toggle_favorito():
    data = request.get_json()
    user_id = data.get('user_id')
    personaje_id = data.get('personaje_id')

    if not user_id or not personaje_id:
        return jsonify({"message": "Faltan datos"}), 400

    try:
        # 1. Buscamos al usuario para ver si ya tiene ese favorito
        user = usuarios.find_one({"_id": ObjectId(user_id)})
        favoritos = user.get('favoritos', [])

        if personaje_id in favoritos:
            # Si ya existe, lo quitamos
            usuarios.update_one(
                {"_id": ObjectId(user_id)},
                {"$pull": {"favoritos": personaje_id}}
            )
            accion = "quitado"
        else:
            # Si no existe, lo añadimos
            usuarios.update_one(
                {"_id": ObjectId(user_id)},
                {"$addToSet": {"favoritos": personaje_id}}
            )
            accion = "añadido"

        return jsonify({"message": f"Personaje {accion}", "isFavorite": accion == "añadido"}), 200

    except Exception as e:
        return jsonify({"message": str(e)}), 500


#------------------- TOGGLE FAVORITO TECNICA -----------------
@app.route('/toggle_favorito_tecnica', methods=['POST'])
def toggle_favorito_tecnica():
    data = request.get_json()
    user_id    = data.get('user_id')
    tecnica_id = data.get('tecnica_id')

    if not user_id or not tecnica_id:
        return jsonify({"message": "Faltan datos"}), 400

    try:
        user = usuarios.find_one({"_id": ObjectId(user_id)})
        if not user:
            return jsonify({"message": "Usuario no encontrado"}), 404

        favs = user.get('favoritos_tecnicas', [])

        if tecnica_id in favs:
            usuarios.update_one(
                {"_id": ObjectId(user_id)},
                {"$pull": {"favoritos_tecnicas": tecnica_id}}
            )
            accion = "quitado"
        else:
            usuarios.update_one(
                {"_id": ObjectId(user_id)},
                {"$addToSet": {"favoritos_tecnicas": tecnica_id}}
            )
            accion = "anadido"

        return jsonify({"message": f"Tecnica {accion}", "isFavorite": accion == "anadido"}), 200

    except Exception as e:
        return jsonify({"message": str(e)}), 500

# ─────────────────────────── ADMIN ───────────────────────────

def require_admin(f):
    """Decorador: sólo usuarios con role='admin' pueden usar el endpoint."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({"message": "Token requerido"}), 401
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            user_id = payload.get("sub")
            user = usuarios.find_one({"_id": ObjectId(user_id)})
            if not user or user.get("role") != "admin":
                return jsonify({"message": "Acceso denegado"}), 403
        except Exception:
            return jsonify({"message": "Token inválido"}), 401
        return f(*args, **kwargs)
    return decorated


@app.route('/admin/usuarios', methods=['GET'])
@require_admin
def admin_listar_usuarios():
    """Lista todos los usuarios (sin contraseña)."""
    try:
        todos = list(usuarios.find({}, {"password": 0}))
        result = []
        for u in todos:
            result.append({
                "id":        str(u["_id"]),
                "username":  u.get("username", ""),
                "email":     u.get("email", ""),
                "role":      u.get("role", "user"),
                "createdAt": str(u.get("createdAt", "")),
                "favoritos": len(u.get("favoritos", [])),
                "favoritos_tecnicas": len(u.get("favoritos_tecnicas", [])),
                "equipos":   len(u.get("equipos", {})),
            })
        return jsonify({"usuarios": result}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500


@app.route('/admin/usuarios/<user_id>', methods=['DELETE'])
@require_admin
def admin_eliminar_usuario(user_id):
    """Elimina un usuario por id."""
    try:
        resultado = usuarios.delete_one({"_id": ObjectId(user_id)})
        if resultado.deleted_count == 0:
            return jsonify({"message": "Usuario no encontrado"}), 404
        return jsonify({"message": "Usuario eliminado"}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500


@app.route('/admin/usuarios/<user_id>/role', methods=['PUT'])
@require_admin
def admin_cambiar_role(user_id):
    """Cambia el role de un usuario (user / admin / banned)."""
    data = request.get_json()
    new_role = data.get("role")
    if new_role not in ("user", "admin", "banned"):
        return jsonify({"message": "Role inválido"}), 400
    try:
        usuarios.update_one({"_id": ObjectId(user_id)}, {"$set": {"role": new_role}})
        return jsonify({"message": f"Role actualizado a {new_role}"}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500


@app.route('/admin/usuarios/<user_id>', methods=['GET'])
@require_admin
def admin_detalle_usuario(user_id):
    """Detalle completo de un usuario para el panel admin."""
    try:
        u = usuarios.find_one({"_id": ObjectId(user_id)}, {"password": 0})
        if not u:
            return jsonify({"message": "No encontrado"}), 404
        return jsonify({
            "id":        str(u["_id"]),
            "username":  u.get("username", ""),
            "email":     u.get("email", ""),
            "role":      u.get("role", "user"),
            "createdAt": str(u.get("createdAt", "")),
            "favoritos": u.get("favoritos", []),
            "favoritos_tecnicas": u.get("favoritos_tecnicas", []),
            "equipos":   u.get("equipos", {}),
        }), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500


# ----------------- RUN -----------------
if __name__ == "__main__":
    app.run(debug=True)