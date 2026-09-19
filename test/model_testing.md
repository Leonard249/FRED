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
- hidden_size (width of the network): 4096
- intermediate_size: 12288
- vocab_size: 151936
- num_attention_heads: 32
- num_key_value_heads: 8

## Vision model: Qwen3-VL-4B-Instruct-5bit (3.6 gb)

- max_position_embeddings (context window): 262144
- rope_scaling + mrope_section (To extend context window): [24,20,20]
- patch_size: 16
- spatial_merge_size: 2
- num_attention_heads: 32
- num_key_value_heads: 8

## Coding model: Qwen2.5-Coder-3B-Instruct-8bit (3.28 gb)

- max_position_embeddings: 32768
- sliding_window: 32768
- num_attention_heads: 16
- num_key_value_heads: 2
- hidden_size: 2048
