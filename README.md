# AgentTexasPoker

Code for our LLM-agent Texas hold'em experiments.

This repository contains the simulation environment, model configs, and run scripts used for the experiments in the paper.

## Requirements

- Python 3.10+
- API access for the models you want to run

## Repository Structure

```text
AgentTexasPoker/
├── configs/          # experiment configs
├── holdem/           # poker engine, agents, providers, analytics
├── scripts/          # run scripts
├── run_simulation.py # main simulator
├── run_dashboard.py  # local dashboard
└── README.md
```

## Experiments

The repository includes configs for:

- homogeneous self-play under different blind levels
- heterogeneous mixed tables
- asymmetric short-stack conditions

## Run

Example:

```bash
export SORUXGPT_API_KEY_GPT='your-key'
RUN_NAME='run_6gpt_10bb' MAX_HANDS=500 ./scripts/gpt/run_simulation_6gpt_10bb.sh
```

Mixed-table example:

```bash
export SORUXGPT_API_KEY_CLAUDE='your-key'
export SORUXGPT_API_KEY_DEEPSEEK='your-key'
export SORUXGPT_API_KEY_GEMINI='your-key'
export SORUXGPT_API_KEY_GPT='your-key'
export QWEN_API_KEY='your-key'
export XIAOMI_API_KEY='your-key'
RUN_NAME='run_6mixed_10bb' MAX_HANDS=500 ./scripts/mixed/run_simulation_6mixed_10bb.sh
```

## Resume

```bash
export RESUME_RUN_DIR='/absolute/path/to/existing/run'
MAX_HANDS=500 ./scripts/gpt/run_simulation_6gpt_10bb.sh
```

## Dashboard

```bash
./scripts/run_dashboard.sh
```

## Notes

- API keys are provided through environment variables.
- Outputs and plotting artifacts are not included in this public repository.
- This repository is intended as the code release accompanying the paper.
