"""
Cala logika biznesowa SkuterBet: dodawanie zdarzen, wycena, obstawianie,
rozliczanie kuponow, leaderboard. Trzymana osobno od UI (app.py).
"""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import func

from models import (
    User, Event, Coupon, CouponLeg, AppState,
    STARTOWE_SALDO, MIN_STAWKA,
    FAZA_DODAWANIE_ZDARZEN, FAZA_OCZEKIWANIE_NA_KURSY, FAZA_OBSTAWIANIE, FAZA_ZAKONCZONY,
    EVENT_OFERTA_OTWARTA, EVENT_BEZ_KURSU,
    EVENT_ROZSTRZYGNIETE_TAK, EVENT_ROZSTRZYGNIETE_NIE, EVENT_UNIEWAZNIONE,
    RYNEK_TAK_NIE, RYNEK_TYLKO_TAK,
    KUPON_OCZEKUJACY, KUPON_WYGRANY, KUPON_PRZEGRANY,
    NOGA_OCZEKUJE, NOGA_WYGRANA, NOGA_PRZEGRANA, NOGA_UNIEWAZNIONA,
)
from auth import encode_password, verify_password


class BladLogiki(Exception):
    pass


# ---------- Stan gry ----------

def get_state(session) -> AppState:
    return session.get(AppState, 1)


def set_faza(session, nowa_faza: str):
    state = get_state(session)
    state.faza = nowa_faza
    session.commit()


# ---------- Uzytkownicy ----------

def create_user(session, nick: str, temp_password: str, is_admin: bool = False) -> User:
    istnieje = session.query(User).filter_by(nick=nick).first()
    if istnieje:
        raise BladLogiki(f"Uzytkownik {nick} juz istnieje.")
    user = User(
        nick=nick,
        password_hash=encode_password(temp_password),
        must_change_password=True,
        is_admin=is_admin,
        saldo=STARTOWE_SALDO,
    )
    session.add(user)
    session.commit()
    return user


def reset_password(session, user: User, temp_password: str):
    user.password_hash = encode_password(temp_password)
    user.must_change_password = True
    session.commit()


def authenticate(session, nick: str, password: str):
    user = session.query(User).filter_by(nick=nick).first()
    if user and verify_password(password, user.password_hash):
        return user
    return None


def change_password(session, user: User, new_password: str):
    user.password_hash = encode_password(new_password)
    user.must_change_password = False
    session.commit()


def all_users(session):
    return session.query(User).order_by(User.nick).all()


# ---------- Faza 1: dodawanie zdarzen ----------

def czy_uzytkownik_moze_dodac_zdarzenie(session, user: User) -> bool:
    """Sprawdza czy user ma jeszcze jakies zdarzenia do dodania (na kogos + 1 ogolne)."""
    inni = [u for u in all_users(session) if u.id != user.id]
    dodane_personalne = session.query(Event).filter_by(
        utworzone_przez=user.id, usuniete=False
    ).filter(Event.dotyczy_user_id.isnot(None)).count()
    dodane_ogolne = session.query(Event).filter_by(
        utworzone_przez=user.id, dotyczy_user_id=None, usuniete=False
    ).count()
    return dodane_personalne < len(inni) or dodane_ogolne < 1


def kolejna_osoba_do_wskazania(session, user: User):
    """Zwraca nastepnego usera, na ktorego 'user' jeszcze nie dodal zdarzenia, albo None
    jesli wszystkie personalne juz dodane (zostaje tylko ogolne)."""
    inni = [u for u in all_users(session) if u.id != user.id]
    juz_dodane_ids = {
        e.dotyczy_user_id for e in session.query(Event).filter_by(
            utworzone_przez=user.id, usuniete=False
        ).filter(Event.dotyczy_user_id.isnot(None)).all()
    }
    for u in inni:
        if u.id not in juz_dodane_ids:
            return u
    return None


def dodano_juz_ogolne(session, user: User) -> bool:
    return session.query(Event).filter_by(
        utworzone_przez=user.id, dotyczy_user_id=None, usuniete=False
    ).count() > 0


def add_event(session, user: User, opis: str, dotyczy_user_id):
    state = get_state(session)
    if state.faza != FAZA_DODAWANIE_ZDARZEN:
        raise BladLogiki("Faza dodawania zdarzen jest zamknieta.")
    if dotyczy_user_id == user.id:
        raise BladLogiki("Nie mozesz dodac zdarzenia na samego siebie.")
    event = Event(
        opis=opis.strip(),
        dotyczy_user_id=dotyczy_user_id,
        utworzone_przez=user.id,
        status=EVENT_BEZ_KURSU,
    )
    session.add(event)
    session.commit()
    return event


