#!/bin/bash

# Check if a folder path is provided
if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <path_to_folder>"
  exit 1
fi
FOLDER_PATH=$1

# Find .mscx file in directory
MSCX_FILE=$(find $FOLDER_PATH -maxdepth 1 -type f -name "*.mscx")
if [ -z "$MSCX_FILE" ]; then
  echo "No .mscx files found in the folder"
  exit 1
fi

python3 export.py $MSCX_FILE