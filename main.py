import os
import re
import fnmatch
import argparse
from pathlib import Path
import asyncio
import aiohttp
from dotenv import load_dotenv
from openai import AsyncOpenAI
from collections import defaultdict

# Load environment variables from .env file
load_dotenv()

api_key = os.getenv('OPENAI_API_KEY')
if not api_key:
    raise ValueError("OPENAI_API_KEY not found in .env file")
api_model = os.getenv('OPENAI_API_MODEL')
if not api_model:
    raise ValueError("OPENAI_API_MODEL not found in .env file")

# Initialize the OpenAI client with the API key from .env
client = AsyncOpenAI(api_key=api_key)

def parse_fileignore(fileignore_path):
    ignore_patterns = []
    if os.path.exists(fileignore_path):
        with open(fileignore_path, 'r') as fileignore:
            for line in fileignore:
                line = line.strip()
                if line and not line.startswith('#'):
                    ignore_patterns.append(line)
    return ignore_patterns

def should_ignore(path, base_path, ignore_patterns):
    rel_path = os.path.relpath(path, base_path)
    path_parts = rel_path.split(os.sep)
    
    for pattern in ignore_patterns:
        if pattern.endswith('/'):
            if any(fnmatch.fnmatch(part, pattern[:-1]) for part in path_parts):
                return True
        elif '/' in pattern:
            if fnmatch.fnmatch(rel_path, pattern):
                return True
        else:
            if any(fnmatch.fnmatch(part, pattern) for part in path_parts):
                return True
    return False

async def summarize_script(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()

        prompt = f"Please provide a one-line summary of what this script does:\n\n{content}\n\nOne-line summary:"
        
        response = await client.chat.completions.create(
            model=api_model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes code."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0
        )
        
        summary = response.choices[0].message.content.strip()
        return summary

    except Exception as e:
        return f"Error analyzing file: {str(e)}"

async def analyze_folder(folder_path, ignore_patterns, analyze_all):
    summaries = []
    tasks = []

    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if not should_ignore(os.path.join(root, d), folder_path, ignore_patterns)]
        
        for file in files:
            if analyze_all or file.endswith(('.sh', '.bash', '.py', '.js', '.ts')):
                file_path = os.path.join(root, file)
                
                if not should_ignore(file_path, folder_path, ignore_patterns):
                    relative_path = os.path.relpath(file_path, folder_path)
                    print(f"Analyzing: {relative_path}")
                    task = summarize_script(file_path)
                    tasks.append((relative_path, task))

    results = await asyncio.gather(*(task for _, task in tasks))
    summaries = [(path, result) for (path, _), result in zip(tasks, results)]
    return summaries

async def analyze_single_file(file_path):
    summary = await summarize_script(file_path)
    return [(os.path.basename(file_path), summary)]

def create_readme(summaries, output_file):
    # Group summaries by folder
    grouped_summaries = defaultdict(list)
    for path, summary in summaries:
        folder = os.path.dirname(path)
        grouped_summaries[folder].append((os.path.basename(path), summary))

    with open(output_file, 'w', encoding='utf-8') as readme:
        readme.write("# Script Summaries\n\n")

        # Sort the folders
        for folder in sorted(grouped_summaries.keys()):
            if folder:
                readme.write(f"## {folder}\n\n")
            else:
                readme.write("## Root\n\n")
            
            readme.write("| Script | Description |\n")
            readme.write("| ------ | ----------- |\n")
            # Sort the files within each folder
            for script, description in sorted(grouped_summaries[folder]):
                readme.write(f"| {script} | {description} |\n")
            readme.write("\n")



async def main():
    parser = argparse.ArgumentParser(description="Analyze scripts in a folder or a single file and create a README_SUMMARY.md")
    parser.add_argument("path", help="Path to the folder or file to analyze")
    parser.add_argument("--all", action="store_true", help="Analyze all files regardless of extension")
    args = parser.parse_args()

    path = args.path
    if not os.path.exists(path):
        print("Invalid path.")
        return

    fileignore_path = os.path.join('.', '.ignore_files')
    ignore_patterns = parse_fileignore(fileignore_path)
    
    if os.path.isdir(path):
        summaries = await analyze_folder(path, ignore_patterns, args.all)
    else:
        summaries = await analyze_single_file(path)
    
    output_file = os.path.join(path, 'README_SUMMARY.md')
    create_readme(summaries, output_file)
    print(f"{output_file} has been created with the script summaries.")

if __name__ == "__main__":
    asyncio.run(main())
