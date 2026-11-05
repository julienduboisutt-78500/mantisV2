import datetime
from database import get_db, init_db, ensure_database_ready, restore_database_from_json
from auth import hash_password

def seed_initial_data():
    """
    Initialisation sécurisée sans écrasement :
    Vérifie l'état de la base et charge le miroir réel (mantis_data.json) si la base est vide.
    N'injecte jamais de fausses données de démonstration.
    """
    return ensure_database_ready()
