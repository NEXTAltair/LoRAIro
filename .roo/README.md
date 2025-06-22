# Roo MCP Server Configuration

## GitHub MCP Server Setup

### 1. Copy the template file
```bash
cp .roo/mcp.json.example .roo/mcp.json
```

### 2. Set up environment variables
Create a `.env` file in the project root and add your GitHub token:

```bash
# .env
GITHUB_PERSONAL_ACCESS_TOKEN=your_github_token_here
GITHUB_TOOLSETS=
GITHUB_READ_ONLY=false
```

### 3. Load environment variables
Make sure the environment variables are loaded before starting the MCP server.

## Security Notes

- Never commit files containing actual tokens or API keys
- Use environment variables for sensitive configuration
- The `.roo/mcp.json` file is excluded from git commits
- Only the template file (`.roo/mcp.json.example`) is tracked in git

## Usage

The MCP server will read the configuration from `.roo/mcp.json` and use environment variables for sensitive values.
