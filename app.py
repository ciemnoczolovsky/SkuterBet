import streamlit as st
from decimal import Decimal, InvalidOperation

from models import (
    get_engine, get_session_factory, init_db, User, Event, Coupon,
    FAZA_DODAWANIE_ZDARZEN, FAZA_OCZEKIWANIE_NA_KURSY, FAZA_OBSTAWIANIE, FAZA_ZAKONCZONY,
    EVENT_OFERTA_OTWARTA, EVENT_BEZ_KURSU,
    EVENT_ROZSTRZYGNIETE_TAK, EVENT_ROZSTRZYGNIETE_NIE, EVENT_UNIEWAZNIONE,
    RYNEK_TAK_NIE, RYNEK_TYLKO_TAK,
    KUPON_OCZEKUJACY, KUPON_WYGRANY, KUPON_PRZEGRANY,
    NOGA_WYGRANA, NOGA_PRZEGRANA, NOGA_UNIEWAZNIONA, MIN_STAWKA,
)
import logic
from logic import BladLogiki

st.set_page_config(page_title="SkuterBet", page_icon="🛵", layout="wide")

try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTOREFRESH = True
except ImportError:
    HAS_AUTOREFRESH = False


# ---------------- Setup DB ----------------

@st.cache_resource
def _engine():
    try:
        db_url = st.secrets.get("DATABASE_URL", "sqlite:///skuterbet_local.db")
    except FileNotFoundError:
        # brak pliku secrets.toml w ogole (np. lokalne testy bez konfiguracji) -> SQLite
        db_url = "sqlite:///skuterbet_local.db"
    eng = get_engine(db_url)
    init_db(eng)
    return eng


def get_session():
    Session = get_session_factory(_engine())
    return Session()


# ---------------- Pomocnicze ----------------

def zl(kwota) -> str:
    try:
        return f"{Decimal(kwota):.2f} zł"
    except (InvalidOperation, TypeError):
        return f"{kwota} zł"


def wymagaj_logowania():
    if "user_id" not in st.session_state:
        st.stop()


def current_user(session):
    uid = st.session_state.get("user_id")
    if uid is None:
        return None
    return session.get(User, uid)


def saldo_kolor(kwota, punkt_odniesienia=1000):
    kolor = "#1a9c4a" if float(kwota) >= punkt_odniesienia else "#d1332f"
    return f"<span style='color:{kolor};font-weight:700'>{zl(kwota)}</span>"


def inject_css():
    st.markdown("""
    <style>
    div.stButton > button {
        background-color: #1c1f26;
        border: 1px solid #2e3340;
        border-radius: 8px;
        color: #e8e8e8;
        font-weight: 700;
        padding: 0.55rem 0.4rem;
        width: 100%;
        transition: border-color 0.15s ease;
    }
    div.stButton > button:hover {
        border-color: #f2b705;
        color: #f2b705;
    }
    div.stButton > button[kind="primary"] {
        background-color: #1a9c4a;
        border-color: #1a9c4a;
        color: white;
    }
    .sb-badge {
        display: inline-block;
        background: #262a33;
        color: #9aa0ac;
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.02em;
        padding: 3px 10px;
        border-radius: 999px;
        margin-bottom: 8px;
    }
    .sb-badge-general {
        background: #2a2410;
        color: #f2c94c;
    }
    .sb-title {
        font-size: 1.02rem;
        font-weight: 600;
        color: #f2f2f2;
        margin-bottom: 12px;
        line-height: 1.35;
    }
    .sb-tbd {
        color: #6b7280;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .sb-status {
        font-size: 0.85rem;
        font-weight: 700;
    }
    .sb-autor {
        color: #6b7280;
        font-size: 0.75rem;
        margin-top: 6px;
        margin-bottom: 10px;
    }
    .sb-lb-card {
        display: flex;
        flex-direction: column;
        gap: 4px;
        background: #14161c;
        border: 1px solid #262a33;
        border-radius: 10px;
        padding: 10px 16px;
        margin-bottom: 8px;
    }
    .sb-lb-top {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 10px;
        font-size: 1.0rem;
    }
    .sb-lb-stats {
        display: flex;
        flex-wrap: wrap;
        gap: 4px 16px;
        font-size: 0.78rem;
        color: #9aa0ac;
    }
    </style>
    """, unsafe_allow_html=True)


