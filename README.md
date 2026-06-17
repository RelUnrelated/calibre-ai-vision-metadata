# AI Vision Metadata

**Version:** 1.1.0  
**Author:** RelUnrelated (<dan@relunrelated.com>)  
**License:** GNU General Public License v3.0 (GPLv3) — See the `LICENSE.md` file for details.  
**Changelog:** See the `CHANGELOG.md` file for release history and updates.  

---

## Overview
AI Vision Metadata is a custom Calibre plugin designed to automate the extraction of metadata from publication covers. By leveraging state-of-the-art AI vision models, it analyzes cover art to identify specific issue numbers, publication dates, publishers, and creators, making it an invaluable tool for cataloging comics, magazines, and vintage periodicals.

Originally built around Google's Gemini API, the plugin has evolved into a robust, multi-agent engine tailored for power users.

## Key Features

* **Multi-Provider Routing:** Seamlessly switch between cloud-based AI models (Google Gemini, OpenAI, Anthropic, OpenRouter) or route requests to your own local, offline models using Ollama or LM Studio.
* **Sequential Batch Processing:** Select multiple publications at once. The plugin intelligently queues the requests in the background, preventing rate-limit bans and UI lockups.
* **Side-by-Side Review GUI:** Never fly blind. The plugin presents a crisp, scaled thumbnail of the cover image right next to the extracted metadata, allowing you to easily verify the AI's accuracy.
* **Isolated Memory Banks:** The configuration menu securely remembers your distinct API keys, model selections, and custom system prompts for every individual provider.
* **Advanced Prompt Tuning:** Directly edit the AI's core instructions to fine-tune extraction behavior for the unique quirks of your specific collection.
* **Thread-Safe Architecture:** Background processing ensures your main Calibre window never freezes, while gracefully catching and reporting network or API errors.

## Installation
Since this is a custom plugin, it must be installed manually through Calibre's interface.

1. Download the release archive. Inside, you will find the `ai_vision_metadata.zip` plugin file. *(Do not unzip this plugin file).*
2. Open Calibre and click on **Preferences** (the gear icon) in the top toolbar.
3. Under the "Advanced" section, click on **Plugins**.
4. Click the **Load plugin from file** button in the bottom right corner.
5. Navigate to and select the `ai_vision_metadata.zip` file.
6. Click **Yes** to accept the security warning and install the plugin.
7. Restart Calibre for the changes to take effect.

## Configuration
Before using the tool, you must configure it with an API key or a local server address.

1. Go to **Preferences > Plugins** and locate **AI Vision Metadata** under the *User interface action* category. Double-click to open the configuration window.
2. **AI Provider:** Select your preferred AI engine from the dropdown (Google Gemini, OpenAI, Anthropic, OpenRouter, or Local). The UI will dynamically update to show the settings for that specific provider. OpenRouter will populate its model list without an API key.
3. **API Key / Local URL:** Paste your API key for the selected cloud provider. If using a local model, ensure your Local Base URL is correct (e.g., `http://localhost:11434` for Ollama).
4. **Model Name:** Click **Fetch Available Models** to populate the dropdown menu directly from your chosen provider, then select the specific model you wish to use.
5. **System Prompt (Advanced):** You can safely tweak the AI's core instructions here. Every provider remembers its own prompt.
6. Click **Apply** or **OK** to save.

## Usage
Once configured, the plugin integrates seamlessly into your standard Calibre workflow.

1. **Select Publications:** Highlight one or more entries in your Calibre library that have cover images. *(Batch processing is fully supported).*
2. **Trigger the Plugin:** Click the AI Vision Metadata button in your main toolbar, or right-click the highlighted books and select it from the context menu. 
3. **Wait for Processing:** The plugin runs in a safe background thread. It will analyze the first image and compile the data.
4. **Review the Data:** A "Review AI Metadata" window will appear, featuring the cover image on the left and the extracted data on the right. 
   * **Action Indicators:** Every field includes a muted sub-label (e.g., *Replaces*, *Merges*, *Appends*) so you know exactly whether checking the box will overwrite your existing Calibre data or safely add to it.
   * **Checkboxes:** Use the checkboxes to select exactly which fields you want to import. Unchecked fields will be ignored, preserving your existing Calibre database entries.
   * **Editable Dropdowns:** Fields like *Series Index* offer auto-generated formats, but you can manually type directly into the box for edge cases.
5. **Apply & Auto-Advance:** Click **OK** to save the checked metadata directly to Calibre. If you selected multiple books, the plugin will seamlessly load the next cover in your queue and begin processing it immediately.

## Provider Setup Guide

To use the cloud features of this plugin, you will need to generate an API key from your preferred provider. Treat these keys like passwords. 

**Google Gemini (Recommended for Free Tier)**
* Navigate to [Google AI Studio](https://aistudio.google.com/app/apikey) to generate a free API key.
* *Note on Limits:* `gemini-2.0-flash` offers generous free daily quotas. Using `gemini-2.5-pro` for complex covers and deep web searching is highly recommended, but it requires adding a billing profile to your Google Cloud account to lift strict rate limits.

**OpenAI (ChatGPT)**
* Navigate to the [OpenAI Platform](https://platform.openai.com/api-keys) to generate a key.
* *Requirements:* OpenAI no longer offers free API grants. You must add prepaid credits (minimum $5) to your developer dashboard for the API to process requests.

**Anthropic (Claude)**
* Navigate to the [Anthropic Console](https://console.anthropic.com/settings/keys) to generate a key.
* *Requirements:* Like OpenAI, Anthropic requires you to load prepaid credits to your account before API requests will be authorized (otherwise you will receive an immediate HTTP 400 error).

**OpenRouter**
* Navigate to the [OpenRouter Console](https://openrouter.ai/settings/keys) to generate a key.
* *Requirements:* OpenRouter provides access to a large variety of models from over sixty providers. OpenRouter requires you to load prepaid credits to your account before API requests will be authorized. The list of models in the configuration window will contain all of those which support image input.

**Local Models (Ollama / LM Studio)**
* You can run vision-capable models (like `llava`) completely offline on your own hardware.
* Download [Ollama](https://ollama.com/) or [LM Studio](https://lmstudio.ai/). Make sure your local server is running, verify the Base URL in the plugin settings, and fetch the models you have downloaded.