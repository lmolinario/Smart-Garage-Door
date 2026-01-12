Cap 5

- Revisioni schermate Bot
- Screenshot bot (comandi, moch up )





\subsection*{Metodologia di misura delle prestazioni}

La valutazione quantitativa delle prestazioni temporali del sistema Smart Garage Door è stata condotta mediante uno strumento software dedicato, sviluppato appositamente nell’ambito del progetto e implementato nel file \texttt{performance\_monitor.py}.
L’obiettivo principale di tale strumento è misurare in modo oggettivo, riproducibile e indipendente la latenza end-to-end del sistema integrato, considerando l’intera catena di comunicazione che intercorre tra l’interfaccia utente remota e l’attuatore fisico della porta.

Nel contesto dei sistemi IoT distribuiti, la latenza end-to-end rappresenta un indicatore prestazionale fondamentale, poiché riflette il tempo complessivo necessario affinché un evento applicativo (ad esempio un comando remoto) venga acquisito, elaborato e tradotto in un’azione fisica sul campo \cite{Zanella2014, Tang2022}.
Per tale motivo, la metodologia adottata non si limita a misurare singoli segmenti della comunicazione (es. rete o backend), ma considera l’intero percorso informativo, comprendendo sia il dominio software sia il dominio embedded.

La catena di misura coinvolge i seguenti livelli architetturali:
\begin{itemize}
    \item \textbf{Application Layer}: invio del comando tramite API REST del server Flask;
    \item \textbf{Network Layer}: pubblicazione MQTT e instradamento Wi-Fi tramite NodeMCU ESP8266;
    \item \textbf{Perception Layer}: ricezione UART su Arduino UNO ed esecuzione del firmware di controllo;
    \item \textbf{Livello fisico}: attivazione reale dell’attuatore e generazione del feedback seriale.
\end{itemize}

Questo approccio è coerente con le linee guida per la valutazione sperimentale dei sistemi cyber-fisici e degli ambienti IoT eterogenei, nei quali è essenziale misurare le prestazioni complessive del sistema piuttosto che i singoli componenti isolati \cite{Marwedel2021, Lee2015}.

\subsection*{Strumento di misura: \texttt{performance\_monitor.py}}

Il modulo \texttt{performance\_monitor.py} è stato progettato come strumento di benchmark automatico per la misurazione della latenza reale del sistema.
Esso opera come processo esterno indipendente, collegandosi contemporaneamente:
\begin{itemize}
    \item al server Flask tramite interfaccia HTTP;
    \item ad Arduino UNO tramite porta seriale UART.
\end{itemize}

In questo modo, lo strumento è in grado di misurare il tempo che intercorre tra:
\begin{enumerate}
    \item l’invio di un comando applicativo (apertura o chiusura porta);
    \item la ricezione del feedback fisico generato dal firmware embedded.
\end{enumerate}

La procedura di misura segue un paradigma \textit{request-response timing}, ampiamente adottato nella validazione dei sistemi distribuiti real-time \cite{Bondavalli2001, Chung2020}.
In particolare, per ciascun test vengono eseguite le seguenti operazioni:

\begin{enumerate}
    \item invio di una richiesta HTTP al server Flask (\texttt{/apri} o \texttt{/chiudi});
    \item avvio del cronometro software;
    \item attesa del messaggio di feedback generato da Arduino tramite seriale;
    \item arresto del cronometro alla ricezione del messaggio;
    \item registrazione del tempo di risposta.
\end{enumerate}

Il frammento seguente mostra la funzione centrale di misura:

\begin{lstlisting}[language=Python, caption={Funzione di misura end-to-end della latenza del sistema}]
def measure_command(cmd_url, expected_feedback):
    ser.reset_input_buffer()
    start = time.time()

    # Invio comando HTTP al server Flask
    requests.get(cmd_url, timeout=TIMEOUT_HTTP)

    # Attesa feedback fisico da Arduino via UART
    while True:
        if time.time() - start > MAX_WAIT:
            return None

        line = ser.readline().decode(errors="ignore").strip()
        if expected_feedback in line:
            return time.time() - start
\end{lstlisting}

Questa funzione consente di misurare la latenza complessiva comprendente:
\begin{itemize}
    \item elaborazione della richiesta REST lato server;
    \item pubblicazione MQTT verso il broker;
    \item propagazione del messaggio sulla rete Wi-Fi;
    \item inoltro UART verso Arduino;
    \item esecuzione del firmware embedded;
    \item risposta fisica dell’attuatore.
\end{itemize}

\subsection*{Campagna sperimentale e analisi statistica}

Per garantire significatività statistica, ogni comando è stato eseguito per un numero prefissato di iterazioni consecutive ($N = 10$).
I tempi di risposta raccolti sono stati successivamente analizzati mediante:
\begin{itemize}
    \item calcolo della media aritmetica;
    \item calcolo della deviazione standard;
    \item individuazione della latenza massima osservata.
\end{itemize}

Al termine della campagna di test, il modulo genera automaticamente:
\begin{itemize}
    \item un file CSV contenente i risultati aggregati;
    \item un grafico PNG per la visualizzazione immediata delle prestazioni;
    \item un report testuale riepilogativo.
\end{itemize}

L’intero processo di misura è completamente automatizzato, consentendo la ripetizione degli esperimenti in condizioni controllate e garantendo la riproducibilità dei risultati, in accordo con le buone pratiche della sperimentazione ingegneristica \cite{Avizienis2004, Marwedel2021}.

\subsection*{Validazione funzionale a supporto delle misure}

A supporto della validità della campagna sperimentale, sono stati utilizzati ulteriori strumenti di test:
\begin{itemize}
    \item \texttt{mqtt\_test.py}, per la simulazione del comportamento del NodeMCU e la verifica della latenza publish/subscribe MQTT;
    \item \texttt{test\_app.py}, per la validazione degli endpoint REST del server Flask e la coerenza dello stato applicativo.
\end{itemize}

Questi moduli permettono di verificare separatamente il corretto funzionamento dei singoli sottosistemi, secondo un approccio di validazione incrementale (\textit{component-based testing}), raccomandato nei sistemi IoT complessi \cite{Tang2022, Zanella2014}.

Nel complesso, la metodologia adottata consente di ottenere una valutazione quantitativa affidabile delle prestazioni temporali del sistema Smart Garage Door, fornendo una base sperimentale solida per l’analisi dei risultati presentati nella sezione seguente.


