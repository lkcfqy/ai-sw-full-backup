"""Pinned model identities; weights remain outside the project in a shared folder."""

PROFILES = {
    "Qwen3-VL-8B-Instruct-8bit": {
        "label": "Qwen3-VL-8B-Instruct · MLX 8-bit · local",
        "repo_id": "mlx-community/Qwen3-VL-8B-Instruct-8bit",
        "revision": "a0093b9b5fda6f76ddd4a462c6830ae7c4fe47ec",
        "weights": {
            "model-00001-of-00002.safetensors": 5_343_910_279,
            "model-00002-of-00002.safetensors": 4_511_968_734,
        },
    },
    "Qwen3.6-27B-4bit": {
        "label": "Qwen3.6-27B · MLX 4-bit · local",
        "repo_id": "mlx-community/Qwen3.6-27B-4bit",
        "revision": "c000ac2c2057d94be3fa931000c31723aac53282",
        "weights": {
            "model-00001-of-00003.safetensors": 5_343_268_752,
            "model-00002-of-00003.safetensors": 5_354_185_100,
            "model-00003-of-00003.safetensors": 5_357_087_747,
        },
    },
}
DEFAULT_PROFILE = "Qwen3.6-27B-4bit"
