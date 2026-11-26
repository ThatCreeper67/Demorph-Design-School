# Dataset and model-training status

## Current model use

DEMORPH Design School does **not** fine-tune or train Qwen. The application sends each uploaded image and optional brief to the configured local Ollama model (`qwen3.5:9b-q4_K_M`) for inference. The repository contains no trained model weights or adapters. The curriculum, annotation schemas, scripts, and evaluation records document the analysis workflow; they are not proof that the foundation model was trained on this material.

## Image collection status

The local working copy contains 96 images under `designs/original/`. The source register at `manifests/source_register.csv` records all 96 as `unknown` provenance with `unconfirmed` permission. The image manifest marks them ineligible for training. Their presence in this project does not grant permission to redistribute them.

For that reason, the original images, generated/processed images, and image caches must stay out of the public Git repository unless and until each image has documented redistribution rights. The metadata manifests may be shared to document the inventory and its status, but they do not include the image files. This means a public checkout will not contain the image collection or reproduce image-based evaluations that depend on it.

## Preparing a redistributable dataset

Before adding any image to a public release, update its source record with a verifiable source URL or owner, exact license or written permission, required attribution, and reviewer/date. Confirm that the terms allow redistribution and the intended use. Keep dataset rights separate from the software license in `LICENSE`; the project's MIT license does not apply to third-party images.

Once images are individually cleared, place only those assets in a dedicated dataset directory with a dataset card, per-image attribution and license records, and checksums. Describe them as an evaluation or demonstration dataset unless a real training process is added and documented.
