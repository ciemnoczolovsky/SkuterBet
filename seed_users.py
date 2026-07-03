"""
Jednorazowy skrypt do zalozenia startowych kont przed zlotem.
Uruchom LOKALNIE (nie na Streamlit Cloud) po ustawieniu zmiennej DATABASE_URL
tak, zeby wskazywala na ta sama baze, ktorej uzywa wdrozona apka:

    export DATABASE_URL="postgresql://user:pass@host:5432/dbname"
    python seed_users.py

Kazdy uczestnik dostaje login = nick oraz to samo haslo tymczasowe
(zmien HASLO_TYMCZASOWE ponizej). Po pierwszym logowaniu apka wymusi
zmiane hasla, wiec podajesz to haslo tylko raz.
"""
import os
from models import get_engine, get_session_factory, init_db
import logic

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///skuterbet_local.db")
HASLO_TYMCZASOWE = "zlot2026"

# Uzupelnij lista uczestnikow (dokladnie tak, jak maja sie logowac).
UCZESTNICY = [
    "Milano",
    "Mati_ALB",
    "Czolasty",
    "MatiZet",
    "Radosny",
    "Mikroczip",
    "Quezter77",
]

# Ci dwaj musza wystapic dokladnie pod tymi nickami w liscie powyzej.
ADMINI = {"Mati_ALB", "Czolasty"}


def main():
    engine = get_engine(DATABASE_URL)
    init_db(engine)
    Session = get_session_factory(engine)
    with Session() as session:
        for nick in UCZESTNICY:
            try:
                user = logic.create_user(
                    session, nick, HASLO_TYMCZASOWE, is_admin=(nick in ADMINI)
                )
                print(f"Utworzono: {nick} (admin={nick in ADMINI})")
            except logic.BladLogiki as e:
                print(f"Pominieto {nick}: {e}")


if __name__ == "__main__":
    main()