# ---------------- Ekran logowania ----------------

def ekran_logowania(session):
    st.title("🛵 SkuterBet")
    st.caption("Wirtualny bukmacher na zlot")
    users = logic.all_users(session)
    if not users:
        st.warning("Brak kont w systemie. Poproś admina o utworzenie kont (patrz README).")
        return
    nicki = [u.nick for u in users]
    with st.form("logowanie"):
        nick = st.selectbox("Twój nick", nicki)
        haslo = st.text_input("Hasło", type="password")
        submit = st.form_submit_button("Zaloguj", use_container_width=True)
    if submit:
        user = logic.authenticate(session, nick, haslo)
        if user:
            st.session_state["user_id"] = user.id
            st.rerun()
        else:
            st.error("Złe hasło.")


def ekran_zmiany_hasla(session, user: User):
    st.title("🛵 SkuterBet")
    st.info("To Twoje pierwsze logowanie. Ustaw sobie nowe hasło, żeby nikt inny nie miał dostępu do konta.")
    with st.form("zmiana_hasla"):
        h1 = st.text_input("Nowe hasło", type="password")
        h2 = st.text_input("Powtórz nowe hasło", type="password")
        submit = st.form_submit_button("Ustaw hasło", use_container_width=True)
    if submit:
        if len(h1) < 4:
            st.error("Hasło musi mieć co najmniej 4 znaki.")
        elif h1 != h2:
            st.error("Hasła się nie zgadzają.")
        else:
            logic.change_password(session, user, h1)
            st.success("Hasło ustawione!")
            st.rerun()


# ---------------- Leaderboard ----------------

def widok_leaderboard(session):
    st.subheader("Ranking")
    if HAS_AUTOREFRESH:
        st_autorefresh(interval=8000, key="lb_refresh")
    dane = logic.leaderboard(session)

    html = ""
    for i, row in enumerate(dane):
        medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}."
        kolor = "#1a9c4a" if float(row["suma"]) >= 1000 else "#d1332f"
        html += f"""
        <div class="sb-lb-card">
            <div class="sb-lb-top">
                <span>{medal} <b>{row['nick']}</b></span>
                <span style="color:{kolor};font-weight:700">{zl(row['suma'])}</span>
            </div>
            <div class="sb-lb-stats">
                <span>Wolny budżet: {zl(row['wolny_budzet'])}</span>
                <span>W grze: {zl(row['budzet_w_grze'])}</span>
                <span>Do wygrania: {zl(row['do_wygrania'])}</span>
                <span>Wygrane kupony: {row['wygrane_kupony']}</span>
                <span>Wygrane zakłady: {row['wygrane_zaklady']}</span>
            </div>
        </div>
        """
    st.markdown(html, unsafe_allow_html=True)


# ---------------- Dodawanie zdarzen ----------------

