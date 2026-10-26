# File arricchito per la piattaforma di outreach

Specifica del file che Antigravity deve produrre a partire da un export Lusha.

La piattaforma non inventa niente: compone l'email dai campi di questo file.
Se Contesto, Gancio ed Email sono compilati, la riga entra gia' **Pronta** e
l'AI interna (DeepSeek) non viene chiamata affatto.

## Formato

Un `.xlsx` o un `.csv`, una riga per referente. Il nome del file deve contenere
la parola `lusha`, e va lasciato nella cartella Download: il sorvegliante lo
prende da solo entro 24 ore.

Le intestazioni possono stare in una delle prime 12 righe. Maiuscole, accenti e
spazi non contano.

## Colonne obbligatorie

| Colonna | Contenuto |
|---|---|
| `Azienda` | Ragione sociale. Senza questa la riga viene scartata. |
| `Email` | Indirizzo del referente. Senza questa la riga viene scartata. |
| `Contatto` | Nome e cognome. In alternativa due colonne `Nome` e `Cognome`. |

## Le tre colonne che costruiscono l'email

Sono quelle che Antigravity deve riempire con la ricerca. Compongono questa
apertura:

> sono Luca Roberto Schoenbech, Talent Sourcing Advisor. Lavoro sui mercati
> professionali dell'industria: **\<Contesto\>**. Dialogo con **\<Gancio\>**.

e l'oggetto:

> Mappatura di mercato e competenze — **\<Tecnologia\>**

### `Tecnologia`

La tecnologia o il processo concreto dell'azienda, come risulta dalla ricerca.

- da 2 a 5 parole
- niente punto finale, niente inglese se esiste il termine italiano
- esempi: `estrusione e stampaggio`, `formatura e converting`, `produzione sterile`

### `Contesto` (le filiere)

Da 2 a 3 filiere separate da virgola, **senza articoli**, massimo 12 parole.

Vanno scelte solo dentro questi quattro gruppi, mai fuori:

- Life Sciences, Healthcare e Medical Devices
- chimica, cosmetica e consumer health
- industria, automazione e impiantistica
- packaging e servizi B2B

Esempio: `imballaggi in plastica e gomma, chimica, medicale`

### `Gancio` (le funzioni)

Da 2 a 4 figure professionali concrete, coerenti con quell'azienda. Massimo 14
parole. Completano la frase "Dialogo con ...".

- inizia con un nome o un ruolo, **non** con "di"
- niente verbi, niente la parola "profili", niente frasi relative ("dove", "in cui")
- niente giudizi sul mercato o sulla scarsita', niente punto finale

Esempio: `responsabili di produzione, ingegneri di processo, tecnici della qualita'`

## Regole che l'uscita deve rispettare

La piattaforma misura queste righe con un controllo di qualita'. Una riga che
non le rispetta non parte.

1. **Niente formule generiche** in `Gancio`. Sono rifiutate:
   `tecnici e manageriali`, `figure tecniche`, `profili tecnici`,
   `personale tecnico`, `ruoli tecnici`, `tecnici e manager`,
   `figure professionali`, `risorse qualificate`.
2. **Nessuna parola ripetuta** fra `Tecnologia`, `Contesto` e `Gancio`, nemmeno
   della stessa famiglia (`radiofarmaci` / `radiofarmaceutico`,
   `estrusione` / `estrusori`).
3. Almeno 2 voci in `Contesto`, almeno 2 in `Gancio`.
4. **Niente invenzioni**: nessun cliente, incarico, numero, tempo o referenza
   che non risulti dalla ricerca. Nessun prezzo o tariffa.
5. Mai le parole `recruiter`, `head hunting`, `ricerca e selezione` riferite al
   lavoro di Schoenbech.
6. Italiano sobrio e professionale, senza superlativi ne' toni commerciali.

## Colonne facoltative

| Colonna | Contenuto |
|---|---|
| `Appiglio` | Una frase che apre l'email prima della presentazione, se la ricerca ha trovato un motivo concreto per scrivere ora (es. un impianto nuovo, una posizione pubblicata). Va lasciata vuota se non c'e' niente di vero da dire. |
| `Timing` | Indicazione di tempistica. Non abbassa mai il livello di dettaglio degli altri campi. |
| `Flag` | `OK`, `Verifica`, `Correzione`, oppure `Sensibile`. |

### Quando usare `Sensibile`

Se la ricerca trova una situazione delicata — ammortizzatori sociali, crisi,
fermo produzione, ricapitalizzazione, discontinuita' — allora e **solo allora**
`Gancio` puo' restare generico (`tecnici e manageriali`) e `Flag` va messo a
`Sensibile`. In quel caso il controllo di qualita' non segnala la riga.

## Colonne della ricerca (alternativa)

Se per un'azienda Antigravity preferisce consegnare il materiale grezzo invece
delle tre colonne finali, puo' compilare queste e lasciare che sia la
piattaforma a scrivere:

| Colonna | Contenuto |
|---|---|
| `Attivita` | Cosa fa l'azienda in Italia, in concreto. |
| `Competenze` | Competenze e professionalita' rilevanti. |
| `Segnale` | Evento recente che giustifica il contatto ora. |
| `Alert` | Nota di correzione, se la ricerca smentisce qualcosa. |

Il risultato sara' piu' povero: la piattaforma riformula, non cerca. Vale la
pena usarla solo dove la ricerca non e' arrivata a conclusioni nette.

## Esempio di riga completa

| Azienda | Contatto | Email | Tecnologia | Contesto | Gancio |
|---|---|---|---|---|---|
| Packly | Simone Congedo | simone.congedo@pack.ly | fustellatura e converting | packaging, chimica, medicale | responsabili di produzione, ingegneri di processo, tecnici della qualita' |

## Cosa succede dopo

1. Il file finisce in Download, il sorvegliante lo legge e lo archivia in `_importati`.
2. Le righe entrano nella campagna `Da rivedere`.
3. Quelle con Contesto + Gancio + Email sono **Pronte**; le altre restano Bozza.
4. Chi e' gia' stato contattato in una campagna precedente viene escluso da solo.
5. Gli invii partono con il ritmo e la finestra oraria configurati.
