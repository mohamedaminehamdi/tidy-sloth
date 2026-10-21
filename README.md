# Tidy Sloth 🦥

Puts your Downloads and Desktop away by learning how **you** already file things. One click to approve, one click to undo. Runs on your Mac, never deletes anything.

**[Try the demo](https://mohamedaminehamdi.github.io/tidy-sloth/)** (made-up files, nothing real moves)

```
uv run tidy-sloth              # scan, plan, open the review screen
uv run tidy-sloth --overnight  # build the plan slowly while you sleep; review it with --review
uv run tidy-sloth --undo       # put the last tidy back
uv run tidy-sloth --eval       # how well it re-files files you already filed
```

## How it works

1. **Learns your filing system with [TabPFN](https://github.com/PriorLabs/TabPFN).** Every file already sitting in one of your folders is a labelled example. Tidy Sloth turns each into a row: extension, size, capture date, photo GPS, the site it was downloaded from (macOS Spotlight already knows), and a few numbers describing the filename. TabPFN fits that table in one forward pass. There is no training run and nothing to configure. Then it says where each loose file belongs, and how sure it is.
2. **Names the junk with Gemma 4, locally.** `IMG_4821.HEIC`, `Screenshot 2026-10-19 at 09.12.44.png` and `document (3).pdf` go to Gemma 4 through [Ollama](https://ollama.com), along with a small preview or the first page of text. A name you chose yourself is never touched. Gemma also gets a say on documents TabPFN isn't sure about.
3. **Shows you the plan.** Files grouped by destination, with editable names and a tick box each. If several files of one kind have no home (four ebooks, say), it suggests a new folder. Anything it isn't sure about stays where it is.

## Safety

- **Moves and renames only.** There is no delete code path.
- **Never touches secrets.** `.pem`, `.key`, `id_rsa`, `.env`, wallets, and anything named like a password or recovery code are listed but never moved.
- **Never touches** hidden files, app bundles, code projects (anything with `.git`, `package.json`, `pyproject.toml`…), or files changed in the last 10 minutes.
- **Never overwrites.** A name clash becomes `name (2).ext`.
- **Undo.** Every move is written to a journal in `~/.tidy-sloth/` *before* it happens, so even a crash can be undone.
- **Stays on this machine.** The review screen is served on `127.0.0.1` only, and requests from other hosts or origins are refused. Your files and filenames never leave your Mac: both models run locally.

## Does it actually learn?

Held-out test on the author's real Desktop: 10 folders, files split 70/30, retrained on the 70%.

| | correct |
|---|---|
| Guess from the file extension | 28.9% |
| TabPFN | **98.6%** |
| TabPFN, only when ≥ 90% sure (93.8% of files) | **100%** |
| TabPFN without capture date and GPS | 45% |

Most of those folders are trips full of photos, so date and location do the heavy lifting. Documents are harder, which is why Gemma reads the ones TabPFN isn't sure about. Run `tidy-sloth --eval` to get your own numbers. It prints totals only.

## Install

macOS (it uses Spotlight's `mdls` and `sips`), Python 3.12, [uv](https://docs.astral.sh/uv/).

```
git clone https://github.com/mohamedaminehamdi/tidy-sloth && cd tidy-sloth
ollama pull gemma4:e4b     # optional: for renaming; skip it and pass --no-gemma
uv run tidy-sloth
```

The first run downloads the open TabPFN v2 weights. No account, no API key, $0.

## Files

```
tidy_sloth/scan.py      what to look at, what to leave alone, Spotlight metadata
tidy_sloth/features.py  the table TabPFN reads
tidy_sloth/learn.py     TabPFN folder model + held-out evaluation
tidy_sloth/rename.py    Gemma 4 naming and document routing (Ollama)
tidy_sloth/plan.py      plan, apply with journal, undo
tidy_sloth/server.py    local review screen
web/                    the review screen (also the GitHub Pages demo)
```

MIT licensed.