def widok_dodawanie_zdarzen(session, user: User):
    st.subheader("➕ Dodawanie zdarzeń")
    st.caption("Dodaj zdarzenie na każdego uczestnika (oprócz siebie) + jedno zdarzenie ogólne.")

    nastepny = logic.kolejna_osoba_do_wskazania(session, user)
    ogolne_gotowe = logic.dodano_juz_ogolne(session, user)

    if nastepny is not None:
        st.markdown(f"### Podaj zdarzenie na: **{nastepny.nick}**")
        with st.form("dodaj_personalne"):
            opis = st.text_area("Tresc zdarzenia", placeholder=f"np. {nastepny.nick} wypije 4 piwa przed 12:00")
            ok = st.form_submit_button("Dodaj zdarzenie", use_container_width=True)
        if ok and opis.strip():
            try:
                logic.add_event(session, user, opis, nastepny.id)
                st.success("Dodano!")
                st.rerun()
            except BladLogiki as e:
                st.error(str(e))

        st.divider()
        st.markdown(f"#### Istniejace zdarzenia na {nastepny.nick}:")
        istniejace = logic.zdarzenia_na_osobe(session, nastepny.id)
        if istniejace:
            for e in istniejace:
                st.write(f"- {e.opis}  _(dodal: {e.autor.nick})_")
        else:
            st.caption("Jeszcze nikt nic nie dodal na te osobe.")

        st.markdown("#### Wszystkie zdarzenia")
        wszystkie = logic.wszystkie_dodane_zdarzenia(session)
        pozostale = [e for e in wszystkie if e.dotyczy_user_id not in (nastepny.id, user.id)]
        if pozostale:
            for e in pozostale:
                cel = e.dotyczy.nick if e.dotyczy else "OGOLNE"
                st.write(f"**[{cel}]** {e.opis}  _(dodal: {e.autor.nick})_")
        else:
            st.caption("Brak innych zdarzen.")
        return

    if not ogolne_gotowe:
        st.markdown("### Podaj jedno zdarzenie ogólne (dotyczące całej grupy)")
        with st.form("dodaj_ogolne"):
            opis = st.text_area("Treść zdarzenia", placeholder="np. Zakupy w Biedronce over 799,99 zł")
            ok = st.form_submit_button("Dodaj zdarzenie ogólne", use_container_width=True)
        if ok and opis.strip():
            try:
                logic.add_event(session, user, opis, None)
                st.success("Dodano! Skończyłeś dodawanie zdarzeń.")
                st.rerun()
            except BladLogiki as e:
                st.error(str(e))
    else:
        st.success("✅ Dodałeś już wszystkie swoje zdarzenia. Czekaj aż reszta skończy.")

    st.divider()
    st.markdown("#### Zdarzenia dodane do tej pory przez wszystkich (na żywo)")
    if HAS_AUTOREFRESH:
        st_autorefresh(interval=6000, key="dodawanie_refresh")
    zdarzenia = [e for e in logic.wszystkie_dodane_zdarzenia(session) if e.dotyczy_user_id != user.id]
    if not zdarzenia:
        st.write("Jeszcze nic nie dodano.")
    for e in zdarzenia:
        cel = e.dotyczy.nick if e.dotyczy else "🌍 OGÓLNE"
        st.write(f"**[{cel}]** {e.opis}  _(dodał: {e.autor.nick})_")


# ---------------- Oferta / obstawianie ----------------

def _badge_i_tytul(e):
    if e.dotyczy:
        st.markdown(f"<span class='sb-badge'>NA: {e.dotyczy.nick}</span>", unsafe_allow_html=True)
    else:
        st.markdown("<span class='sb-badge sb-badge-general'>ZDARZENIE OGOLNE</span>", unsafe_allow_html=True)
    st.markdown(f"<div class='sb-title'>{e.opis}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='sb-autor'>dodal: {e.autor.nick}</div>", unsafe_allow_html=True)


def widok_oferta(session, user: User):
    st.subheader("Oferta")
    state = logic.get_state(session)

    if state.faza == FAZA_OCZEKIWANIE_NA_KURSY:
        st.warning("Mati_ALB i Czolasty pracuja w tej chwili nad kursami. Zdarzenia widoczne ponizej, ale bez kursow.")

    zdarzenia = logic.zdarzenia_widoczne_dla(session, user)
    if not zdarzenia:
        st.write("Brak zdarzen.")
        return

    if state.faza == FAZA_OBSTAWIANIE:
        _widok_budowania_kuponu(session, user, zdarzenia)
    else:
        kolumny = st.columns(2)
        for i, e in enumerate(zdarzenia):
            with kolumny[i % 2]:
                with st.container(border=True):
                    _badge_i_tytul(e)
                    if e.status in (EVENT_ROZSTRZYGNIETE_TAK, EVENT_ROZSTRZYGNIETE_NIE, EVENT_UNIEWAZNIONE):
                        etykieta = {
                            EVENT_ROZSTRZYGNIETE_TAK: "ROZSTRZYGNIETE: TAK",
                            EVENT_ROZSTRZYGNIETE_NIE: "ROZSTRZYGNIETE: NIE",
                            EVENT_UNIEWAZNIONE: "UNIEWAZNIONE",
                        }[e.status]
                        st.markdown(f"<span class='sb-status'>{etykieta}</span>", unsafe_allow_html=True)
                    else:
                        st.markdown("<span class='sb-tbd'>Kurs: TBD</span>", unsafe_allow_html=True)


