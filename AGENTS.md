# AGENTS.md

This file tells a coding agent how this repository is organized and how to set
up `sbx` for a user. Read it before you act.

`sbx` makes throwaway Proxmox VMs ("sandboxes") for development. Each user has
their own Proxmox host, their own Mac (or Linux machine), and their own
Tailscale tailnet. Nothing in this repository connects to another person's
host. Each agent sandbox has a sidecar VM that holds its tokens; the diagrams
in `README.md` and `docs/architecture.md` show how the parts connect.

## Where to look

| Question | Read |
|---|---|
| What sbx is, and a map of the docs | `README.md` |
| The whole path, from setup to an agent sandbox with Remote Control, a preview and no expiry | `docs/getting-started.md` |
| The setup, step by step, with a check for each step | `docs/setup.md` |
| Daily use: profiles, sandboxes, ports, Claude, snapshots | `docs/usage.md` |
| A project's recipe, manifest and pane layout (`.sandbox/`) | `docs/projects.md` |
| Templates: which exist, and how to make or change one | `docs/templates.md` |
| What an agent sandbox can reach, and why | `docs/security.md` |
| A symptom and its fix | `docs/troubleshooting.md` |
| Every command, setting and file | `docs/reference.md` |
| How each mechanism works, the traps, the tests | `docs/architecture.md` |
| The values that one setup chooses | `host/local.conf.example` |
| A start point for a Rails project | `examples/rails/.sandbox/` |
| The usage on one screen | `sbx guide` |
| The web portal: its routes, jobs and locks | `sbxlib/portal/`, `docs/architecture.md` |

## The parts

| Path | Runs on | Purpose |
|---|---|---|
| `bin/sbx`, `sbxlib/` | the Mac | the CLI (Python 3.11 or later, no dependencies) |
| `sbxlib/hostsetup.py` | the Mac | `sbx setup`: reads the host, writes `host/local.conf`, runs the host scripts |
| `sbxlib/doctor.py` | the Mac | `sbx doctor`: the checks of `docs/setup.md` |
| `host/` | the Proxmox host, as root | the bridges, the gateway, the templates (the sidecar template too), the API token |
| `gw/` | the gateway container | dnsmasq, the nftables guard, Tailscale |
| `sidecar/` | the sidecar VM of each agent sandbox | the credential proxy, the expose API, nftables, the cloudflared unit |
| `template/` | the template VMs | the core build (`provision.sh`) and the components (`template/components/`) |
| `templates/` | the Mac and the host | the template definitions; `templates/local/` is the user's own, not in git |
| `sbxlib/templates.py` | the Mac and the host | reads a definition; the host runs it during a build |
| `tailscale/` | the Tailscale admin console | the policy fragment |

The settings come from three layers, lowest first:

1. `host/defaults.conf`: the shared defaults, in git.
2. `host/local.conf`: the values of this setup. It is NOT in git.
3. `~/.config/sbx/config.toml`: the Mac's own settings (API address, token command).

The host scripts and the CLI read the first two layers, so they always agree.
A shared key (the domain, the bridges, the subnets, the IDs) belongs in
`host/local.conf` only. The CLI refuses a `config.toml` that disagrees with it.

## Rules for an agent

- **Do not read or print a secret.** The Proxmox token, the git tokens, the
  Claude token and the Cloudflare token live in the macOS keychain, or off
  macOS in `~/.config/sbx/secrets/`. `~/.config/sbx/config.toml` names
  commands that print them. Do not run those commands, and do not read the
  keychain items or the files in `~/.config/sbx/secrets/`.
- **Never stop, restart or remove a VM that the user did not name.** Before a
  change that touches a sandbox the user works in, offer a snapshot of it and
  its sidecar with `sbx snap <name> <label> --ram`; both keep running.
