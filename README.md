# Voce

Interfaccia personale per la sintesi vocale Fish Audio S2 Pro.

- `index.html`: la pagina (GitHub Pages, https://francescoqqqq.github.io/voce/). Voci salvate, cronologia e impostazioni restano nel browser (IndexedDB/localStorage), non sul server.
- `motore.ipynb`: il notebook Colab che fa girare il modello su una T4 gratuita e lo espone con un tunnel Cloudflare temporaneo, protetto da una chiave. Alla fine stampa un link `.../voce/#motore=URL&chiave=K` che collega la pagina.
- `motore.py`: lo stesso codice della cella principale (il notebook si rigenera da qui).

## Correzioni necessarie per la T4 (applicate dal notebook)
- Il modello (4,5 miliardi di parametri) viene creato direttamente sulla GPU in fp16 e i pesi caricati un file alla volta: il codice originale lo crea in RAM a precisione piena (~18 GB) e Colab si chiude.
- `max_seq_len` 32768 → 8192 nel config, e le tabelle fisse 32768×32768 del codec → 8192: altrimenti la GPU da 15 GB non basta.
- CORS: il server accetta l'header `Authorization` (serve alla pagina che sta su un altro indirizzo).
- Porta 7860: la 8080 è già usata da Colab.

## Come funziona la pagina
- Testi lunghi: divisi in pezzi da ~250 caratteri (il tunnel chiude le richieste oltre ~100 s), poi riuniti in un unico WAV. Senza una voce scelta, il primo pezzo fa da voce di riferimento per gli altri, così il timbro non cambia.
- Voci: l'audio caricato o registrato viene convertito in WAV mono 24 kHz (max 30 s) e mandato a ogni richiesta.
- Dialogo: testo con `<|speaker:N|>` e le voci in `references` con `speaker` = N.

Licenza del modello: Fish Audio Research License, solo uso personale/non commerciale.