def _widok_budowania_kuponu(session, user: User, zdarzenia):
    if "kupon_nogi" not in st.session_state:
        st.session_state["kupon_nogi"] = {}  # event_id -> typ

    aktywne = [e for e in zdarzenia if e.status == EVENT_OFERTA_OTWARTA]
    if not aktywne:
        st.write("Brak aktywnych zdarzen w ofercie (wszystko juz rozstrzygniete).")
        return

    nogi = st.session_state["kupon_nogi"]
    by_id = {e.id: e for e in aktywne}
    if nogi:
        with st.container(border=True):
            st.markdown(f"<span class='sb-badge'>KUPON AKO - {len(nogi)} ZDARZEN</span>", unsafe_allow_html=True)
            kurs_total = Decimal("1.0")
            for eid, typ in list(nogi.items()):
                e = by_id.get(eid)
                if e is None:
                    continue
                kurs = e.kurs_tak if typ == "tak" else e.kurs_nie
                kurs_total *= Decimal(str(kurs))
                cel = e.dotyczy.nick if e.dotyczy else "OGOLNE"
                colA, colB = st.columns([6, 1])
                colA.write(f"[{cel}] {e.opis} - **{typ.upper()}** @{kurs}")
                if colB.button("Usun", key=f"usun_{eid}"):
                    nogi.pop(eid, None)
                    st.rerun()

            st.markdown(f"**Kurs laczny: {kurs_total:.2f}**")
            stawka = st.number_input("Stawka (zl)", min_value=float(MIN_STAWKA), step=5.0, value=float(MIN_STAWKA))
            st.write(f"Mozliwa wygrana: **{zl(kurs_total * Decimal(str(stawka)))}**")
            if st.button("Zatwierdz kupon", type="primary", use_container_width=True):
                try:
                    legs = [(eid, typ) for eid, typ in nogi.items()]
                    logic.zloz_kupon(session, user, legs, stawka)
                    st.session_state["kupon_nogi"] = {}
                    st.success("Kupon przyjety, powodzenia!")
                    st.rerun()
                except BladLogiki as err:
                    st.error(str(err))
        st.divider()
    else:
        st.caption("Kliknij TAK/NIE przy zdarzeniach, zeby dodac je do kuponu.")
        st.divider()

    kolumny = st.columns(2)
    for i, e in enumerate(aktywne):
        wybrany = st.session_state["kupon_nogi"].get(e.id)
        with kolumny[i % 2]:
            with st.container(border=True):
                _badge_i_tytul(e)
                if e.typ_rynku == RYNEK_TAK_NIE:
                    c1, c2 = st.columns(2)
                else:
                    c1, c2 = st.columns([1, 1])
                if c1.button(f"TAK @ {e.kurs_tak}", key=f"tak_{e.id}",
                             type="primary" if wybrany == "tak" else "secondary"):
                    if wybrany == "tak":
                        st.session_state["kupon_nogi"].pop(e.id, None)
                    else:
                        st.session_state["kupon_nogi"][e.id] = "tak"
                    st.rerun()
                if e.typ_rynku == RYNEK_TAK_NIE:
                    if c2.button(f"NIE @ {e.kurs_nie}", key=f"nie_{e.id}",
                                 type="primary" if wybrany == "nie" else "secondary"):
                        if wybrany == "nie":
                            st.session_state["kupon_nogi"].pop(e.id, None)
                        else:
                            st.session_state["kupon_nogi"][e.id] = "nie"
                        st.rerun()


# ---------------- Moje kupony ----------------

def widok_moje_kupony(session, user: User):
    st.subheader("🎟️ Moje kupony")
    kupony = logic.moje_kupony(session, user)
    if not kupony:
        st.write("Nie masz jeszcze żadnych kuponów.")
        return
    for c in kupony:
        if c.status == KUPON_WYGRANY:
            badge = "🟢 WYGRANY"
        elif c.status == KUPON_PRZEGRANY:
            badge = "🔴 PRZEGRANY"
        else:
            badge = "🟡 W GRZE"
        with st.expander(f"{badge} - stawka {zl(c.stawka)} - kurs {c.kurs_calkowity:.2f} - "
                          f"{'wygrana ' + zl(c.stawka * c.kurs_calkowity) if c.status == KUPON_WYGRANY else ''}"):
            for leg in c.legs:
                cel = leg.event.dotyczy.nick if leg.event.dotyczy else "OGÓLNE"
                if leg.wynik == NOGA_WYGRANA:
                    kolor = "green"
                elif leg.wynik == NOGA_PRZEGRANA:
                    kolor = "red"
                elif leg.wynik == NOGA_UNIEWAZNIONA:
                    kolor = "gray"
                else:
                    kolor = "orange"
                st.markdown(
                    f":{kolor}[**[{cel}] {leg.event.opis} - {leg.typ.upper()} @{leg.kurs_snapshot}**]"
                )


