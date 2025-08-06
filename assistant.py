#!/usr/bin/env python3
"""
YouTube Transcript Downloader and Summarizer

A CLI tool that downloads YouTube transcripts and generates summaries using OpenAI GPT-4o-mini.
Supports YouTube URLs, video IDs, channel IDs, and search phrases.
"""

import os
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse, parse_qs
import re
import threading
import time

import click
from youtube_transcript_api import YouTubeTranscriptApi
from googleapiclient.discovery import build
from openai import OpenAI
from dotenv import load_dotenv

# Optional clipboard support
try:
    import pyperclip
    CLIPBOARD_AVAILABLE = True
except ImportError:
    CLIPBOARD_AVAILABLE = False

# Load environment variables
load_dotenv()

class YouTubeSummarizer:
    def __init__(self):
        self.openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.youtube_api_key = os.getenv('YOUTUBE_API_KEY')
        self.youtube = build('youtube', 'v3', developerKey=self.youtube_api_key)
        self.base_dir = Path('transcripts')
        self.base_dir.mkdir(exist_ok=True)
        self.audio_dir = Path('audio')
        self.audio_dir.mkdir(exist_ok=True)
        
    def extract_video_id(self, url_or_id: str) -> str:
        """Extract video ID from YouTube URL or return if already an ID"""
        if len(url_or_id) == 11 and url_or_id.isalnum():
            return url_or_id
            
        patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([^&\n?#]+)',
            r'youtube\.com/v/([^&\n?#]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url_or_id)
            if match:
                return match.group(1)
                
        raise ValueError(f"Could not extract video ID from: {url_or_id}")
    
    def extract_playlist_id(self, url_or_id: str) -> str:
        """Extract playlist ID from YouTube URL or return if already an ID"""
        if len(url_or_id) == 34 and url_or_id.startswith('PL'):
            return url_or_id
        
        # Check if this is a channel URL instead of playlist
        if self._is_channel_url(url_or_id):
            raise ValueError(f"This appears to be a channel URL, not a playlist URL. Use the 'channel' command instead.")
            
        patterns = [
            r'[?&]list=([^&\n?#]+)',
            r'youtube\.com/playlist\?list=([^&\n?#]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url_or_id)
            if match:
                return match.group(1)
                
        raise ValueError(f"Could not extract playlist ID from: {url_or_id}")
    
    def _is_channel_url(self, url: str) -> bool:
        """Check if URL is a channel URL"""
        channel_patterns = [
            r'youtube\.com/channel/[^/]+',
            r'youtube\.com/c/[^/]+',
            r'youtube\.com/@[^/]+',
            r'youtube\.com/user/[^/]+',
        ]
        return any(re.search(pattern, url) for pattern in channel_patterns)
    
    def _is_playlist_url(self, url: str) -> bool:
        """Check if URL is a playlist URL"""
        return 'list=' in url or 'playlist' in url
    
    def get_url_from_clipboard(self) -> str:
        """Try to get YouTube URL from clipboard"""
        if not CLIPBOARD_AVAILABLE:
            raise ValueError("Clipboard functionality requires pyperclip. Install with: pip install pyperclip")
        
        try:
            clipboard_content = pyperclip.paste().strip()
            
            # Check if clipboard contains a YouTube URL
            youtube_patterns = [
                r'youtube\.com',
                r'youtu\.be',
            ]
            
            if any(re.search(pattern, clipboard_content) for pattern in youtube_patterns):
                return clipboard_content
            else:
                raise ValueError(f"Clipboard doesn't contain a YouTube URL. Found: {clipboard_content[:100]}...")
                
        except Exception as e:
            raise ValueError(f"Could not read from clipboard: {str(e)}")
    
    def get_video_info(self, video_id: str) -> Dict:
        """Get video metadata from YouTube API"""
        response = self.youtube.videos().list(
            part='snippet,statistics',
            id=video_id
        ).execute()
        
        if not response['items']:
            raise ValueError(f"Video not found: {video_id}")
            
        return response['items'][0]
    
    def get_channel_videos(self, channel_id: str, max_results: int = 50) -> List[str]:
        """Get video IDs from a channel"""
        # Check if this is a playlist URL instead of channel
        if self._is_playlist_url(channel_id):
            raise ValueError(f"This appears to be a playlist URL, not a channel URL. Use the 'playlist' command instead.")
            
        # Get uploads playlist ID
        channel_response = self.youtube.channels().list(
            part='contentDetails',
            id=channel_id
        ).execute()
        
        if not channel_response['items']:
            raise ValueError(f"Channel not found: {channel_id}")
            
        uploads_playlist_id = channel_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        
        # Get videos from uploads playlist
        videos = []
        next_page_token = None
        
        while len(videos) < max_results:
            playlist_response = self.youtube.playlistItems().list(
                part='contentDetails',
                playlistId=uploads_playlist_id,
                maxResults=min(50, max_results - len(videos)),
                pageToken=next_page_token
            ).execute()
            
            for item in playlist_response['items']:
                videos.append(item['contentDetails']['videoId'])
                
            next_page_token = playlist_response.get('nextPageToken')
            if not next_page_token:
                break
                
        return videos
    
    def get_playlist_videos(self, playlist_id: str, max_results: int = 50) -> List[str]:
        """Get video IDs from a playlist"""
        videos = []
        next_page_token = None
        
        while len(videos) < max_results:
            playlist_response = self.youtube.playlistItems().list(
                part='contentDetails',
                playlistId=playlist_id,
                maxResults=min(50, max_results - len(videos)),
                pageToken=next_page_token
            ).execute()
            
            for item in playlist_response['items']:
                videos.append(item['contentDetails']['videoId'])
                
            next_page_token = playlist_response.get('nextPageToken')
            if not next_page_token:
                break
                
        return videos
    
    def search_videos(self, query: str, max_results: int = 10) -> List[str]:
        """Search for videos by query"""
        search_response = self.youtube.search().list(
            q=query,
            part='id',
            maxResults=max_results,
            type='video'
        ).execute()
        
        return [item['id']['videoId'] for item in search_response['items']]
    
    def get_transcript_path(self, video_id: str) -> Path:
        """Get the file path for storing transcript"""
        video_info = self.get_video_info(video_id)
        channel_title = re.sub(r'[<>:"/\\|?*]', '_', video_info['snippet']['channelTitle'])
        video_title = re.sub(r'[<>:"/\\|?*]', '_', video_info['snippet']['title'])
        
        channel_dir = self.base_dir / channel_title
        channel_dir.mkdir(exist_ok=True)
        
        return channel_dir / f"{video_id}_{video_title}.json"
    
    def download_transcript(self, video_id: str) -> Dict:
        """Download transcript for a video"""
        transcript_path = self.get_transcript_path(video_id)
        
        # Check if transcript already exists
        if transcript_path.exists():
            with open(transcript_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        try:
            # Try to get transcript
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
            full_text = ' '.join([entry['text'] for entry in transcript_list])
            
            # Get video metadata
            video_info = self.get_video_info(video_id)
            
            transcript_data = {
                'video_id': video_id,
                'title': video_info['snippet']['title'],
                'channel': video_info['snippet']['channelTitle'],
                'published_at': video_info['snippet']['publishedAt'],
                'transcript': transcript_list,
                'full_text': full_text,
                'summaries': {}
            }
            
            # Save transcript
            with open(transcript_path, 'w', encoding='utf-8') as f:
                json.dump(transcript_data, f, indent=2, ensure_ascii=False)
                
            return transcript_data
            
        except Exception as e:
            raise ValueError(f"Could not download transcript for {video_id}: {str(e)}")
    
    def load_prompt_template(self, template_name: str) -> str:
        """Load prompt template from file"""
        template_path = Path('prompts') / f"{template_name}.txt"
        
        if not template_path.exists():
            # Create default template if it doesn't exist
            default_template = """Please provide a comprehensive summary of the following YouTube video transcript.

Include:
1. Main topics and key points
2. Important insights or conclusions
3. Any actionable information
4. Overall theme and purpose

Transcript:
{transcript}"""
            
            template_path.parent.mkdir(exist_ok=True)
            with open(template_path, 'w') as f:
                f.write(default_template)
                
        with open(template_path, 'r') as f:
            return f.read()
    
    def summarize_transcript(self, transcript_data: Dict, prompt_template: str) -> str:
        """Generate summary using OpenAI GPT-4o-mini"""
        video_id = transcript_data['video_id']
        
        # Ensure summaries dict exists (for backward compatibility)
        if 'summaries' not in transcript_data:
            transcript_data['summaries'] = {}
        
        # Check if summary already exists for this template
        if prompt_template in transcript_data['summaries']:
            click.echo(f"Using cached summary for template '{prompt_template}'")
            return transcript_data['summaries'][prompt_template]
        
        # Generate new summary
        click.echo(f"Generating new summary using template '{prompt_template}'...")
        template = self.load_prompt_template(prompt_template)
        prompt = template.format(transcript=transcript_data['full_text'])
        
        response = self.openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that creates concise and informative summaries of video transcripts."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.3
        )
        
        summary = response.choices[0].message.content
        
        # Save summary to transcript data
        transcript_data['summaries'][prompt_template] = summary
        
        # Save updated transcript data to file
        transcript_path = self.get_transcript_path(video_id)
        with open(transcript_path, 'w', encoding='utf-8') as f:
            json.dump(transcript_data, f, indent=2, ensure_ascii=False)
        
        return summary
    
    def get_audio_path(self, video_id: str, template_name: str) -> Path:
        """Get the file path for storing audio summary"""
        return self.audio_dir / f"{video_id}_{template_name}_openai.mp3"
    
    def generate_openai_audio(self, summary: str, video_id: str, template_name: str, voice: str = "alloy") -> Path:
        """Generate high-quality audio using OpenAI TTS API"""
        audio_path = self.get_audio_path(video_id, template_name)
        
        try:
            click.echo("Generating high-quality audio with OpenAI TTS...")
            response = self.openai_client.audio.speech.create(
                model="tts-1-hd",  # High quality model
                voice=voice,  # alloy, echo, fable, onyx, nova, shimmer
                input=summary,
                response_format="mp3"
            )
            
            # Save the audio file
            with open(audio_path, 'wb') as f:
                f.write(response.content)
                
            return audio_path
            
        except Exception as e:
            click.echo(f"Error generating OpenAI audio: {e}", err=True)
            raise e
    
    def play_summary_audio(self, summary: str, video_id: str, template_name: str, voice: str = "alloy") -> None:
        """Generate and play audio for summary using OpenAI TTS"""
        audio_path = self.get_audio_path(video_id, template_name)
        
        # Check if audio file already exists
        if audio_path.exists() and audio_path.stat().st_size > 0:
            click.echo("Playing cached audio summary...")
            try:
                # Use OS command to play audio file
                os.system(f"mpv '{audio_path}' --really-quiet 2>/dev/null || ffplay -nodisp -autoexit -v quiet '{audio_path}' 2>/dev/null || echo 'Audio file created but no audio player found'")
                return
            except Exception as e:
                click.echo(f"Error playing cached audio: {e}", err=True)
        
        # Generate new audio file
        try:
            audio_path = self.generate_openai_audio(summary, video_id, template_name, voice)
            click.echo("Playing audio summary...")
            os.system(f"mpv '{audio_path}' --really-quiet 2>/dev/null || ffplay -nodisp -autoexit -v quiet '{audio_path}' 2>/dev/null || echo 'Audio file created but no audio player found'")
        except Exception as e:
            click.echo(f"Error generating/playing audio: {e}", err=True)

@click.group()
def cli():
    """YouTube Transcript Downloader and Summarizer"""
    pass

@cli.command()
@click.argument('url_or_id', required=False)
@click.option('--template', '-t', default='default', help='Prompt template name')
@click.option('--clipboard', '-c', is_flag=True, help='Read URL from clipboard')
@click.option('--play-audio', '-p', is_flag=True, help='Play audio of the summary using OpenAI TTS')
@click.option('--voice', default='alloy', help='Voice for OpenAI TTS (alloy, echo, fable, onyx, nova, shimmer)')
def video(url_or_id, template, clipboard, play_audio, voice):
    """Download and summarize a single YouTube video"""
    summarizer = YouTubeSummarizer()
    
    try:
        # Get URL from clipboard or argument
        if clipboard:
            if url_or_id:
                click.echo("Warning: Using clipboard URL, ignoring provided URL argument")
            url_or_id = summarizer.get_url_from_clipboard()
            click.echo(f"Using URL from clipboard: {url_or_id}")
        elif not url_or_id:
            raise click.UsageError("Either provide a URL/ID as argument or use --clipboard flag")
        
        video_id = summarizer.extract_video_id(url_or_id)
        click.echo(f"Processing video: {video_id}")
        
        transcript_data = summarizer.download_transcript(video_id)
        click.echo(f"Downloaded transcript for: {transcript_data['title']}")
        
        summary = summarizer.summarize_transcript(transcript_data, template)
        
        click.echo("\n" + "="*80)
        click.echo(f"SUMMARY - {transcript_data['title']}")
        click.echo("="*80)
        click.echo(summary)
        
        # Play audio if requested
        if play_audio:
            summarizer.play_summary_audio(summary, video_id, template, voice)
        
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)

@cli.command()
@click.argument('channel_id')
@click.option('--template', '-t', default='default', help='Prompt template name')
@click.option('--max-videos', '-m', default=10, help='Maximum number of videos to process')
@click.option('--auto-confirm', '-y', is_flag=True, help='Skip confirmation prompts')
@click.option('--play-audio', '-p', is_flag=True, help='Play audio of each summary using OpenAI TTS')
@click.option('--voice', default='alloy', help='Voice for OpenAI TTS (alloy, echo, fable, onyx, nova, shimmer)')
def channel(channel_id, template, max_videos, auto_confirm, play_audio, voice):
    """Download and summarize videos from a YouTube channel"""
    summarizer = YouTubeSummarizer()
    
    try:
        click.echo(f"Getting videos from channel: {channel_id}")
        video_ids = summarizer.get_channel_videos(channel_id, max_videos)
        
        # Show video list and ask for confirmation
        click.echo(f"\nFound {len(video_ids)} videos from channel:")
        for i, video_id in enumerate(video_ids[:5], 1):  # Show first 5 titles
            try:
                video_info = summarizer.get_video_info(video_id)
                click.echo(f"{i}. {video_info['snippet']['title']}")
            except:
                click.echo(f"{i}. {video_id} (couldn't get title)")
        
        if len(video_ids) > 5:
            click.echo(f"... and {len(video_ids) - 5} more videos")
        
        if not auto_confirm:
            if not click.confirm(f"\nProcess all {len(video_ids)} videos?"):
                click.echo("Cancelled.")
                return
        
        selected_videos = []
        for i, video_id in enumerate(video_ids, 1):
            try:
                video_info = summarizer.get_video_info(video_id)
                video_title = video_info['snippet']['title']
                
                if not auto_confirm:
                    if not click.confirm(f"\nProcess video {i}/{len(video_ids)}: {video_title}?"):
                        click.echo("Skipped.")
                        continue
                
                selected_videos.append((video_id, video_title))
                
            except Exception as e:
                click.echo(f"Error getting info for video {video_id}: {str(e)}", err=True)
                continue
        
        # Process selected videos
        for i, (video_id, video_title) in enumerate(selected_videos, 1):
            click.echo(f"\nProcessing video {i}/{len(selected_videos)}: {video_id}")
            
            try:
                transcript_data = summarizer.download_transcript(video_id)
                click.echo(f"Downloaded transcript for: {transcript_data['title']}")
                
                summary = summarizer.summarize_transcript(transcript_data, template)
                
                click.echo("\n" + "="*80)
                click.echo(f"SUMMARY {i} - {transcript_data['title']}")
                click.echo("="*80)
                click.echo(summary)
                
                # Play audio if requested
                if play_audio:
                    summarizer.play_summary_audio(summary, video_id, template, voice)
                
            except Exception as e:
                click.echo(f"Error processing video {video_id}: {str(e)}", err=True)
                continue
                
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)

@cli.command()
@click.argument('query')
@click.option('--template', '-t', default='default', help='Prompt template name')
@click.option('--max-results', '-m', default=5, help='Maximum number of search results to process')
@click.option('--auto-confirm', '-y', is_flag=True, help='Skip confirmation prompts')
@click.option('--play-audio', '-p', is_flag=True, help='Play audio of each summary using OpenAI TTS')
@click.option('--voice', default='alloy', help='Voice for OpenAI TTS (alloy, echo, fable, onyx, nova, shimmer)')
def search(query, template, max_results, auto_confirm, play_audio, voice):
    """Search for and summarize YouTube videos"""
    summarizer = YouTubeSummarizer()
    
    try:
        click.echo(f"Searching for: {query}")
        video_ids = summarizer.search_videos(query, max_results)
        
        # Show search results and ask for confirmation
        click.echo(f"\nFound {len(video_ids)} videos for query '{query}':")
        for i, video_id in enumerate(video_ids, 1):
            try:
                video_info = summarizer.get_video_info(video_id)
                click.echo(f"{i}. {video_info['snippet']['title']} - {video_info['snippet']['channelTitle']}")
            except:
                click.echo(f"{i}. {video_id} (couldn't get title)")
        
        if not auto_confirm:
            if not click.confirm(f"\nProcess all {len(video_ids)} videos?"):
                click.echo("Cancelled.")
                return
        
        selected_videos = []
        for i, video_id in enumerate(video_ids, 1):
            try:
                video_info = summarizer.get_video_info(video_id)
                video_title = video_info['snippet']['title']
                channel_title = video_info['snippet']['channelTitle']
                
                if not auto_confirm:
                    if not click.confirm(f"\nProcess video {i}/{len(video_ids)}: {video_title} by {channel_title}?"):
                        click.echo("Skipped.")
                        continue
                
                selected_videos.append((video_id, video_title))
                
            except Exception as e:
                click.echo(f"Error getting info for video {video_id}: {str(e)}", err=True)
                continue
        
        # Process selected videos
        for i, (video_id, video_title) in enumerate(selected_videos, 1):
            click.echo(f"\nProcessing video {i}/{len(selected_videos)}: {video_id}")
            
            try:
                transcript_data = summarizer.download_transcript(video_id)
                click.echo(f"Downloaded transcript for: {transcript_data['title']}")
                
                summary = summarizer.summarize_transcript(transcript_data, template)
                
                click.echo("\n" + "="*80)
                click.echo(f"SUMMARY {i} - {transcript_data['title']}")
                click.echo("="*80)
                click.echo(summary)
                
            except Exception as e:
                click.echo(f"Error processing video {video_id}: {str(e)}", err=True)
                continue
                
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)

