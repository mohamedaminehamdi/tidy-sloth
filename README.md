# Tidy Sloth 🦥

Puts your Downloads and Desktop away by learning how **you** already file things. One click to approve, one click to undo. Runs on your Mac, never deletes anything.

**[Try the demo](https://mohamedaminehamdi.github.io/tidy-sloth/)** (made-up files, nothing real moves)

## Install

Paste this into Terminal once (Apple silicon, macOS 14+, no admin password):

```
curl -fsSL https://mohamedaminehamdi.github.io/tidy-sloth/install.sh | sh
```

It installs [uv](https://docs.astral.sh/uv/), Tidy Sloth, [Ollama](https://ollama.com) with Gemma 4 (about 6.6 GB, the bulk of the download), and the open TabPFN weights. Then it makes a **Tidy Sloth app** in your Applications folder. From then on it's one click: open the app, and the sloth looks through your Downloads and Desktop while you watch.

The installer also asks whether to build a plan every night at 3 am. It's off unless you say yes. A Mac that's asleep at 3 am builds the plan when it next wakes. The nightly run never moves anything; it only has the plan ready when you open the app.

Why a Terminal line and not a .dmg? macOS blocks downloaded apps that aren't notarized, and notarizing needs a paid Apple developer account. The app the installer makes is built on your own Mac, so there's nothing for Gatekeeper to block. [Read the script](install.sh) before you run it; it's short.

### Uninstall

```
tidy-sloth --uninstall && uv tool uninstall tidy-sloth
```

That removes the app, the nightly run and the program. Ollama and its models stay, since other apps may use them.

## Commands

```
tidy-sloth              # open the review screen (last night's plan if there is one, otherwise it looks now)
tidy-sloth --rescan     # ignore last night's plan and look again
tidy-sloth --overnight  # build the plan only
tidy-sloth --undo       # put the last tidy back
tidy-sloth --eval       # how well it re-files files you already filed
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
- **One change at a time.** A double-click on Approve, or a stale tab from an older plan, is refused instead of acted on.
- **Asks macOS first.** The first time the app opens, macOS asks whether Tidy Sloth may look in Desktop, Documents and Downloads. If you say no, it tells you how to allow it, instead of quietly planning nothing.

## Does it actually learn?

Held-out test on the author's real Desktop: 10 folders, files split 70/30, retrained on the 70%.

| | correct |
|---|---|
| Guess from the file extension | 28.9% |
| TabPFN | **98.6%** |
| TabPFN, only when ≥ 90% sure (93.8% of files) | **100%** |
| TabPFN without capture date and GPS | 45% |

Most of those folders are trips full of photos, so date and location do the heavy lifting. Documents are harder, which is why Gemma reads the ones TabPFN isn't sure about. Run `tidy-sloth --eval` to get your own numbers. It prints totals only.

## Develop

macOS (it uses Spotlight's `mdls` and `sips`), Python 3.12, [uv](https://docs.astral.sh/uv/).

```
git clone https://github.com/mohamedaminehamdi/tidy-sloth && cd tidy-sloth
ollama pull gemma4:e4b     # optional: for renaming; skip it and pass --no-gemma
uv run tidy-sloth
uv run pytest
```

No account, no API key, $0.

## Files

```
tidy_sloth/scan.py      what to look at, what to leave alone, Spotlight metadata
tidy_sloth/features.py  the table TabPFN reads
tidy_sloth/learn.py     TabPFN folder model + held-out evaluation
tidy_sloth/rename.py    Gemma 4 naming and document routing (Ollama)
tidy_sloth/plan.py      plan, apply with journal, undo
tidy_sloth/server.py    local review screen (opens at once; the plan builds in the background)
tidy_sloth/install.py   --setup: models, the Mac app, the optional nightly run
tidy_sloth/web/         the review screen and the sloth (also the GitHub Pages demo)
install.sh              the one-line installer
```

MIT licensed.
