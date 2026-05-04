import argparse
import json
import os
import sys
import traceback
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
SRC_DIR = CURRENT_FILE.parents[2]
BACKEND_DIR = CURRENT_FILE.parents[3]

sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(CURRENT_FILE.parent))

from services.media.audio_transcriber import transcribe_video


def main() -> int:
    parser = argparse.ArgumentParser(description="Run recovery transcription in isolated subprocess")
    parser.add_argument("--video", required=True)
    parser.add_argument("--language", default="auto")
    parser.add_argument("--model", default="base")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    try:
        phrase_timings, language = transcribe_video(
            args.video,
            language=args.language,
            model_name=args.model,
        )
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "phrase_timings": phrase_timings,
                    "language": language,
                },
                handle,
                indent=2,
                ensure_ascii=False,
            )
        return 0
    except Exception as error:
        traceback.print_exc()
        try:
            with open(args.output, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "error": str(error),
                    },
                    handle,
                    indent=2,
                    ensure_ascii=False,
                )
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
