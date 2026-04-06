# orxhestra-code

AI coding agent for your terminal. Reads, writes, edits code and runs commands — powered by [orxhestra](https://github.com/NicolaiLassen/orxhestra).

Works with **any LangChain-supported LLM provider**.

## Install

```bash
uv pip install orxhestra-code
```

Then install the provider for your model:

```bash
# Pick one (or more)
uv pip install langchain-anthropic    # Claude
uv pip install langchain-openai       # GPT-4o, o1, etc.
uv pip install langchain-google-genai # Gemini
uv pip install langchain-aws          # Bedrock
uv pip install langchain-mistralai    # Mistral
uv pip install langchain-groq         # Groq
uv pip install langchain-ollama       # Ollama (local)
uv pip install langchain-fireworks    # Fireworks
uv pip install langchain-together     # Together
uv pip install langchain-cohere       # Cohere
uv pip install langchain-deepseek     # DeepSeek
uv pip install langchain-xai          # xAI / Grok
uv pip install langchain-openrouter   # OpenRouter (multi-provider)
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
orx-coder --model anthropic/claude-sonnet-4-6
orx-coder --model openai/gpt-4o
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

# Set max tokens per response
orx-coder --max-tokens 32768

# Work in a specific directory
orx-coder --workspace /path/to/project

# Pipe a command
echo "fix the failing tests" | orx-coder
```

## What it can do

- **Read** files, search with glob/grep
- **Write** and **edit** files (sends diffs, not full rewrites)
- **Run** shell commands (build, test, git, etc.)
- **Remember** things across sessions (project context, preferences)
- **Track tasks** with a structured todo list
- **Git** workflow (commit, branch, PR creation)

## Configuration

Create `~/.orx-coder/config.yaml` for persistent defaults:

```yaml
model: anthropic/claude-sonnet-4-6
effort: high
max_tokens: 16384
auto_approve_reads: true
```

### Environment variables

| Variable | Description |
|---|---|
| `ORX_MODEL` | Override model (e.g. `openai/gpt-4o`) |
| `ORX_EFFORT` | Override effort (`low`, `medium`, `high`) |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `GOOGLE_API_KEY` | Google AI API key |
| `GROQ_API_KEY` | Groq API key |
| `MISTRAL_API_KEY` | Mistral API key |
| `TOGETHER_API_KEY` | Together API key |
| `FIREWORKS_API_KEY` | Fireworks API key |

## Project instructions

Create a `CLAUDE.md` (or `.orx/instructions.md`) in your project root with project-specific instructions. The agent loads these automatically.

```markdown
# Project rules

- Use pytest for testing
- Follow PEP 8
- Always run tests before committing
```

Instructions are loaded from the current directory up to the filesystem root, so you can have global instructions in `~/CLAUDE.md` and project-specific ones in your repo.

## REPL commands

| Command | Description |
|---|---|
| `/model <name>` | Switch model |
| `/clear` | Clear conversation |
| `/compact` | Summarize history to free context |
| `/todos` | Show task list |
| `/memory` | Browse saved memories |
| `/help` | Show all commands |
| `/exit` | Quit |

## License

Apache-2.0
