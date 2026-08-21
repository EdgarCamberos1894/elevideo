import subprocess
import tempfile
from typing import Callable, Iterable, Optional


ProgressCallback = Optional[Callable[[float], None]]


def run_ffmpeg_with_progress(
    cmd: Iterable[str],
    duration_seconds: Optional[float] = None,
    on_progress: ProgressCallback = None,
) -> subprocess.CompletedProcess:
    """
    Ejecuta FFmpeg leyendo su protocolo machine-readable `-progress`.

    El callback recibe una fracción 0..1 basada en out_time_us / duración del
    contenido. stderr se guarda en un archivo temporal para evitar deadlocks y
    conservar diagnósticos completos si FFmpeg falla.
    """
    command = list(cmd)
    if not command:
        raise ValueError("Comando FFmpeg vacío")

    # En los comandos de EleVideo el último argumento es siempre el output.
    # -progress es una opción global y se coloca antes de ese output.
    if "-progress" not in command:
        output = command[-1]
        command = command[:-1] + ["-progress", "pipe:1", "-nostats", output]

    last_fraction = -1.0
    stdout_lines = []

    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stderr_file:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=stderr_file,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            stdout_lines.append(line)

            key, sep, value = line.partition("=")
            if not sep:
                continue

            fraction = None
            if key == "out_time_us" and duration_seconds and duration_seconds > 0:
                try:
                    seconds = max(0.0, float(value) / 1_000_000.0)
                    fraction = seconds / duration_seconds
                except (TypeError, ValueError):
                    fraction = None
            elif key == "out_time" and duration_seconds and duration_seconds > 0:
                seconds = _parse_ffmpeg_time(value)
                if seconds is not None:
                    fraction = seconds / duration_seconds
            elif key == "progress" and value == "end":
                fraction = 1.0

            if fraction is not None and on_progress:
                fraction = max(0.0, min(1.0, fraction))
                # Evita callbacks excesivos sin sacrificar sensación de fluidez.
                if fraction >= 1.0 or fraction - last_fraction >= 0.005:
                    last_fraction = fraction
                    on_progress(fraction)

        return_code = process.wait()
        stderr_file.seek(0)
        stderr = stderr_file.read()

    stdout = "\n".join(stdout_lines)
    if return_code != 0:
        raise subprocess.CalledProcessError(
            return_code,
            command,
            output=stdout,
            stderr=stderr,
        )

    if on_progress and last_fraction < 1.0:
        on_progress(1.0)

    return subprocess.CompletedProcess(command, return_code, stdout=stdout, stderr=stderr)


def probe_duration_seconds(path: str) -> Optional[float]:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        duration = float(result.stdout.strip())
        return duration if duration > 0 else None
    except Exception:
        return None


def _parse_ffmpeg_time(value: str) -> Optional[float]:
    try:
        hours, minutes, seconds = value.split(":", 2)
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except (ValueError, TypeError):
        return None