def wszystkie_dodane_zdarzenia(session):
    """Do podgladu na zywo w trakcie fazy dodawania (zeby uniknac duplikatow)."""
    return session.query(Event).filter_by(usuniete=False).order_by(Event.created_at.desc()).all()


def zdarzenia_na_osobe(session, target_user_id):
    """Zdarzenia dotyczace konkretnej osoby, do podgladu 'istniejace zdarzenia na X'."""
    return session.query(Event).filter_by(
        dotyczy_user_id=target_user_id, usuniete=False
    ).order_by(Event.created_at.desc()).all()


def zamknij_faze_dodawania(session, user: User):
    if not user.is_admin or user.nick != "Czolasty":
        raise BladLogiki("Tylko Czolasty moze zamknac faze dodawania zdarzen.")
    set_faza(session, FAZA_OCZEKIWANIE_NA_KURSY)


def otworz_faze_dodawania(session, user: User):
    if not user.is_admin or user.nick != "Czolasty":
        raise BladLogiki("Tylko Czolasty moze otworzyc faze dodawania zdarzen.")
    set_faza(session, FAZA_DODAWANIE_ZDARZEN)


# ---------- Faza 2: wycena (kursy) ----------

def zdarzenia_widoczne_dla(session, user: User, tylko_z_kursem=False):
    """Zdarzenia widoczne dla danego usera - bez tych, ktore go dotycza."""
    q = session.query(Event).filter_by(usuniete=False).filter(
        (Event.dotyczy_user_id != user.id) | (Event.dotyczy_user_id.is_(None))
    )
    if tylko_z_kursem:
        q = q.filter(Event.status == EVENT_OFERTA_OTWARTA)
    return q.order_by(Event.created_at.asc()).all()


def zdarzenia_do_wyceny(session):
    return session.query(Event).filter_by(status=EVENT_BEZ_KURSU, usuniete=False).order_by(Event.created_at.asc()).all()


def ustaw_kurs(session, admin: User, event: Event, typ_rynku: str, kurs_tak, kurs_nie=None):
    if not admin.is_admin:
        raise BladLogiki("Tylko admin moze ustawiac kursy.")
    if typ_rynku == RYNEK_TYLKO_TAK:
        kurs_nie = None
    elif typ_rynku == RYNEK_TAK_NIE:
        if kurs_nie is None:
            raise BladLogiki("Rynek TAK/NIE wymaga obu kursow.")
    else:
        raise BladLogiki("Nieznany typ rynku.")

    # zachowaj poprzednie kursy do wyswietlenia przekreslonych/zmiany koloru
    if event.kurs_tak is not None:
        event.kurs_tak_poprzedni = event.kurs_tak
    if event.kurs_nie is not None:
        event.kurs_nie_poprzedni = event.kurs_nie

    event.typ_rynku = typ_rynku
    event.kurs_tak = Decimal(str(kurs_tak))
    event.kurs_nie = Decimal(str(kurs_nie)) if kurs_nie is not None else None
    if event.status == EVENT_BEZ_KURSU:
        event.status = EVENT_OFERTA_OTWARTA
    session.commit()


def wszystkie_zdarzenia_maja_kurs(session) -> bool:
    return session.query(Event).filter_by(status=EVENT_BEZ_KURSU, usuniete=False).count() == 0


def otworz_obstawianie(session, admin: User):
    if not admin.is_admin:
        raise BladLogiki("Tylko admin moze otworzyc obstawianie.")
    if not wszystkie_zdarzenia_maja_kurs(session):
        raise BladLogiki("Nie wszystkie zdarzenia maja jeszcze wystawiony kurs.")
    set_faza(session, FAZA_OBSTAWIANIE)


# ---------- Faza 3: obstawianie ----------

def kurs_dla_typu(event: Event, typ: str) -> Decimal:
    if typ == "tak":
        return event.kurs_tak
    if typ == "nie":
        if event.kurs_nie is None:
            raise BladLogiki("To zdarzenie ma rynek tylko na TAK.")
        return event.kurs_nie
    raise BladLogiki("Niepoprawny typ zakladu.")


