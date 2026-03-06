from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017/")

db = client["Lisensiado"]

entrenadores = db["entrenadores"]
equipos = db["equipos"]
jugadores = db["jugadores"]


