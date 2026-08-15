# Genus-Agent

**Made with Genus**

Genus-Agent is a sophisticated, AI-driven programming assistant designed to integrate directly with your local development environment. By leveraging powerful GenAI APIs, Genus-Agent gains the capability to autonomously analyze, read, and modify files within your codebase, streamlining your development workflow.

## Key Features

- **Autonomous File Management & Drive**: Seamlessly read and edit files, and interact with Google Drive using integrated toolsets.
- **Gmail & Workspace Integration**: Full capability to list, read, send, draft, and manage emails and conversation threads directly from your assistant tools.
- **Advanced GenAI Integration**: Utilizes advanced LLMs to provide intelligent code suggestions, debugging, refactoring, and tool execution.
- **Local Control & Memory**: Designed to operate within your environment, keeping track of user preferences and project context in persistent memory.
- **Task Automation**: Capable of handling repetitive coding tasks, documentation generation, terminal management, and file system access.
- **Extensible Architecture**: Built with modular tools, allowing for easy expansion and customization of agent capabilities.

> [!NOTE]
> A stable internet connection is required to run Genus smoothly; slower connections may affect API response times.

## Prerequisites

- Python 3.x
- An active Gemini API key from [Google AI Studio](https://aistudio.google.com/)
- Google Workspace API credentials (for Gmail and Drive integration)

## Installation & Setup

1. Clone this repository:
   ```bash
   git clone https://github.com/plusstudiocorp/Genus-Agent.git
   cd Genus-Agent
   ```

2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure your Environment & Credentials:
   - Create a `.env` file in the project root and add your Gemini API key:
     ```
     GEMINI_API_KEY=your_actual_api_key_here
     ```
   - **Adding `credentials.json`**: For Gmail and Google Drive features to work, obtain your OAuth 2.0 client credentials from the Google Cloud Console, name the file `credentials.json`, and place it directly into the project root directory (`E:\Mayank\genus\Genus-Agent\`).

## Getting Started

Run the main agent script to start interacting:
```bash
python main.py
```
Once active, you can provide instructions, ask for code generation, request file manipulations, manage emails, or inspect your Google Drive directly through the interface.

## Project Structure

- `main.py`: The entry point for the agent, containing the chat loop and Gemini client configuration.
- `tools/`: A collection of modular tools for file system interaction, Google Drive, Gmail management, web searching, and terminal management.
- `requirements.txt`: List of necessary Python libraries.

## Contributing

We welcome contributions! Please fork the repository, make your changes, and submit a pull request. For significant changes, please open an issue first to discuss the proposed updates.

## License
This project is licensed under the MIT License.
