<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>NETWATCH MAP - Projektbeschreibung</title>
</head>
<body>
  <h1>NETWATCH MAP</h1>
  <p>
    NETWATCH MAP ist eine lokale Webanwendung zur Live-Visualisierung von
    Netzwerkverbindungen. Die App ueberwacht aktive TCP- und UDP-Verbindungen
    auf dem aktuellen System und zeigt diese in Echtzeit auf einem interaktiven
    3D-Globus an.
  </p>

  <h2>Was die App macht</h2>
  <ul>
    <li>Erfasst laufend aktive Internetverbindungen des Computers.</li>
    <li>Unterscheidet zwischen eingehenden und ausgehenden Verbindungen.</li>
    <li>Filtert private, lokale und nicht relevante IP-Adressen heraus.</li>
    <li>Bestimmt zu entfernten IPs Standortdaten wie Land, Stadt und ISP.</li>
    <li>Zeigt jede Verbindung als animierte Linie auf einem 3D-Globus.</li>
    <li>Listet erkannte Verbindungen parallel in einer Seitenleiste auf.</li>
    <li>Zeigt beim Anklicken einer Verbindung Zusatzinfos in einer Toolbox auf der Karte.</li>
    <li>Ordnet Verbindungen dem verwendeten Prozess bzw. der Anwendung zu.</li>
  </ul>

  <h2>Live-Funktionen</h2>
  <ul>
    <li>Neue Verbindungen werden automatisch per WebSocket an den Browser gesendet.</li>
    <li>Geschlossene Verbindungen werden direkt aus Liste und Karte entfernt.</li>
    <li>Der Globus fokussiert sich beim Anklicken einer Verbindung auf das Ziel.</li>
    <li>Aktive Verbindungen werden farblich nach Richtung hervorgehoben.</li>
    <li>Statistiken zu Gesamtzahl, Richtungen und betroffenen Laendern werden live aktualisiert.</li>
  </ul>

  <h2>Details pro Verbindung</h2>
  <p>Zu jeder Verbindung koennen unter anderem folgende Informationen angezeigt werden:</p>
  <ul>
    <li>Lokale IP-Adresse und lokaler Port</li>
    <li>Remote-IP-Adresse und Remote-Port</li>
    <li>Portname bzw. bekannter Dienst wie HTTPS, DNS oder SSH</li>
    <li>Status der Verbindung</li>
    <li>Richtung: eingehend oder ausgehend</li>
    <li>Zielland, Stadt, Laendercode und Internetanbieter</li>
    <li>Prozessname der Anwendung</li>
    <li>PID des Prozesses</li>
    <li>Pfad der ausfuehrbaren Datei, sofern auslesbar</li>
  </ul>

  <h2>Benutzeroberflaeche</h2>
  <ul>
    <li>Obere Leiste mit Adapter-Auswahl, Statusanzeige und eigener IP/Standortanzeige</li>
    <li>3D-Globus mit animierten Verbindungslinien, Punkten und Ringen</li>
    <li>Seitenpanel mit laufender Verbindungsliste</li>
    <li>Toolbox auf der Karte fuer Detailinformationen zur ausgewaehlten Verbindung</li>
    <li>Untere Statistikleiste mit Live-Kennzahlen</li>
  </ul>

  <h2>Technischer Aufbau</h2>
  <ul>
    <li>Backend mit Python, Flask und Flask-SocketIO</li>
    <li>Netzwerkueberwachung ueber psutil</li>
    <li>Geolokalisierung ueber ip-api.com mit Cache und Rate-Limit</li>
    <li>Frontend mit HTML, CSS und JavaScript</li>
    <li>3D-Visualisierung ueber Globe.gl</li>
    <li>Echtzeitkommunikation zwischen Backend und Browser per Socket.IO</li>
  </ul>

  <h2>Ablauf der App</h2>
  <ol>
    <li>Beim Start ermittelt die App die oeffentliche IP und den groben Standort des Geraets.</li>
    <li>Ein Hintergrundprozess scannt wiederholt aktive Netzwerkverbindungen.</li>
    <li>Relevante externe Verbindungen werden gefiltert und verarbeitet.</li>
    <li>Fuer neue Ziel-IPs werden Geodaten geladen und zwischengespeichert.</li>
    <li>Prozessinformationen der jeweiligen Verbindung werden ausgelesen.</li>
    <li>Die Daten werden in Echtzeit an die Browseroberflaeche uebertragen.</li>
    <li>Die Oberflaeche aktualisiert Globus, Liste, Toolbox und Statistik automatisch.</li>
  </ol>

  <h2>Besondere Merkmale</h2>
  <ul>
    <li>Lokale Ausfuehrung ohne externe Cloud-Plattform</li>
    <li>Fokus auf visuelle Netzwerktransparenz in Echtzeit</li>
    <li>Zuordnung von Verbindungen zu konkreten Anwendungen</li>
    <li>Adapter-basierter Filter fuer gezielte Analyse einzelner Netzwerkschnittstellen</li>
    <li>Kombination aus Monitoring, Geolokalisierung und 3D-Darstellung</li>
  </ul>

  <h2>Einsatzmoeglichkeiten</h2>
  <ul>
    <li>Analyse, welche Programme Internetverbindungen aufbauen</li>
    <li>Sichtbarmachung externer Ziele und Verbindungswege</li>
    <li>Ueberwachung von Netzwerkaktivitaeten auf einem lokalen Rechner</li>
    <li>Demonstration und Visualisierung fuer Security-, Netzwerk- oder Admin-Zwecke</li>
  </ul>

  <h2>Hinweis</h2>
  <p>
    Die Anwendung ist auf Live-Monitoring und Visualisierung ausgelegt. Die
    Genauigkeit von Geodaten haengt vom verwendeten IP-Geolocation-Dienst ab.
    Manche Prozesspfade oder Prozessnamen koennen je nach Berechtigungen des
    Betriebssystems nur eingeschraenkt verfuegbar sein.
  </p>
</body>
</html>