def zloz_kupon(session, user: User, legs: list, stawka):
    """legs: lista (event_id, typ) gdzie typ='tak'/'nie'."""
    state = get_state(session)
    if state.faza != FAZA_OBSTAWIANIE:
        raise BladLogiki("Obstawianie jest w tej chwili zamkniete.")
    stawka = Decimal(str(stawka))
    if stawka < MIN_STAWKA:
        raise BladLogiki(f"Minimalna stawka to {MIN_STAWKA:.2f} zl.")
    if not legs:
        raise BladLogiki("Kupon musi miec co najmniej jedno zdarzenie.")
    if user.saldo < stawka:
        raise BladLogiki("Za male saldo.")

    kurs_calkowity = Decimal("1.0")
    leg_objs = []
    for event_id, typ in legs:
        event = session.get(Event, event_id)
        if event is None:
            raise BladLogiki("Zdarzenie nie istnieje.")
        if event.dotyczy_user_id == user.id:
            raise BladLogiki("Nie mozesz obstawiac zdarzenia dotyczacego samego siebie.")
        if event.status != EVENT_OFERTA_OTWARTA:
            raise BladLogiki(f"Zdarzenie '{event.opis}' nie jest juz dostepne w ofercie.")
        kurs = kurs_dla_typu(event, typ)
        kurs_calkowity *= kurs
        leg_objs.append((event, typ, kurs))

    coupon = Coupon(
        user_id=user.id,
        stawka=stawka,
        kurs_calkowity=kurs_calkowity,
        status=KUPON_OCZEKUJACY,
    )
    session.add(coupon)
    session.flush()

    for event, typ, kurs in leg_objs:
        session.add(CouponLeg(
            coupon_id=coupon.id,
            event_id=event.id,
            typ=typ,
            kurs_snapshot=kurs,
            wynik=NOGA_OCZEKUJE,
        ))

    user.saldo = Decimal(str(user.saldo)) - stawka
    session.commit()
    return coupon


def moje_kupony(session, user: User):
    return session.query(Coupon).filter_by(user_id=user.id).order_by(Coupon.created_at.desc()).all()


# ---------- Faza 4: rozliczanie ----------

def rozstrzygnij_zdarzenie(session, admin: User, event: Event, wynik: str):
    """wynik: 'tak' / 'nie' / 'uniewaznione'"""
    if not admin.is_admin:
        raise BladLogiki("Tylko admin moze rozstrzygac zdarzenia.")
    if wynik == "tak":
        event.status = EVENT_ROZSTRZYGNIETE_TAK
    elif wynik == "nie":
        event.status = EVENT_ROZSTRZYGNIETE_NIE
    elif wynik == "uniewaznione":
        event.status = EVENT_UNIEWAZNIONE
    else:
        raise BladLogiki("Niepoprawny wynik.")
    session.commit()
    _rozlicz_dotkniete_kupony(session, event)


def przywroc_zdarzenie(session, admin: User, event: Event):
    """Cofniecie rozstrzygniecia (misclick). Odwraca tez ewentualne juz wyplacone kupony."""
    if not admin.is_admin:
        raise BladLogiki("Tylko admin moze cofac rozstrzygniecia.")

    # cofnij skutki dla kuponow, ktore zdazyly sie rozliczyc przez to zdarzenie
    legs = session.query(CouponLeg).filter_by(event_id=event.id).all()
    for leg in legs:
        coupon = leg.coupon
        if coupon.status in (KUPON_WYGRANY, KUPON_PRZEGRANY):
            if coupon.status == KUPON_WYGRANY:
                coupon.user.saldo = Decimal(str(coupon.user.saldo)) - Decimal(str(coupon.stawka)) * Decimal(str(coupon.kurs_calkowity))
            coupon.status = KUPON_OCZEKUJACY
            coupon.rozliczony_at = None
        leg.wynik = NOGA_OCZEKUJE

    event.status = EVENT_OFERTA_OTWARTA
    session.commit()


def _rozlicz_dotkniete_kupony(session, event: Event):
    legs = session.query(CouponLeg).filter_by(event_id=event.id).all()
    for leg in legs:
        if event.status == EVENT_ROZSTRZYGNIETE_TAK:
            leg.wynik = NOGA_WYGRANA if leg.typ == "tak" else NOGA_PRZEGRANA
        elif event.status == EVENT_ROZSTRZYGNIETE_NIE:
            leg.wynik = NOGA_WYGRANA if leg.typ == "nie" else NOGA_PRZEGRANA
        elif event.status == EVENT_UNIEWAZNIONE:
            leg.wynik = NOGA_UNIEWAZNIONA
    session.commit()

    # sprawdz kazdy dotkniety kupon - czy mozna go juz rozliczyc
    coupon_ids = {leg.coupon_id for leg in legs}
    for cid in coupon_ids:
        _sprobuj_rozliczyc_kupon(session, session.get(Coupon, cid))