# ---------------- Panel admina: fazy i konta (Czolasty) ----------------

def panel_czolasty(session, user: User):
    st.subheader("⚙️ Panel Czolastego - sterowanie fazami")
    state = logic.get_state(session)
    st.write(f"Aktualna faza: **{state.faza}**")

    c1, c2, c3, c4 = st.columns(4)
    if c1.button("Otwórz dodawanie zdarzeń"):
        try:
            logic.otworz_faze_dodawania(session, user)
            st.rerun()
        except BladLogiki as e:
            st.error(str(e))
    if c2.button("Zamknij dodawanie zdarzeń"):
        try:
            logic.zamknij_faze_dodawania(session, user)
            st.rerun()
        except BladLogiki as e:
            st.error(str(e))
    if c3.button("Otwórz obstawianie", type="primary"):
        try:
            logic.otworz_obstawianie(session, user)
            st.rerun()
        except BladLogiki as e:
            st.error(str(e))
    if c4.button("🏁 Zakończ zlot"):
        try:
            logic.zakoncz_zlot(session, user)
            st.rerun()
        except BladLogiki as e:
            st.error(str(e))

    st.divider()
    st.markdown("#### Zarządzanie kontami")
    with st.form("nowe_konto"):
        nick = st.text_input("Nick nowego uczestnika")
        haslo = st.text_input("Hasło tymczasowe", value="zlot2026")
        admin = st.checkbox("Konto administratora")
        ok = st.form_submit_button("Utwórz konto")
    if ok and nick.strip():
        try:
            logic.create_user(session, nick.strip(), haslo, admin)
            st.success(f"Utworzono konto {nick}")
            st.rerun()
        except BladLogiki as e:
            st.error(str(e))

    st.markdown("#### Reset hasła")
    users = logic.all_users(session)
    with st.form("reset_hasla"):
        wybrany = st.selectbox("Użytkownik", [u.nick for u in users])
        nowe_haslo = st.text_input("Nowe hasło tymczasowe", value="zlot2026")
        ok2 = st.form_submit_button("Resetuj hasło")
    if ok2:
        u = next(x for x in users if x.nick == wybrany)
        logic.reset_password(session, u, nowe_haslo)
        st.success(f"Zresetowano hasło {wybrany}, użytkownik ustawi nowe przy logowaniu.")


# ---------------- Panel admina: kursy i rozliczanie ----------------

