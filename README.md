# YouTube Transcript Downloader and Summarizer

A CLI tool that downloads YouTube transcripts and generates summaries using OpenAI GPT-4o-mini. Supports YouTube URLs, video IDs, channel IDs, playlists, and search phrases with optional audio playback of summaries.

## Features

- Download and summarize individual YouTube videos
- Process entire channels or playlists
- Search and summarize YouTube videos by query
- Customizable prompt templates for different summary styles
- Audio generation and playback using OpenAI TTS
- Caching system for transcripts and audio files
- Support for clipboard input
- Interactive confirmation prompts

## Setup

### Prerequisites

- Python 3.10+
- YouTube Data API v3 key
- OpenAI API key
- Audio player (mpv or ffplay) for audio playback

### Environment Configuration

Create a `.env` file in the project root with your API keys:

```
YOUTUBE_API_KEY=your_youtube_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
```

#### Getting API Keys

1. **YouTube API Key**: 
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select existing one
   - Enable YouTube Data API v3
   - Create credentials (API key)
   - Copy the key to your `.env` file

2. **OpenAI API Key**:
   - Visit [OpenAI API](https://platform.openai.com/api-keys)
   - Create a new API key
   - Copy the key to your `.env` file

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd youtube-assistant
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure your `.env` file with the API keys (see above)

4. Make the script executable:
```bash
chmod +x assistant.py
```

## Usage

The tool provides several commands for different use cases:

### Single Video

```bash
./assistant.py video "https://youtube.com/watch?v=VIDEO_ID"
./assistant.py video VIDEO_ID
./assistant.py video --clipboard  # Use URL from clipboard
./assistant.py video VIDEO_ID --template compact --play-audio
```

### Channel Videos

```bash
./assistant.py channel CHANNEL_ID --max-videos 5
./assistant.py channel CHANNEL_ID --auto-confirm --template expanded
```

### Playlist

```bash
./assistant.py playlist "https://youtube.com/playlist?list=PLAYLIST_ID"
./assistant.py playlist --clipboard --max-videos 10
```

### Search

```bash
./assistant.py search "machine learning tutorial" --max-results 3
./assistant.py search "python programming" --auto-confirm --play-audio
```

### Command Options

- `--template, -t`: Prompt template name (default, compact, expanded)
- `--clipboard, -c`: Read URL from clipboard
- `--play-audio, -p`: Generate and play audio summary
- `--voice`: TTS voice (alloy, echo, fable, onyx, nova, shimmer)
- `--max-videos, -m`: Maximum number of videos to process
- `--auto-confirm, -y`: Skip confirmation prompts

## Prompt Templates

The tool supports customizable prompt templates stored in the `prompts/` directory:

- `default.txt`: Comprehensive summary with key points
- `compact.txt`: Brief, concise summary
- `expanded.txt`: Detailed analysis with insights

Create custom templates by adding new `.txt` files in the `prompts/` directory.

## File Structure

```
youtube-assistant/
├── assistant.py          # Main application
├── requirements.txt      # Python dependencies
├── .env                 # API keys (create this file)
├── .gitignore          # Git ignore rules
├── README.md           # This file
├── prompts/            # Summary prompt templates
│   ├── default.txt
│   ├── compact.txt
│   └── expanded.txt
├── transcripts/        # Downloaded transcripts (organized by channel)
└── audio/             # Generated audio files
```

## Storage

- **Transcripts**: Stored in `transcripts/CHANNEL_NAME/VIDEO_ID_TITLE.json`
- **Audio**: Stored in `audio/VIDEO_ID_TEMPLATE_openai.mp3`
- **Templates**: Stored in `prompts/TEMPLATE_NAME.txt`

## Requirements

All required Python packages are listed in `requirements.txt`:

- click: Command-line interface
- youtube-transcript-api: Transcript downloading
- google-api-python-client: YouTube API access
- openai: GPT summarization and TTS
- python-dotenv: Environment variable loading
- pyperclip: Clipboard functionality

## Security Notes

- Keep your `.env` file secure and never commit it to version control
- The `.gitignore` file is configured to exclude the `.env` file
- API keys in `.env` should have appropriate usage limits set
- Generated audio files are stored locally and not uploaded anywhere

## Troubleshooting

1. **"Could not download transcript"**: Video may not have transcripts available or may be private
2. **API key errors**: Verify your keys in the `.env` file are correct and have proper permissions
3. **Audio playback issues**: Install mpv (`sudo apt install mpv`) or ffplay for audio support
4. **Rate limiting**: YouTube and OpenAI APIs have rate limits; the tool will show errors if exceeded
