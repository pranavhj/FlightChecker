"""
Minimal claude CLI wrapper.
- Compacts session history when it grows large (keeps last KEEP_PAIRS exchanges).
- --print-file <path>: reads prompt from file and pipes via stdin to avoid
  newline-splitting issues on Windows.

Usage: python agent-smart.py [claude args...]
"""
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path

THRESHOLD_KB = 100
KEEP_PAIRS = 5


def _session_dir() -> Path:
    key = re.sub(r'[^a-zA-Z0-9]', '-', str(Path.cwd()))
    return Path.home() / '.claude' / 'projects' / key


def maybe_compact(keep_pairs: int = KEEP_PAIRS) -> None:
    session_dir = _session_dir()
    if not session_dir.is_dir():
        return
    files = list(session_dir.glob('*.jsonl'))
    if not files:
        return
    current = max(files, key=lambda p: p.stat().st_mtime)
    if current.stat().st_size // 1024 <= THRESHOLD_KB:
        return

    lines = current.read_text(encoding='utf-8', errors='replace').splitlines(keepends=True)
    msgs = [l for l in lines if json.loads(l.strip()).get('type') in ('user', 'assistant')]
    kept = msgs[-(keep_pairs * 2):]

    # Drop a leading orphaned tool_result block (its tool_use was cut off)
    while kept:
        first = json.loads(kept[0].strip())
        content = first.get('message', {}).get('content', [])
        if first.get('type') == 'user' and isinstance(content, list) and content and all(
            c.get('type') == 'tool_result' for c in content
        ):
            kept = kept[1:]
        else:
            break

    dst = session_dir / f'{uuid.uuid4()}.jsonl'
    dst.write_text(''.join(kept), encoding='utf-8')
    current.unlink()


def main():
    args = list(sys.argv[1:])
    maybe_compact()

    if '--print-file' in args:
        idx = args.index('--print-file')
        prompt = Path(args[idx + 1]).read_text(encoding='utf-8')
        args = args[:idx] + args[idx + 2:]
        subprocess.run(
            ['claude'] + args,
            input=prompt, text=True, encoding='utf-8',
            shell=sys.platform == 'win32',
        )
        return

    subprocess.run(['claude'] + args, shell=sys.platform == 'win32')


if __name__ == '__main__':
    main()