def panel_kursy_rozliczenia(session, user: User):
    st.subheader("💹 Kursy i rozliczenia")
    tab1, tab2, tab3, tab4 = st.tabs(
        ["Wystawianie kursów", "Rozliczanie zdarzeń", "Usuwanie zdarzeń", "Kara / korekta salda"]
    )

    with tab1:
        do_wyceny = [e for e in logic.zdarzenia_do_wyceny(session) if e.dotyczy_user_id != user.id]
        if not do_wyceny:
            st.success("Wszystkie zdarzenia mają już kurs.")
        for e in do_wyceny:
            cel = e.dotyczy.nick if e.dotyczy else "🌍 OGÓLNE"
            with st.form(f"kurs_{e.id}"):
                st.write(f"**[{cel}] {e.opis}**")
                rynek = st.radio("Typ rynku", [RYNEK_TAK_NIE, RYNEK_TYLKO_TAK],
                                  format_func=lambda x: "TAK / NIE" if x == RYNEK_TAK_NIE else "Tylko TAK",
                                  key=f"rynek_{e.id}", horizontal=True)
                colk1, colk2 = st.columns(2)
                kt = colk1.number_input("Kurs TAK", min_value=1.0, step=0.05, value=2.0, key=f"kt_{e.id}")
                kn = None
                if rynek == RYNEK_TAK_NIE:
                    kn = colk2.number_input("Kurs NIE", min_value=1.0, step=0.05, value=2.0, key=f"kn_{e.id}")
                ok = st.form_submit_button("Ustaw kurs")
            if ok:
                try:
                    logic.ustaw_kurs(session, user, e, rynek, kt, kn)
                    st.rerun()
                except BladLogiki as err:
                    st.error(str(err))

        st.divider()
        st.markdown("#### Zmiana kursów już wystawionych")
        wycenione = session.query(Event).filter_by(status=EVENT_OFERTA_OTWARTA, usuniete=False).filter(
            (Event.dotyczy_user_id != user.id) | (Event.dotyczy_user_id.is_(None))
        ).all()
        for e in wycenione:
            cel = e.dotyczy.nick if e.dotyczy else "🌍 OGÓLNE"
            with st.expander(f"[{cel}] {e.opis}"):
                _pokaz_kurs_z_historia(e, "TAK", e.kurs_tak, e.kurs_tak_poprzedni)
                if e.kurs_nie is not None:
                    _pokaz_kurs_z_historia(e, "NIE", e.kurs_nie, e.kurs_nie_poprzedni)
                with st.form(f"zmiana_kurs_{e.id}"):
                    nk_tak = st.number_input("Nowy kurs TAK", min_value=1.0, step=0.05,
                                              value=float(e.kurs_tak), key=f"nkt_{e.id}")
                    nk_nie = None
                    if e.kurs_nie is not None:
                        nk_nie = st.number_input("Nowy kurs NIE", min_value=1.0, step=0.05,
                                                  value=float(e.kurs_nie), key=f"nkn_{e.id}")
                    ok2 = st.form_submit_button("Zaktualizuj kurs")
                if ok2:
                    try:
                        logic.ustaw_kurs(session, user, e, e.typ_rynku, nk_tak, nk_nie)
                        st.rerun()
                    except BladLogiki as err:
                        st.error(str(err))

    with tab2:
        aktywne = session.query(Event).filter(
            Event.status.in_([EVENT_OFERTA_OTWARTA]), Event.usuniete == False
        ).filter(
            (Event.dotyczy_user_id != user.id) | (Event.dotyczy_user_id.is_(None))
        ).all()
        if not aktywne:
            st.write("Brak zdarzeń czekających na rozstrzygnięcie.")
        for e in aktywne:
            cel = e.dotyczy.nick if e.dotyczy else "🌍 OGÓLNE"
            c1, c2, c3, c4 = st.columns([5, 1, 1, 1])
            c1.write(f"**[{cel}] {e.opis}**")
            if c2.button("✅ TAK", key=f"wtak_{e.id}"):
                logic.rozstrzygnij_zdarzenie(session, user, e, "tak")
                st.rerun()
            if c3.button("❌ NIE", key=f"wnie_{e.id}"):
                logic.rozstrzygnij_zdarzenie(session, user, e, "nie")
                st.rerun()
            if c4.button("🚫 Anuluj", key=f"wanul_{e.id}"):
                logic.rozstrzygnij_zdarzenie(session, user, e, "uniewaznione")
                st.rerun()

        st.divider()
        st.markdown("#### Rozstrzygnięte (cofnij w razie pomyłki)")
        rozstrzygniete = session.query(Event).filter(
            Event.status.in_([EVENT_ROZSTRZYGNIETE_TAK, EVENT_ROZSTRZYGNIETE_NIE, EVENT_UNIEWAZNIONE]),
            Event.usuniete == False
        ).filter(
            (Event.dotyczy_user_id != user.id) | (Event.dotyczy_user_id.is_(None))
        ).all()
        for e in rozstrzygniete:
            cel = e.dotyczy.nick if e.dotyczy else "🌍 OGÓLNE"
            c1, c2 = st.columns([6, 1])
            c1.write(f"[{cel}] {e.opis} - **{e.status}**")
            if c2.button("↩️ Przywróć", key=f"cofnij_{e.id}"):
                logic.przywroc_zdarzenie(session, user, e)
                st.rerun()

    with tab3:
        st.caption("Usuniecie zdarzenia jest ostateczne. Jesli ktos juz na nim postawil, "
                   "zaklad zostanie automatycznie potraktowany jak uniewazniony (zwrot stawki na tej nodze). "
                   "Autor dostanie powiadomienie przy nastepnym logowaniu.")
        wszystkie = [e for e in logic.wszystkie_dodane_zdarzenia(session) if e.dotyczy_user_id != user.id]
        if not wszystkie:
            st.write("Brak zdarzen.")
        for e in wszystkie:
            cel = e.dotyczy.nick if e.dotyczy else "OGOLNE"
            c1, c2 = st.columns([6, 1])
            c1.write(f"[{cel}] {e.opis}  _(dodal: {e.autor.nick}, status: {e.status})_")
            if c2.button("Usun", key=f"usun_zdarzenie_{e.id}"):
                logic.usun_zdarzenie(session, user, e)
                st.success("Zdarzenie usuniete.")
                st.rerun()

    with tab4:
        st.caption("Reczne potracenie salda, np. w razie jawnej ustawki.")
        users = logic.all_users(session)
        with st.form("kara_saldo"):
            wybrany = st.selectbox("Uzytkownik", [u.nick for u in users])
            kwota = st.number_input("Kwota do potracenia (zl)", min_value=0.01, step=10.0, value=50.0)
            ok3 = st.form_submit_button("Potracaj", type="primary")
        if ok3:
            try:
                target = next(x for x in users if x.nick == wybrany)
                logic.potracenie_salda(session, user, target, kwota)
                st.success(f"Potracono {zl(kwota)} od {wybrany}. Nowe saldo: {zl(target.saldo)}")
                st.rerun()
            except BladLogiki as err:
                st.error(str(err))


