# Contributing to Buddy

Thanks for helping! Bug reports, ideas and pull requests are all welcome.

## Reporting a bug or asking for a feature

Open an [issue](https://github.com/ShashwatkumarXD/buddy/issues). For bugs, include your OS,
the Pokémon you use, and the last lines of Buddy's log (paths are in the README's
Troubleshooting section).

## Sending a pull request

1. Fork the repo and create a branch from `main`.
2. Set up a dev copy: `./install.sh` from your clone (Windows:
   `powershell -ExecutionPolicy Bypass -File install.ps1`). This makes an editable install with
   the test tools in `.venv`.
3. Make your change and add or update tests in `tests/`.
4. Run the tests: `.venv/bin/pytest -q`
5. Open a pull request against `main` and describe what changed and why.

Every pull request is tested on Windows, macOS and Linux, and is reviewed before it's merged.
For a first-time contributor, the tests start once a maintainer approves them to run.

## Ground rules

- **No Pokémon sprites in the repo.** Sprites are downloaded on the user's computer when they
  choose a Pokémon. Please don't commit sprite images or game assets.
- Keep changes focused: one fix or feature per pull request.
- By contributing, you agree that your contribution is licensed under the [MIT License](LICENSE).