def _sprobuj_rozliczyc_kupon(session, coupon: Coupon):
    if coupon.status != KUPON_OCZEKUJACY:
        return
    wyniki = [leg.wynik for leg in coupon.legs]

    # regula 16: jedna przegrana noga = caly kupon przegrany, natychmiast
    if NOGA_PRZEGRANA in wyniki:
        coupon.status = KUPON_PRZEGRANY
        coupon.rozliczony_at = datetime.utcnow()
        session.commit()
        return

    # regula 15: wszystkie nogi zamkniete (wygrana lub uniewazniona) -> auto rozliczenie
    if all(w in (NOGA_WYGRANA, NOGA_UNIEWAZNIONA) for w in wyniki):
        # przelicz kurs calkowity: nogi uniewaznione licza sie jako 1.0 (push)
        kurs_final = Decimal("1.0")
        for leg in coupon.legs:
            if leg.wynik == NOGA_WYGRANA:
                kurs_final *= leg.kurs_snapshot
        coupon.kurs_calkowity = kurs_final
        coupon.status = KUPON_WYGRANY
        coupon.rozliczony_at = datetime.utcnow()
        coupon.user.saldo = Decimal(str(coupon.user.saldo)) + Decimal(str(coupon.stawka)) * kurs_final
        session.commit()


# ---------- Usuwanie zdarzen (admin) i powiadomienia ----------

def usun_zdarzenie(session, admin: User, event: Event):
    if not admin.is_admin:
        raise BladLogiki("Tylko admin moze usuwac zdarzenia.")
    # jesli ktos juz zdazyl na tym postawic, potraktuj to jak uniewaznienie
    # (zwrot stawek na tej nodze), zanim zdarzenie zniknie z oferty
    ma_zaklady = session.query(CouponLeg).filter_by(event_id=event.id).count() > 0
    if ma_zaklady and event.status == EVENT_OFERTA_OTWARTA:
        rozstrzygnij_zdarzenie(session, admin, event, "uniewaznione")
    event.usuniete = True
    event.powiadomienie_odczytane = False
    session.commit()


def nieprzeczytane_powiadomienia(session, user: User):
    return session.query(Event).filter_by(
        utworzone_przez=user.id, usuniete=True, powiadomienie_odczytane=False
    ).all()


def oznacz_powiadomienia_przeczytane(session, events):
    for e in events:
        e.powiadomienie_odczytane = True
    session.commit()


# ---------- Rezczna korekta salda (kary za ustawki itp.) ----------

def potracenie_salda(session, admin: User, target: User, kwota):
    if not admin.is_admin:
        raise BladLogiki("Tylko admin moze potracac saldo.")
    kwota = Decimal(str(kwota))
    if kwota <= 0:
        raise BladLogiki("Kwota potracenia musi byc dodatnia.")
    target.saldo = max(Decimal("0"), Decimal(str(target.saldo)) - kwota)
    session.commit()




def zakoncz_zlot(session, admin: User):
    if not admin.is_admin:
        raise BladLogiki("Tylko admin moze zakonczyc zlot.")
    set_faza(session, FAZA_ZAKONCZONY)


# ---------- Leaderboard ----------

def leaderboard(session):
    users = all_users(session)
    wyniki = []
    for u in users:
        w_grze = session.query(func.coalesce(func.sum(Coupon.stawka), 0)).filter_by(
            user_id=u.id, status=KUPON_OCZEKUJACY
        ).scalar()
        do_wygrania = Decimal("0")
        for c in session.query(Coupon).filter_by(user_id=u.id, status=KUPON_OCZEKUJACY).all():
            do_wygrania += c.stawka * c.kurs_calkowity
        wygrane_kupony = session.query(Coupon).filter_by(user_id=u.id, status=KUPON_WYGRANY).count()
        wygrane_zaklady = session.query(CouponLeg).join(Coupon).filter(
            Coupon.user_id == u.id, CouponLeg.wynik == NOGA_WYGRANA
        ).count()
        wolny = Decimal(str(u.saldo))
        suma = wolny + Decimal(str(w_grze))
        wyniki.append({
            "nick": u.nick,
            "wolny_budzet": wolny,
            "budzet_w_grze": Decimal(str(w_grze)),
            "do_wygrania": do_wygrania,
            "wygrane_kupony": wygrane_kupony,
            "wygrane_zaklady": wygrane_zaklady,
            "suma": suma,
        })
    wyniki.sort(key=lambda r: (-r["suma"], -r["wygrane_kupony"], -r["wygrane_zaklady"]))
    return wyniki