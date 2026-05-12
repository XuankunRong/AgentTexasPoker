# Script Layout

Model-specific wrappers live under `scripts/<model>/` and only set `CONFIG_PATH`.
They do not contain API keys.

Examples:

```bash
export SORUXGPT_API_KEY_CLAUDE='your-key'
RUN_NAME='run_6claude_10bb' MAX_HANDS=500 ./scripts/claude/run_simulation_6claude_10bb.sh
```

```bash
export QWEN_API_KEY='your-key'
RUN_NAME='run_6qwen_10bb' MAX_HANDS=500 ./scripts/qwen/run_simulation_6qwen_10bb.sh
```

```bash
export SORUXGPT_API_KEY_CLAUDE='your-key'
export SORUXGPT_API_KEY_GEMINI='your-key'
export SORUXGPT_API_KEY_DEEPSEEK='your-key'
export SORUXGPT_API_KEY_GPT='your-key'
export QWEN_API_KEY='your-key'
export XIAOMI_API_KEY='your-key'
RUN_NAME='run_6mixed_10bb' MAX_HANDS=500 ./scripts/mixed/run_simulation_6mixed_10bb.sh
```

To resume a run:

```bash
export RESUME_RUN_DIR='/absolute/path/to/existing/run'
MAX_HANDS=500 ./scripts/<model>/run_simulation_<config>.sh
```
