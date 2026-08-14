---
name: llm-finetuning-patterns
description: Use when planning or reviewing LLM fine-tuning, LoRA, quantization-aware training, preference optimization, weight editing, ablation, or training efficiency.
---

# LLM Fine-tuning Patterns

Choose the smallest intervention that can measurably change the target behavior.

## Decision guide

- Use supervised fine-tuning for demonstrated task behavior and formatting.
- Use preference or reward optimization only when preference data and evaluation are reliable.
- Use LoRA when adapter portability and limited trainable parameters matter.
- Use quantization-aware methods when the deployed precision differs materially from training.
- Use directional ablation or weight editing for narrow, experimentally testable behavior changes.

## Experimental contract

Define the baseline, target metric, held-out sets, safety regressions, compute budget, precision, seed policy, and stopping criteria before training. Keep training and evaluation data separated by source and semantic near-duplicate checks.

## Efficiency

Profile memory per layer, optimizer state, activations, sequence length, and adapter rank. Fused kernels and runtime patching are optimizations only after correctness equivalence is tested.

## Release evidence

Publish configuration, data provenance, exact base revision, evaluation code, confidence intervals, known regressions, and hardware/software environment.

Source briefs: [LLM fine-tuning and research](../../knowledge/llm-finetuning-and-research/).
