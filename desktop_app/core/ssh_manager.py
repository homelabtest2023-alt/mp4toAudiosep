"""
ssh_manager.py — Manages an SSH connection to the remote GPU server.

Allows the desktop app to:
  - Connect to the Ubuntu server via SSH (password or key-based auth)
  - Start/Stop the AudioSep lan_server.py remotely
  - Check if the API is already running
"""
import paramiko
import time


class SSHManager:
    def __init__(self):
        self.client: paramiko.SSHClient | None = None
        self.connected = False

        # Connection settings (set via GUI)
        self.host = ""
        self.port = 22
        self.username = ""
        self.password = ""
        self.key_path = ""              # Path to an SSH private key file (optional)
        self.server_script_path = ""    # e.g., /home/user/audiosep/lan_server.py
        self.python_path = "python3"    # Python executable on the remote machine
        self.api_port = 8001            # The port lan_server.py listens on

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------
    def connect(self) -> str:
        """Establish an SSH connection. Returns a status message."""
        if self.connected and self.client:
            self.disconnect()

        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            kwargs = {
                "hostname": self.host,
                "port": self.port,
                "username": self.username,
                "timeout": 10,
            }
            # Prefer key-based auth if a key path is provided
            if self.key_path:
                kwargs["key_filename"] = self.key_path
            elif self.password:
                kwargs["password"] = self.password

            self.client.connect(**kwargs)
            self.connected = True
            return f"Connected to {self.host}:{self.port} as {self.username}"

        except paramiko.AuthenticationException:
            self.connected = False
            raise Exception("SSH authentication failed. Check username/password or key file.")
        except paramiko.SSHException as e:
            self.connected = False
            raise Exception(f"SSH error: {str(e)}")
        except Exception as e:
            self.connected = False
            raise Exception(f"Cannot connect to {self.host}:{self.port} — {str(e)}")

    def disconnect(self):
        """Close the SSH connection."""
        if self.client:
            self.client.close()
        self.client = None
        self.connected = False

    # ------------------------------------------------------------------
    # Remote commands
    # ------------------------------------------------------------------
    def _exec(self, command: str, timeout: int = 10) -> str:
        """Execute a command on the remote server and return combined stdout+stderr."""
        if not self.connected or not self.client:
            raise Exception("Not connected. Please connect via SSH first.")

        _, stdout, stderr = self.client.exec_command(command, timeout=timeout)
        out = stdout.read().decode(errors="replace").strip()
        err = stderr.read().decode(errors="replace").strip()
        return out if out else err

    def _ensure_connected(self):
        """Auto-connect if not already connected. Raises on failure."""
        if not self.connected or not self.client:
            self.connect()

    def start_server(self) -> str:
        """
        Start lan_server.py on the remote server using nohup so it
        persists after the SSH session ends. Returns a status message.
        """
        if not self.server_script_path:
            raise Exception("Server script path is not configured. Set it in SSH Settings.")

        # FIX: Auto-connect before running any remote command
        self._ensure_connected()

        # First check if the server is already running
        if self._is_port_in_use():
            return f"AudioSep API is already running on port {self.api_port}."

        # Build the remote startup command
        # cd into the script's directory, then run with nohup
        # FIX: Guard against empty script_dir (e.g. path = /lan_server.py)
        normalized = self.server_script_path.replace("\\", "/")
        parts = normalized.rsplit("/", 1)
        script_dir = parts[0] if len(parts) > 1 and parts[0] else "/"
        script_name = parts[-1]

        cmd = (
            f"cd {script_dir} && "
            f"nohup {self.python_path} -u {script_name} "
            f"> /tmp/audiosep_server.log 2>&1 &"
        )

        self._exec(cmd, timeout=5)
        # Give the server a moment to start
        time.sleep(2)

        if self._is_port_in_use():
            return f"AudioSep API started successfully on port {self.api_port}!"
        else:
            log = self._exec("tail -20 /tmp/audiosep_server.log", timeout=5)
            return f"Server process launched but port {self.api_port} is not open yet.\nLog:\n{log}"

    def stop_server(self) -> str:
        """Kill the AudioSep API process on the remote server."""
        # FIX: Auto-connect before running any remote command
        self._ensure_connected()
        # FIX: Use lsof instead of fuser — fuser may not be installed on minimal Ubuntu
        self._exec(
            f"kill $(lsof -t -i:{self.api_port}) 2>/dev/null || "
            f"kill $(ss -tlnp | grep ':{self.api_port}' | awk '{{print $NF}}' | grep -oP 'pid=\\K[0-9]+') 2>/dev/null || true",
            timeout=5
        )
        time.sleep(1)

        if not self._is_port_in_use():
            return "AudioSep API stopped successfully."
        else:
            return "Warning: the API process may still be running."

    def check_status(self) -> str:
        """Check whether the AudioSep API is running on the remote server."""
        # FIX: Auto-connect before running any remote command
        self._ensure_connected()
        if self._is_port_in_use():
            return f"🟢 AudioSep API is running on port {self.api_port}."
        else:
            return f"🔴 AudioSep API is NOT running on port {self.api_port}."

    def get_server_log(self) -> str:
        """Retrieve the last 30 lines of the server log."""
        self._ensure_connected()
        return self._exec("tail -30 /tmp/audiosep_server.log", timeout=5)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _is_port_in_use(self) -> bool:
        """Check if the API port is currently in use on the remote machine."""
        result = self._exec(f"ss -tlnp | grep :{self.api_port}", timeout=5)
        return bool(result)
