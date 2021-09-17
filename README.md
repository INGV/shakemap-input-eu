<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [shakemap-input-eu](#shakemap-input-eu)
  - [Situazione attuale](#situazione-attuale)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# shakemap-input-eu
Repository for ShakeMap4 input XML files

comandi per configurare le credenziali di github:

git remote rm origin

git remote add origin https://serioca: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@github.com/INGV/shakemap-input-eu.git

todo

anno (CCYY) in testa alla root /data
verificare i cambiamenti di event.xml (perche il campo ora cambia sempre, quindi controllare tutti meno questo)
verifica di chi ha fatto il commit (solo i commit fatti dal programma automatico possono essere sovrascritti)

le due funzioni ESM e RRSM quanto differiscono tra loro. 
se sono simili farne uno solo con url sistemati in fase di priorita (cosi ci possiamo aggiungere il link INGV)

VALENTINO....
Riguardo a shakemap-input-eu, ho parlato con Alberto e non c’e’ piu la necessita di cercare i file prima su ESM e poi su RRSM; si possono cercare su entrambi indistintamente. L’importate e’ che ESM appaia, dal punto di vista di ordinamento alfabetico, dopo RRSM. Quindi i file dovranno, ad esempio, esser chiamati:
20210908_0000116_A_RRSM_dat.xml
20210908_0000116_B_ESM_dat.xml
Per quanto riguarda il nome delle directory, sotto data meglio mettere una directory con YYYYMM; esempio:
data/202109
20210905_0000177/current
data/202108
20210807_0000078/current



## Situazione attuale

Per ogni evento viene chiamata due volte la funzione `get_IMs`

La prima volta con le due URL, dati-evento ed evento, di ESM 

La seconda volta con le due URL, dati-evento ed evento, di RRSM

alla funzione  `get_IMs` vengono passate le path assolute dei due file (dati-evento ed evento), dove scrivere i dati scaricati.

Per quanto riguarda il file evento viene creato un file temporaneo che viene passato ad entrambe le chiamate a `get_IMs`. Ciò significa che se i dati evento vengono scaricati da entrambi i siti, nel file ci saranno i dati relativi alla seconda chiamata. Al termine delle due chiamate viene controllato se il file evento già esiste nella cartella. Se non esiste viene creato con il contenuto del file temporaneo. se esiste viene sovrascritto soltanto se i dati sono cambiati a meno del campo `created`. Questo perchè il campo `created` cambia sempre, anche quando i dati sono gli stessi.

Per quanto riguarda il file dati-evento. Il procedimento del file temporaneo viene applicato solo al sito ESM, perchè anche in questo caso è presente nei dati il campo `created`, da non considerare. Prr il sito RRSM vine passato alla funzione `get_IMs` direttamente la path assoluta del file nella cartella di destinazione, che verrà quindi creato o sovrascritto. Nel caso viene sovrascritto pur essendo uguale, la commit di git lo ignorerà.

### Punti da chiarire

La procedura di scarico dati ESM dello script vecchio, nel caso di file già esistente fa un controllo che il file dati-evento sia più recente di un certo numero di giorni passati a configurazione (dfault = 1), se lo è lo scarico dell'evento è annullato. Attualmente la script nuovo ignora questo controllo. Va inserito?

La codice di scarico del file fault (ce  n'è uno nel periodo 2020/10/30), dello script vecchio,  crea due file: `event_fault.txt.sav` e `rupture.json`. Va generato solo il secondo?

Viene chiamata la funzione `_rotate_polygon` che non esiste.





