# SkuterBet

Wirtualny bukmacher na zlot. Streamlit + Postgres.

## 1. Załóż darmową bazę Postgres
Najprościej [Neon](https://neon.tech) albo [Supabase](https://supabase.com), darmowy plan wystarczy.
Po założeniu skopiuj "connection string" (będzie wyglądał jak
`postgresql://user:pass@host/dbname`).

## 2. Wrzuć kod na GitHub
Załóż prywatne repo i wrzuć do niego całą zawartość tego folderu.

## 3. Wdróż na Streamlit Community Cloud
1. Wejdź na [share.streamlit.io](https://share.streamlit.io), zaloguj się GitHubem.
2. Wskaż repo i plik główny `app.py`.
3. W panelu aplikacji wejdź w **Settings > Secrets** i wklej:
   ```
   DATABASE_URL = "postgresql://user:pass@host/dbname"
   ```
4. Deploy. Dostaniesz publiczny URL.

## 4. Załóż konta uczestników
Zanim wyślesz link chłopakom, załóż konta. Najprościej lokalnie:

```bash
pip install -r requirements.txt
export DATABASE_URL="postgresql://user:pass@host/dbname"   # ta sama baza co w Secrets
python seed_users.py
```

Wcześniej zedytuj listę `UCZESTNICY` w `seed_users.py` (dokładne nicki, pod którymi
mają się logować) oraz `HASLO_TYMCZASOWE`. `Mati_ALB` i `Czolasty` muszą wystąpić
dokładnie pod tymi nickami, bo panel admina jest do nich przypisany na sztywno.

Wyślij każdemu: **link do apki + jego nick + hasło tymczasowe**. Przy pierwszym
logowaniu apka wymusi ustawienie własnego hasła.

Możesz też dodawać/resetować konta później z poziomu apki, w panelu Czolastego
("Zarządzanie kontami"), bez odpalania skryptu.

## 5. Przebieg zlotu w apce
1. **Czolasty** otwiera fazę dodawania zdarzeń (domyślnie otwarta od startu).
2. Każdy loguje się i dodaje po jednym zdarzeniu na każdego innego uczestnika
   + jedno zdarzenie ogólne. Zdarzenia dodane przez innych widać na żywo.
3. **Czolasty** zamyka fazę dodawania zdarzeń.
4. **Mati_ALB** i **Czolasty** wchodzą w "Kursy i rozliczenia" i wystawiają
   kurs (i typ rynku: TAK/NIE albo tylko TAK) dla każdego zdarzenia.
5. Gdy wszystko ma kurs, jeden z adminów klika "Otwórz obstawianie".
6. Uczestnicy budują kupony (AKO, wiele zdarzeń na kupon, kursy się mnożą)
   i obstawiają. Minimalna stawka: 5 zł.
7. W trakcie zlotu admini rozstrzygają zdarzenia (TAK / NIE / Anuluj) w
   zakładce "Rozliczanie zdarzeń". Kupony rozliczają się automatycznie:
   - jedna przegrana noga = cały kupon przegrany,
   - wszystkie nogi zamknięte na wygraną/anulowaną = kupon wygrany,
     anulowana noga liczy się jako kurs 1.00 (zwrot bez zysku/straty na tej nodze).
   - Da się cofnąć rozstrzygnięcie (misclick) przyciskiem "Przywróć", nawet
     jeśli kupon zdążył się już wypłacić — wypłata zostanie cofnięta.
   - Admini mogą też zmieniać kurs już wystawionego, otwartego zdarzenia
     (stary kurs pokazuje się przekreślony, nowy na zielono/czerwono).
8. Na koniec zlotu dowolny admin klika "Zakończ zlot" — ranking zostaje
   widoczny, ale obstawianie i rozliczanie się zamyka.

## Uwagi
- Ranking sortowany po: suma (wolny budżet + budżet w grze) → liczba
  wygranych kuponów → liczba wygranych zdarzeń (nóg) łącznie na wszystkich
  kuponach.
- Nie ma doładowań — jak ktoś przegra wszystko, koniec gry dla niego.
- Aplikacja odświeża ranking i listę dodawanych zdarzeń co kilka sekund
  (`streamlit-autorefresh`), żeby wyglądało na żywo między telefonami.
