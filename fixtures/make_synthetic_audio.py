"""Create the valid synthetic silent WAV referenced by manifest.jsonl."""
import wave
from pathlib import Path

path = Path(__file__).with_name("synthetic.wav")
with wave.open(str(path), "wb") as wav:
    wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
    wav.writeframes(b"\x00\x00" * 1600)
print(path)