- **Do not commit `host/local.conf`.** It holds the user's own values.
- **Ask before a command that changes the host or makes VMs.** These commands
  change real infrastructure:
  - `sbx setup` without `--local-only` (it changes the host network and builds VMs)
  - `sbx template rebuild`, `rm`, `prune` and `adopt` (they build or remove template VMs)
  - `sbx doctor --isolation` (it makes one sandbox per profile, three VMs
    with the agent's sidecar, and removes them)
  - `sbx new`, `sbx rm`, `sbx gc`, `sbx rollback`, `sbx snap`
  - `sbx publish <name> <port>` (a public hostname behind Cloudflare Access),
    `sbx autostart`, `sbx extend`, `sbx gpu attach|detach`
  - `sbx remote-control` (it puts a full claude.ai login in a sandbox;
    `--allow-agent` puts one in an agent sandbox, where the agent can read it)
  - `sbx import-ca` (it adds a CA to this machine's trust stores, with `sudo`; `--upload` writes the CA
    certificate, not its key, into 1Password)
  - `sbx claude-token` without `--status` (it writes into every running sandbox)
- **These commands are safe to run at any time:** `sbx doctor`, `sbx guide`,
  `sbx list`, `sbx projects`, `sbx inputs <project>`, `sbx versions`,
  `sbx template list`, `sbx template show`, `sbx template components`,
  `sbx template export`, the listing forms `sbx publish <name>`,
  `sbx autostart <name> --status`, `sbx remote-control <name> --status` and
  `sbx claude-token --status`, and the unit tests.
- **The portal (`sbx web`) follows the same rules.** Do not use its API to
  make, change or remove a VM without the user's consent. Do not read the
  portal link in `~/.config/sbx/portal/url`: it holds the session token.
- **`sbx template import` writes component scripts that run as root in a
  template build.** Show the user each script, and let the user answer the
  prompt. Do not pass `-y` for a file from someone else.

## How to set up sbx for a user

`sbx setup` needs the root password of the Proxmox host, and it stops at steps
in the Tailscale admin console. An agent cannot type a password, and it has no
terminal for SSH to ask in. So the USER runs `sbx setup` in their own
terminal. The agent prepares, explains, and checks.

1. **Check the prerequisites on the Mac.** Report what is missing:
   - `python3 --version` prints 3.11 or later.
   - `ssh` and `scp` exist.
   - The Tailscale app is installed and signed in (`tailscale status`, or
     `/Applications/Tailscale.app/Contents/MacOS/Tailscale status`).
   - On Linux instead of a Mac: `docs/setup.md`, "A Linux machine instead of
     a Mac" (accept the subnet routes; the secrets are files).
   - Optional: `mkcert` (https in each sandbox), `herdr` (the sidebar) and
     `op`, the 1Password CLI (it lets `sbx setup` keep the sandbox key in
     1Password).
2. **Ask the user** for these facts:
   - Is this a new host, or a host that another Mac set up already?
   - The address of the Proxmox host.
   - Are they an admin of their tailnet? A new host needs a policy change.
3. **Put `sbx` on the PATH** (ask first; it writes outside the repository):

   ```
   ln -s "$PWD/bin/sbx" "$(brew --prefix 2>/dev/null || echo /usr/local)/bin/sbx"
   ```

4. **Tell the user which command to run in their own terminal:**
   - A new host: `sbx setup`. It takes about 30 to 50 minutes, because it
     builds a template, and then the `sidecar` template that every agent
     sandbox needs. Ask the user which kinds of projects they work on, and
     suggest the matching templates (`sbx template list` shows them).
   - A host that is set up already: `sbx setup --local-only`. It does not change
     the host.

   Before a new-host setup, tell the user what the wizard does:
   - It proposes free bridges, subnets and VM IDs, and they accept or edit them.
   - It changes `/etc/network/interfaces` on the host, and asks first.
   - It shows a Tailscale policy fragment to MERGE into their policy, not to
     paste over it.
   - It asks them to add a split-DNS nameserver in the Tailscale admin console.
5. **Run `sbx doctor`** after the setup, and explain each `FAIL` and `WARN`.
   Each line names the next step. `docs/troubleshooting.md` covers the rest.
6. **Offer `sbx doctor --isolation`.** It proves that an agent sandbox cannot
   reach the LAN or the tailnet. It makes two VMs, so ask first.

`sbx setup` is safe to run again. A step whose check passes is skipped, and a
host with an existing gateway keeps its values.

## How to set up a project

1. Copy `examples/rails/.sandbox/` to the root of the project, or write a
   recipe from `docs/projects.md`. Edit `sandbox.toml` to list the inputs that
   the project really needs.
2. Run `sbx inputs <checkout>`. It shows each input and where its value comes
   from, and it makes nothing.
3. For an `agent` sandbox of a private repository, the user runs
   `sbx git-token <checkout or git URL>` and pastes a fine-grained token at
   the hidden prompt. Do not handle the token yourself. With a URL, no
   checkout is needed on the Mac: `sbx new --project <URL>` reads the
   recipe with that token.
4. With the user's consent: `sbx new <name> --project <checkout>`. An agent
   sandbox needs `--with <input>` or `--without <input>` for each input.
5. If the recipe fails, read `~/.local/state/sbx/recipe.log` in the sandbox:
   `sbx ssh <name> -- tail -n 50 .local/state/sbx/recipe.log`.

## How to give a user the template they need

1. Ask which languages and tools their projects use.
2. Run `sbx template list` and `sbx template components`. A shared
   definition often fits already.
3. If none fits, run `sbx template new <name> --from <closest>` and edit
   `templates/local/<name>.toml`. `docs/templates.md` lists every key.
4. A tool with no component needs a new file in
   `template/components/local/<name>.sh`. `docs/templates.md`, "Write your own
   component", has the rules.
5. The user runs `sbx template rebuild <name>` (it asks for the host's root
   password). Then set `default_template`, or `[recipe] template` in the
   project.
6. To give the template to a coworker: `sbx template export <name> -o <file>`.
   They run `sbx template import <file>`.

## When something fails

1. Run `sbx doctor`. Each line that fails names the next step.
2. Look up the symptom in `docs/troubleshooting.md`.
3. For a recipe, read `~/.local/state/sbx/recipe.log` in the sandbox.
4. To understand why a mechanism behaves as it does, read `docs/architecture.md`.

## How to work on this repository

- The unit tests need no dependencies:

  ```
  python3 -m unittest discover -s tests -t .
  ```

- Five behavior tests need Docker: `tests/run-guard-test.sh`,
  `tests/run-dns-test.sh`, `tests/run-mirror-test.sh`, `tests/run-finish-test.sh`,
  `tests/run-sidecar-test.sh`. Run the guard test after a change to
  `gw/nftables.conf.tmpl`, the DNS test after a change to
  `gw/dnsmasq.conf.tmpl`, and the sidecar test after a change under `sidecar/`.
- The diagrams in the docs are Mermaid. Check a changed one with the Mermaid
  CLI (`mmdc`) before a commit: GitHub shows a broken one as an error.
- A new key in `host/defaults.conf` that the CLI reads also needs a field in
  `sbxlib/config.py` and an entry in `_ENV_MAP`. A test keeps the two defaults
  equal.
- The tests ignore the user's `host/local.conf` and their own templates and
  components (`tests/__init__.py` sets `SBX_LOCAL_CONF` and
  `SBX_IGNORE_LOCAL_TEMPLATES`), so they give the same result on every setup.
- A change to a command, an option, or a setting also changes
  `docs/reference.md`. `tests/test_docs.py` fails until it does.
- Each topic has one home in `docs/`. Link to it; do not copy it.
- Keep the repository generic. No real host address, domain, user name, or
  project name belongs in a file. Use `192.168.1.10`, `sbx.internal` and
  `myapp` in examples.