@cli.command()
@click.argument('playlist_url_or_id', required=False)
@click.option('--template', '-t', default='default', help='Prompt template name')
@click.option('--max-videos', '-m', default=50, help='Maximum number of videos to process')
@click.option('--auto-confirm', '-y', is_flag=True, help='Skip confirmation prompts')
@click.option('--clipboard', '-c', is_flag=True, help='Read URL from clipboard')
@click.option('--play-audio', '-p', is_flag=True, help='Play audio of each summary using OpenAI TTS')
@click.option('--voice', default='alloy', help='Voice for OpenAI TTS (alloy, echo, fable, onyx, nova, shimmer)')
def playlist(playlist_url_or_id, template, max_videos, auto_confirm, clipboard, play_audio, voice):
    """Download and summarize videos from a YouTube playlist"""
    summarizer = YouTubeSummarizer()
    
    try:
        # Get URL from clipboard or argument
        if clipboard:
            if playlist_url_or_id:
                click.echo("Warning: Using clipboard URL, ignoring provided URL argument")
            playlist_url_or_id = summarizer.get_url_from_clipboard()
            click.echo(f"Using URL from clipboard: {playlist_url_or_id}")
        elif not playlist_url_or_id:
            raise click.UsageError("Either provide a playlist URL/ID as argument or use --clipboard flag")
        
        playlist_id = summarizer.extract_playlist_id(playlist_url_or_id)
        click.echo(f"Getting videos from playlist: {playlist_id}")
        video_ids = summarizer.get_playlist_videos(playlist_id, max_videos)
        
        click.echo(f"\nFound {len(video_ids)} videos in playlist.")
        
        # Handle video selection based on options
        if auto_confirm:
            # Auto-confirm mode - process all videos
            selected_videos = []
            for video_id in video_ids:
                try:
                    video_info = summarizer.get_video_info(video_id)
                    video_title = video_info['snippet']['title']
                    selected_videos.append((video_id, video_title))
                except Exception as e:
                    click.echo(f"Error getting info for video {video_id}: {str(e)}", err=True)
                    continue
        else:
            # Show each video individually and ask for confirmation (default yes)
            selected_videos = []
            for i, video_id in enumerate(video_ids, 1):
                try:
                    video_info = summarizer.get_video_info(video_id)
                    video_title = video_info['snippet']['title']
                    
                    # Show video info and ask for confirmation with default Yes
                    click.echo(f"\nVideo {i}/{len(video_ids)}: {video_title}")
                    if click.confirm("Process this video?", default=True):
                        selected_videos.append((video_id, video_title))
                    else:
                        click.echo("Skipped.")
                    
                except Exception as e:
                    click.echo(f"Error getting info for video {video_id}: {str(e)}", err=True)
                    continue
        
        # Process selected videos
        for i, (video_id, video_title) in enumerate(selected_videos, 1):
            click.echo(f"\nProcessing video {i}/{len(selected_videos)}: {video_id}")
            
            try:
                transcript_data = summarizer.download_transcript(video_id)
                click.echo(f"Downloaded transcript for: {transcript_data['title']}")
                
                summary = summarizer.summarize_transcript(transcript_data, template)
                
                click.echo("\n" + "="*80)
                click.echo(f"SUMMARY {i} - {transcript_data['title']}")
                click.echo("="*80)
                click.echo(summary)
                
                # Play audio if requested
                if play_audio:
                    summarizer.play_summary_audio(summary, video_id, template, voice)
                
            except Exception as e:
                click.echo(f"Error processing video {video_id}: {str(e)}", err=True)
                continue
                
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)

if __name__ == '__main__':
    cli()