def _pokaz_kurs_z_historia(e, etykieta, aktualny, poprzedni):
    if poprzedni is not None:
        try:
            wzrost = float(aktualny) > float(poprzedni)
        except (TypeError, ValueError):
            wzrost = True
        kolor = "green" if wzrost else "red"
        st.markdown(f"{etykieta}: ~~{poprzedni}~~ → :{kolor}[**{aktualny}**]")
    else:
        st.write(f"{etykieta}: **{aktualny}**")


# ---------------- MAIN ----------------

def main():
    inject_css()
    session = get_session()

    if "user_id" not in st.session_state:
        ekran_logowania(session)
        session.close()
        return

    user = current_user(session)
    if user is None:
        st.session_state.pop("user_id", None)
        st.rerun()

    if user.must_change_password:
        ekran_zmiany_hasla(session, user)
        session.close()
        return

    state = logic.get_state(session)

    notyfikacje = logic.nieprzeczytane_powiadomienia(session, user)
    if notyfikacje:
        for e in notyfikacje:
            cel = e.dotyczy.nick if e.dotyczy else "zdarzenie ogolne"
            if state.faza == FAZA_DODAWANIE_ZDARZEN:
                st.warning(
                    f"Twoje zdarzenie \"{e.opis}\" (na {cel}) zostalo usuniete przez admina. "
                    f"Dodaj je jeszcze raz w zakladce 'Dodawanie zdarzen'."
                )
            else:
                st.warning(f"Twoje zdarzenie \"{e.opis}\" (na {cel}) zostalo usuniete przez admina.")
        logic.oznacz_powiadomienia_przeczytane(session, notyfikacje)

    with st.sidebar:
        st.markdown(f"### 🛵 SkuterBet")
        st.write(f"Zalogowano jako **{user.nick}**" + (" (admin)" if user.is_admin else ""))
        st.write(f"Saldo: {zl(user.saldo)}")
        if state.faza == FAZA_ZAKONCZONY:
            st.warning("🏁 Zlot zakończony")
        if st.button("Wyloguj"):
            st.session_state.pop("user_id", None)
            st.rerun()

        strony = ["🏆 Ranking"]
        if state.faza == FAZA_DODAWANIE_ZDARZEN:
            strony.append("➕ Dodawanie zdarzeń")
        if state.faza in (FAZA_OCZEKIWANIE_NA_KURSY, FAZA_OBSTAWIANIE, FAZA_ZAKONCZONY):
            strony.append("📋 Oferta")
        strony.append("🎟️ Moje kupony")
        if user.is_admin and user.nick == "Czolasty":
            strony.append("⚙️ Panel Czolastego")
        if user.is_admin:
            strony.append("💹 Kursy i rozliczenia")

        wybor = st.radio("Nawigacja", strony, label_visibility="collapsed")

    if wybor == "🏆 Ranking":
        widok_leaderboard(session)
    elif wybor == "➕ Dodawanie zdarzeń":
        widok_dodawanie_zdarzen(session, user)
    elif wybor == "📋 Oferta":
        widok_oferta(session, user)
    elif wybor == "🎟️ Moje kupony":
        widok_moje_kupony(session, user)
    elif wybor == "⚙️ Panel Czolastego":
        panel_czolasty(session, user)
    elif wybor == "💹 Kursy i rozliczenia":
        panel_kursy_rozliczenia(session, user)

    session.close()


if __name__ == "__main__":
    main()
