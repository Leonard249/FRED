# Testing for model ram usage

## Reasoning model

1. Qwen3-8B-4bit-DWQ-053125 -> 4.726 gb

## VLM

1. Qwen3-VL-4B-Instruct-3bit -> 1.889 gb
2. Qwen3-VL-4B-Instruct-8bit -> 4.400 gb
3. Qwen3-VL-4B-Instruct-5bit -> 2.893 gb
4.

## coding model

1. Qwen2.5-Coder-3B-Instruct-8bit -> 3.4 gb

# Finalised models (for now)

## Reasoning model: Qwen3-8B-4bit-DWQ-053125 (4.61 gb)

- max_position_embeddings (context window): 40960
- sliding_window (save memory on long contexts): None
- rope_scaling (Rotary Position Embeddings to extend context window): None
- vocab_size: 151936

## Vision model: Qwen3-VL-4B-Instruct-5bit ()

## Coding model: Qwen2.5-Coder-3B-Instruct-8bit
