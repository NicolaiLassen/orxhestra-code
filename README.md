# orxhestra-code

AI coding agent for your terminal. Reads, writes, edits code and runs commands — powered by [orxhestra](https://github.com/NicolaiLassen/orxhestra).

Works with **any LangChain-supported LLM provider**.

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

## What it can do

- **Read** files, search with glob/grep
- **Write** and **edit** files (sends diffs, not full rewrites)
- **Run** shell commands (build, test, git, etc.)
- **Plan** complex tasks before implementing (enter/exit plan mode with user approval)
- **Track tasks** with a structured todo list
- **Git** workflow (structured commit protocol, PR creation with `gh`)
- **Persist sessions** to disk (SQLite) and resume later
- **Delegate** subtasks to isolated sub-agents

## Permission modes

| Mode | Behavior |
|---|---|
| `default` | Prompt for destructive tools (writes, edits, shell) |
| `plan` | Read-only — explore and analyze, cannot modify anything |
| `accept-edits` | Auto-approve file operations, prompt for shell |
| `auto-approve` | Auto-approve everything, no prompts |
| `trust` | Full autonomous mode, no prompts or warnings |

Switch modes mid-session with `/permissions`:

```
/permissions plan           # switch to read-only
/permissions accept-edits   # auto-approve edits
/permissions cycle          # rotate to next mode
/permissions                # show current mode
```

## Plan mode

For non-trivial tasks, the agent can enter plan mode to explore the codebase and design an approach before writing code:

1. Agent calls `enter_plan_mode` (switches to read-only)
2. Agent reads files, searches, analyzes the codebase
3. Agent calls `exit_plan_mode` with an implementation plan
4. **You approve, reject, or request changes** to the plan
5. On approval, permissions restore and the agent implements

## Reasoning effort

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

## Project instructions

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

## REPL commands

| Command | Description |
|---|---|
| `/model <name>` | Switch model |
| `/permissions <mode>` | Switch permission mode |
| `/perm cycle` | Cycle to next permission mode |
| `/clear` | Clear conversation |
| `/compact` | Summarize history to free context |
| `/todos` | Show task list |
| `/session` | Session info |
| `/undo` | Remove last turn |
| `/retry` | Re-run last message |
| `/copy` | Copy last response |
| `/memory` | Browse saved memories |
| `/theme` | Switch theme |
| `/help` | Show all commands |
| `/exit` | Quit |

## Session persistence

Sessions are automatically saved to `~/.orx-coder/sessions.db` (SQLite). Resume previous sessions:

```bash
orx-coder -c                    # continue most recent session
orx-coder -r SESSION_ID         # resume specific session
```

## License

Apache-2.0
