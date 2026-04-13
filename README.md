<p align="center">
  <img src="https://raw.githubusercontent.com/NicolaiLassen/orxhestra-code/main/assets/logo_code_text_bottom.svg" width="400" alt="orxhestra-code logo">
</p>

<p align="center">
  <strong>AI coding agent for your terminal — reads, writes, edits code and runs commands.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/orxhestra-code/"><img src="https://img.shields.io/pypi/v/orxhestra-code" alt="PyPI"></a>
  <a href="https://pypi.org/project/orxhestra-code/"><img src="https://img.shields.io/pypi/pyversions/orxhestra-code" alt="Python"></a>
  <a href="https://github.com/NicolaiLassen/orxhestra-code/blob/main/LICENSE"><img src="https://img.shields.io/github/license/NicolaiLassen/orxhestra-code" alt="License"></a>
</p>

<br>

Powered by [orxhestra](https://github.com/NicolaiLassen/orxhestra). Works with **any LangChain-supported LLM provider**.

## Install

```bash
# Install with your preferred provider
pip install orxhestra-code[openai]       # GPT-5.4, o3, o4, etc.
pip install orxhestra-code[anthropic]    # Claude
pip install orxhestra-code[google]       # Gemini
pip install orxhestra-code[aws]          # Bedrock
pip install orxhestra-code[azure-ai]     # Azure OpenAI
pip install orxhestra-code[mistral]      # Mistral
pip install orxhestra-code[groq]         # Groq
pip install orxhestra-code[ollama]       # Ollama (local)
pip install orxhestra-code[deepseek]     # DeepSeek
pip install orxhestra-code[xai]          # xAI / Grok
pip install orxhestra-code[openrouter]   # OpenRouter (multi-provider)

# Or install all providers at once
pip install orxhestra-code[all]
```

Or with Homebrew:

```bash
brew tap NicolaiLassen/orxhestra
brew install orxhestra-code
```

Or from source:

```bash
git clone https://github.com/NicolaiLassen/orxhestra-code.git
cd orxhestra-code
uv sync
```

## Usage

```bash
# Start with default model (Claude Sonnet)
orx-coder

# Use any LangChain provider
orx-coder --model openai/gpt-5.4
orx-coder --model anthropic/claude-sonnet-4-6
orx-coder --model google/gemini-2.5-pro
orx-coder --model mistral/mistral-large-latest
orx-coder --model groq/llama-3.3-70b-versatile
orx-coder --model ollama/qwen2.5-coder:32b
orx-coder --model deepseek/deepseek-chat
orx-coder --model xai/grok-3

# Control LLM reasoning effort
orx-coder --effort low      # fast responses, 5 iterations max
orx-coder --effort medium   # balanced reasoning, 15 iterations max
orx-coder --effort high     # deep reasoning, 30 iterations max (default)

# Permission modes
orx-coder --permission-mode plan           # read-only analysis
orx-coder --permission-mode accept-edits   # auto-approve edits, prompt for shell
orx-coder --auto-approve                   # skip all approval prompts
orx-coder --permission-mode trust          # full autonomous mode

# Resume previous sessions
orx-coder --continue             # continue most recent session
orx-coder --resume SESSION_ID   # resume a specific session

# Work in a specific directory
orx-coder --workspace /path/to/project

# Pipe a command
echo "fix the failing tests" | orx-coder
```

## Tools

The agent has access to these built-in tools:

`web_search` and `web_fetch` do not require a separate search API key. They use open-web search/fetching locally inside the CLI.

### File Operations
- **ls** — List files and directories
- **read_file** — Read files with line numbers, offset/limit pagination, image support
- **write_file** — Create or overwrite files, auto-creates parent directories
- **edit_file** — Find-and-replace edits with diff output
- **mkdir** — Create directories
- **glob** — Fast file pattern matching (`**/*.py`, `src/*.ts`)
- **grep** — Search file contents with regex, context lines, glob filtering

### Shell
- **shell_exec** — Run shell commands (git, npm, pip, make, tests, etc.)

### Web
- **web_search** — Search the open web without an extra search API key
- **web_fetch** — Fetch a URL and extract readable content from the page

### Planning
- **enter_plan_mode** — Switch to read-only mode for codebase exploration. The agent reads files, searches, and analyzes before writing code.
- **exit_plan_mode** — Present an implementation plan for your approval. You can approve, reject, or request changes before the agent starts coding.

### Task Management
- **write_todos** — Create and update structured task lists. The agent breaks complex work into steps and tracks progress.

### Delegation
- **task** — Delegate a complex subtask to a fresh agent with isolated context. Useful for parallel research or exploratory work that would clutter the main conversation.

### Artifacts
- **save_artifact** — Save files or data to the artifact store
- **load_artifact** — Load a previously saved artifact
- **list_artifacts** — List all available artifacts

### User Interaction
- **human_input** — Ask you a clarifying question when the agent needs more information before proceeding

## Permission Modes

Control what the agent can do without prompting:

| Mode | Reads | Edits | Shell | Web | Use case |
|---|---|---|---|---|---|
| `default` | auto | prompt | prompt | prompt | Normal usage — you approve each destructive or external action |
| `plan` | auto | **deny** | **deny** | **deny** | Read-only exploration and analysis |
| `accept-edits` | auto | auto | prompt | prompt | Focused coding — edits are expected, shell/web need approval |
| `auto-approve` | auto | auto | auto | auto | Full speed — trust the agent completely |
| `trust` | auto | auto | auto | auto | Like auto-approve with no warnings |

Switch mid-session:

```
/permissions plan           # switch to read-only
/permissions accept-edits   # auto-approve edits
/permissions cycle          # rotate to next mode
/permissions                # show current mode
```

When a tool needs approval, you'll see:

```
  ? Allow: shell_exec: npm test
  [y/n/a(ll)] >
```

Type `y` to allow once, `n` to deny, or `a` to auto-approve all for the rest of the session.

## Plan Mode

For non-trivial tasks, the agent enters plan mode to explore and design before coding:

```
orx-coder> build a REST API for user management

  ┌ enter_plan_mode
  └ done
  ┌ glob(**/*.py), read_file(app/models.py), grep(def.*user, path=app/)
  └ done
  ┌ exit_plan_mode
  │ IMPLEMENTATION PLAN
  │ ============================================================
  │ 1. Create app/routers/users.py with CRUD endpoints
  │ 2. Add UserCreate/UserUpdate schemas to app/schemas.py
  │ 3. Add pagination to list endpoint
  │ ============================================================
  │
  │ ? Approve this plan? [y/n/e(dit)] >
```

- **y** — Approve and start implementing
- **n** — Reject, agent asks what you'd prefer
- **e** — Request changes, agent revises the plan

## Reasoning Effort

The `--effort` flag maps to each provider's native reasoning API:

| Provider | Parameter | What it does |
|---|---|---|
| Anthropic / AWS | `thinking.budget_tokens` | Extended thinking with token budget |
| OpenAI / Azure | `reasoning_effort` + Responses API | Internal reasoning depth |
| Google / Vertex | `thinking_level` | Gemini thinking depth |
| xAI | `reasoning_effort` | Grok reasoning depth |
| DeepSeek | `reasoning_effort` | DeepSeek reasoning depth |
| Mistral | `reasoning_effort` | Magistral reasoning depth |
| Groq | `reasoning_effort` | Groq reasoning depth |
| Cohere | `thinking.budget_tokens` | Command A reasoning budget |

## REPL Commands

| Command | Description |
|---|---|
| `/model <name>` | Switch model mid-session |
| `/permissions <mode>` | Switch permission mode |
| `/perm cycle` | Cycle to next permission mode |
| `/cost` | Show session token usage |
| `/diff` | Show uncommitted git changes (`/diff full` for syntax-highlighted diff) |
| `/compact` | Summarize history to free context (also auto-triggers at 80K chars) |
| `/todos` | Show task list |
| `/session` | Session info |
| `/undo` | Remove last turn |
| `/retry` | Re-run last message |
| `/copy` | Copy last response |
| `/memory` | Browse saved memories |
| `/theme` | Switch theme |
| `/clear` | Clear conversation |
| `/help` | Show all commands |
| `/exit` | Quit |

## Configuration

Create `~/.orx-coder/config.yaml` for persistent defaults:

```yaml
model: anthropic/claude-sonnet-4-6
effort: high
permission_mode: default
```

### Environment variables

| Variable | Description |
|---|---|
| `ORX_MODEL` | Override model (e.g. `openai/gpt-5.4`) |
| `ORX_EFFORT` | Override effort (`low`, `medium`, `high`) |
| `ORX_PERMISSION_MODE` | Override permission mode |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `GOOGLE_API_KEY` | Google AI API key |
| `GROQ_API_KEY` | Groq API key |
| `MISTRAL_API_KEY` | Mistral API key |
| `TOGETHER_API_KEY` | Together API key |
| `FIREWORKS_API_KEY` | Fireworks API key |

## Project Instructions

The agent loads instructions from multiple sources (closest files have highest priority):

| File | Scope | Description |
|---|---|---|
| `CLAUDE.md` | Project (shared) | Team-shared project rules, version controlled |
| `CLAUDE.local.md` | Project (personal) | Personal rules, gitignored |
| `.claude/CLAUDE.md` | Project | Alternative location |
| `.orx/instructions.md` | Project | Alternative location |
| `~/.claude/CLAUDE.md` | User | Global rules for all projects |
| `~/.orx-coder/CLAUDE.md` | User | Global rules for all projects |

Instructions support `@path/to/file` import directives for composing rules from multiple files. HTML comments are stripped to save tokens. Files are truncated at 50KB with a warning.

```markdown
# Project rules

- Use pytest for testing
- Follow PEP 8
- Always run tests before committing

@.claude/style-guide.md
```

## Session Persistence

Sessions are automatically saved to `~/.orx-coder/sessions.db` (SQLite). Context is auto-compacted when it exceeds 80K characters.

```bash
orx-coder -c                    # continue most recent session
orx-coder -r SESSION_ID         # resume specific session
```

## License

Apache-2.0
