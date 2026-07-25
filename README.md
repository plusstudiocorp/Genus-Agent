# Genus-Agent

**Made with Genus**

Genus-Agent is a sophisticated, AI-driven programming assistant designed to integrate directly with your local development environment. By leveraging powerful GenAI APIs, Genus-Agent gains the capability to autonomously analyze, read, and modify files within your codebase, streamlining your development workflow.

## Key Features

- **Autonomous File Management**: Seamlessly read and edit files across your local projects using integrated toolsets.
- **GenAI Integration**: Utilizes advanced LLMs to provide intelligent code suggestions, debugging, and refactoring capabilities.
- **Local Control**: Designed to operate within your environment, ensuring your code and data remain on your machine.
- **Task Automation**: Capable of handling repetitive coding tasks, documentation generation, and boilerplate creation through terminal and file system access.
- **Extensible Architecture**: Built with modular tools, allowing for easy expansion and customization of agent capabilities.

## Prerequisites

- Python 3.x
- An active Gemini API key from [Google AI Studio](https://aistudio.google.com/)

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/plusstudiocorp/Genus-Agent.git
   cd Genus-Agent
   ```

2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure your environment:
   - Rename `.env.example` (or create a new `.env` file) in the project root.
   - Add your API key:
     ```
     GEMINI_API_KEY=your_actual_api_key_here
     ```

## Getting Started

Run the main agent script to start interacting:
```bash
python main.py
```
Once active, you can provide instructions, ask for code generation, or request file manipulations directly through the terminal interface.

## Project Structure

- `main.py`: The entry point for the agent, containing the chat loop and Gemini client configuration.
- `tools/`: A collection of modular tools for file system interaction, web searching, and terminal management.
- `requirements.txt`: List of necessary Python libraries.

## Contributing

We welcome contributions! Please fork the repository, make your changes, and submit a pull request. For significant changes, please open an issue first to discuss the proposed updates.

## License
This project is licensed under the MIT License.
