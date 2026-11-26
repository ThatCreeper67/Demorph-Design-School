# Quickstart: local design analysis

1. Start Ollama and confirm the required `qwen3.5:9b-q4_K_M` model is already installed.
2. From the project root, run:

   ```powershell
   .\start_local_app.ps1
   ```

3. Open **http://127.0.0.1:8765**.
4. Drop a PNG, JPG/JPEG, or WEBP into the image panel, or browse to select one.
5. Check the preview, dimensions, and file size. Add a brief if the design has a specific audience or communication goal.
6. Select **Analyze design**. The app reports real backend stages and waits for the local Qwen response; it does not invent a percentage.
7. Review the evidence-backed observations, relationships, hierarchy, evaluations, and any recommendations. Open evidence details to see which visible cues support each claim.
8. Export JSON or Markdown, or reopen the result later from the local history list.
9. Choose **New analysis** to submit another image. Stop the app with **Ctrl+C** in its terminal.

The first run may be slow while Ollama loads the model. The app does not fetch models from the network. Model findings are drafts, not approved design labels.
