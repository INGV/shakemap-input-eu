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

