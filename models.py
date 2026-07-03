"""
Modele bazy danych dla SkuterBet.
Dziala zarowno na Postgres (produkcja) jak i SQLite (testy lokalne),
bo uzywamy SQLAlchemy ORM zamiast surowego SQL.
"""
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Numeric, Boolean,
    DateTime, ForeignKey, Text, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()

STARTOWE_SALDO = 1000.00
MIN_STAWKA = 5.00

# --- Fazy gry (globalny stan aplikacji) ---
FAZA_DODAWANIE_ZDARZEN = "dodawanie_zdarzen"
FAZA_OCZEKIWANIE_NA_KURSY = "oczekiwanie_na_kursy"
FAZA_OBSTAWIANIE = "obstawianie"
FAZA_ZAKONCZONY = "zakonczony"

# --- Statusy zdarzen ---
EVENT_OFERTA_OTWARTA = "oferta_otwarta"          # ma kursy, mozna obstawiac
EVENT_BEZ_KURSU = "bez_kursu"                     # dodane, czeka na wycene
EVENT_ROZSTRZYGNIETE_TAK = "rozstrzygniete_tak"
EVENT_ROZSTRZYGNIETE_NIE = "rozstrzygniete_nie"
EVENT_UNIEWAZNIONE = "uniewaznione"

# --- Typ rynku (ustawiany przez admina razem z kursem) ---
RYNEK_TAK_NIE = "tak_nie"
RYNEK_TYLKO_TAK = "tylko_tak"

# --- Statusy kuponow ---
KUPON_OCZEKUJACY = "oczekujacy"
KUPON_WYGRANY = "wygrany"
KUPON_PRZEGRANY = "przegrany"

# --- Wynik pojedynczej nogi kuponu ---
NOGA_OCZEKUJE = "oczekuje"
NOGA_WYGRANA = "wygrana"
NOGA_PRZEGRANA = "przegrana"
NOGA_UNIEWAZNIONA = "uniewazniona"


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    nick = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    must_change_password = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    saldo = Column(Numeric(12, 2), default=STARTOWE_SALDO, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    coupons = relationship("Coupon", back_populates="user")


class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True)
    opis = Column(Text, nullable=False)
    dotyczy_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # NULL = ogolne
    utworzone_przez = Column(Integer, ForeignKey("users.id"), nullable=False)
    typ_rynku = Column(String(20), nullable=True)  # tak_nie / tylko_tak, ustawiane przy wycenie
    kurs_tak = Column(Numeric(6, 2), nullable=True)
    kurs_nie = Column(Numeric(6, 2), nullable=True)
    kurs_tak_poprzedni = Column(Numeric(6, 2), nullable=True)
    kurs_nie_poprzedni = Column(Numeric(6, 2), nullable=True)
    status = Column(String(30), default=EVENT_BEZ_KURSU, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    usuniete = Column(Boolean, default=False, nullable=False)
    powiadomienie_odczytane = Column(Boolean, default=True, nullable=False)

    dotyczy = relationship("User", foreign_keys=[dotyczy_user_id])
    autor = relationship("User", foreign_keys=[utworzone_przez])


class Coupon(Base):
    __tablename__ = "coupons"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    stawka = Column(Numeric(12, 2), nullable=False)
    kurs_calkowity = Column(Numeric(12, 4), nullable=False)  # snapshot w momencie obstawienia
    status = Column(String(20), default=KUPON_OCZEKUJACY, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    rozliczony_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="coupons")
    legs = relationship("CouponLeg", back_populates="coupon", cascade="all, delete-orphan")


class CouponLeg(Base):
    __tablename__ = "coupon_legs"
    id = Column(Integer, primary_key=True)
    coupon_id = Column(Integer, ForeignKey("coupons.id"), nullable=False)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    typ = Column(String(5), nullable=False)  # 'tak' / 'nie'
    kurs_snapshot = Column(Numeric(6, 2), nullable=False)
    wynik = Column(String(20), default=NOGA_OCZEKUJE, nullable=False)

    coupon = relationship("Coupon", back_populates="legs")
    event = relationship("Event")


class AppState(Base):
    __tablename__ = "app_state"
    id = Column(Integer, primary_key=True, default=1)
    faza = Column(String(30), default=FAZA_DODAWANIE_ZDARZEN, nullable=False)
    nazwa_zlotu = Column(String(100), default="Zlot")


def get_engine(db_url: str):
    connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    return create_engine(db_url, connect_args=connect_args)


def get_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine):
    Base.metadata.create_all(engine)
    Session = get_session_factory(engine)
    with Session() as session:
        state = session.get(AppState, 1)
        if state is None:
            session.add(AppState(id=1, faza=FAZA_DODAWANIE_ZDARZEN))
            session.commit()