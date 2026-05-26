<body>
  <h1>NETWATCH MAP</h1>
  <p>
    NETWATCH MAP is a local web application for live visualization of network
    connections. The app monitors active TCP and UDP connections on the current
    system and displays them in real time on an interactive 3D globe.
  </p>

  <h2>What the app does</h2>
  <ul>
    <li>Continuously detects active internet connections on the computer.</li>
    <li>Distinguishes between incoming and outgoing connections.</li>
    <li>Filters private, local, and irrelevant IP addresses.</li>
    <li>Resolves remote IPs into location data such as country, city, and ISP.</li>
    <li>Displays every connection as an animated line on a 3D globe.</li>
    <li>Lists detected connections in a live side panel.</li>
    <li>Shows additional connection details in a toolbox on the map when clicked.</li>
    <li>Maps connections to the application or process using them.</li>
  </ul>

  <h2>Live features</h2>
  <ul>
    <li>New connections are automatically pushed to the browser via WebSocket.</li>
    <li>Closed connections are removed from the list and map immediately.</li>
    <li>Clicking a connection focuses the globe on the remote destination.</li>
    <li>Active connections are color-coded by direction.</li>
    <li>Statistics for total connections, direction, and affected countries update live.</li>
  </ul>

  <h2>Details shown per connection</h2>
  <p>The app can display the following information for each connection:</p>
  <ul>
    <li>Local IP address and local port</li>
    <li>Remote IP address and remote port</li>
    <li>Port name or known service such as HTTPS, DNS, or SSH</li>
    <li>Connection status</li>
    <li>Direction: incoming or outgoing</li>
    <li>Destination country, city, country code, and ISP</li>
    <li>Process or application name</li>
    <li>Process ID</li>
    <li>Executable path when available</li>
  </ul>

  <h2>User interface</h2>
  <ul>
    <li>Top bar with adapter selection, live status, and local IP/location display</li>
    <li>3D globe with animated connection arcs, points, and pulse rings</li>
    <li>Side panel with a live connection list</li>
    <li>Toolbox overlay on the map for selected connection details</li>
    <li>Bottom statistics bar with real-time metrics</li>
  </ul>

  <h2>Technical structure</h2>
  <ul>
    <li>Backend built with Python, Flask, and Flask-SocketIO</li>
    <li>Network monitoring powered by psutil</li>
    <li>Geolocation provided by ip-api.com with caching and rate limiting</li>
    <li>Frontend built with HTML, CSS, and JavaScript</li>
    <li>3D visualization powered by Globe.gl</li>
    <li>Real-time communication between backend and browser via Socket.IO</li>
  </ul>

  <h2>How the app works</h2>
  <ol>
    <li>On startup, the app determines the device's public IP and approximate location.</li>
    <li>A background worker repeatedly scans active network connections.</li>
    <li>Relevant external connections are filtered and processed.</li>
    <li>New remote IPs are geolocated and cached.</li>
    <li>Process information for each connection is collected.</li>
    <li>The data is sent to the browser interface in real time.</li>
    <li>The UI updates the globe, list, toolbox, and statistics automatically.</li>
  </ol>

  <h2>Key features</h2>
  <ul>
    <li>Runs locally without relying on a cloud platform</li>
    <li>Focus on real-time visual network transparency</li>
    <li>Assigns live connections to specific applications</li>
    <li>Adapter-based filtering for targeted network interface analysis</li>
    <li>Combines monitoring, geolocation, and 3D visualization</li>
  </ul>

  <h2>Possible use cases</h2>
  <ul>
    <li>Analyze which programs are creating internet connections</li>
    <li>Visualize external destinations and connection paths</li>
    <li>Monitor network activity on a local computer</li>
    <li>Demonstrate traffic patterns for security, networking, or admin use</li>
  </ul>

  <h2>Note</h2>
  <p>
    The application is designed for live monitoring and visualization. The
    accuracy of geolocation data depends on the IP geolocation service in use.
    Some process names or executable paths may be limited by operating system
    permissions.
  </p>
</body>
</html>
