import os
import subprocess
import shutil
import httpx
import tempfile
import uuid

class AudioProcessor:
    def __init__(self, server_url: str):
        self.server_url = server_url
        self.tmp_dir = tempfile.gettempdir()

    def _extract_wav(self, mp4_path: str, output_wav_path: str) -> bool:
        """
        Extracts 32kHz Mono WAV from MP4 using FFmpeg.
        Uses subprocess.run (synchronous) - safe to call inside a QThread.
        """
        # CREATE_NO_WINDOW prevents a flash console window on Windows (important for PyInstaller builds)
        creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

        command = [
            "ffmpeg", "-y", "-i", mp4_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", "32000", "-ac", "1",
            output_wav_path
        ]

        try:
            result = subprocess.run(
                command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags
            )
            return True
        except subprocess.CalledProcessError as e:
            stderr_msg = e.stderr.decode(errors='replace') if e.stderr else "No output"
            raise Exception(
                f"FFmpeg failed to extract audio.\nDetails: {stderr_msg}\n"
                "Please ensure FFmpeg is installed and in your system PATH."
            )
        except FileNotFoundError:
            raise Exception(
                "FFmpeg executable not found.\n"
                "Please install FFmpeg and ensure it is available in your system PATH."
            )

    async def _send_to_lan_server(self, wav_path: str, query: str, output_path: str) -> bool:
        """Sends the WAV and query to the LAN GPU server and saves the response."""
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                with open(wav_path, "rb") as audio_file:
                    files = {"file": (os.path.basename(wav_path), audio_file, "audio/wav")}
                    data = {"text": query}
                    response = await client.post(self.server_url, files=files, data=data)

                if response.status_code != 200:
                    raise Exception(
                        f"Server returned HTTP {response.status_code}.\n"
                        f"Details: {response.text}"
                    )

                # Save the separated audio returned by the server
                with open(output_path, "wb") as f:
                    f.write(response.content)

            return True

        except httpx.ConnectError:
            raise Exception(
                f"Cannot connect to the GPU server at:\n{self.server_url}\n\n"
                "Please check:\n"
                "  1. The GPU machine is powered on and running lan_server.py\n"
                "  2. The IP address is correct (Settings > Set LAN Server IP)\n"
                "  3. There is no firewall blocking the port"
            )
        except httpx.TimeoutException:
            raise Exception(
                f"The request to the GPU server timed out (after 300s).\n"
                "The server might be overloaded or the file might be too large."
            )
        except Exception as e:
            # Re-raise to preserve the original message if it was already formatted
            raise Exception(f"Communication Error: {str(e)}")

    async def process_audio(self, mp4_path: str, query: str, progress_callback=None) -> str:
        """
        Main pipeline: MP4 -> WAV -> LAN Server -> Separated WAV
        Returns the path to the separated WAV file.
        """
        job_id = str(uuid.uuid4())
        extracted_wav_path = os.path.join(self.tmp_dir, f"audiosep_extract_{job_id}.wav")
        separated_wav_path = os.path.join(self.tmp_dir, f"audiosep_result_{job_id}.wav")

        try:
            if progress_callback:
                progress_callback("Step 1/2: Extracting audio from video...")

            # FIX: Corrected from httpx.anyio.run_process to subprocess.run (synchronous,
            # perfectly safe inside a QThread). This was the main bug preventing FFmpeg from working.
            self._extract_wav(mp4_path, extracted_wav_path)

            if progress_callback:
                progress_callback("Step 2/2: Sending to GPU Server for separation (this may take a while)...")

            await self._send_to_lan_server(extracted_wav_path, query, separated_wav_path)

            if progress_callback:
                progress_callback("Done!")

            return separated_wav_path

        finally:
            # Always clean up the intermediate extracted WAV file
            if os.path.exists(extracted_wav_path):
                try:
                    os.remove(extracted_wav_path)
                except OSError:
                    pass  # Non-critical: temp file cleanup failure should not crash the app
